"""Replay historian: 168 h of operating history generated from the twin.

Three views are kept, exactly as an on-line twin would have them:

* **truth**  — the twin driven by the real ore and the real (event-affected) equipment state;
* **measurement** — truth sampled at each instrument with noise, quantisation and scripted
  sensor faults (drift, flat-line, loss of signal);
* **model** — what the twin believes: DCS setpoints and lagged ore estimates, with no knowledge
  of the events. The residual between model and measurement is what drives the diagnostics page.

Six events are scripted into the week so the desk always has something to diagnose.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from datetime import datetime, timedelta, timezone, timezone
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.models.domain import OperatingConfig, OreConfig
from app.services.plant_service import TAGS, get_plant_service
from app.twin.circuit import solve
from app.utils.math_helpers import get_path

REPLAY_HOURS = 168

EVENTS: list[dict] = [
    {"key": "clay_surge", "label": "Clay-rich ore band (pit blend change)", "type": "process",
     "unit_id": "scrubber", "start_h": 18, "end_h": 38,
     "signature": "Head alumina climbs, scrubber power falls as the charge slurries, lump alumina rises",
     "severity": "high"},
    {"key": "jig_screen_blind", "label": "Lump jig screen plate blinding", "type": "process",
     "unit_id": "lump_jig", "start_h": 50, "end_h": 62,
     "signature": "Bed loosens at constant hutch water, cut density drifts up, lump yield falls",
     "severity": "medium"},
    {"key": "hutch_pump_fault", "label": "Jig hutch-water pump cavitation", "type": "process",
     "unit_id": "lump_jig", "start_h": 78, "end_h": 90,
     "signature": "Actual hutch water below set-point, bed tightens, lump alumina rises",
     "severity": "high"},
    {"key": "spiral_choke", "label": "Spiral feed distributor partially choked", "type": "process",
     "unit_id": "spirals", "start_h": 104, "end_h": 116,
     "signature": "Uneven start loading, concentrate grade falls while middling tonnage rises",
     "severity": "medium"},
    {"key": "whims_matrix_blind", "label": "WHIMS matrix blinding", "type": "process", "unit_id": "whims",
     "start_h": 122, "end_h": 140,
     "signature": "Magnetic recovery decays at constant field, wash water pressure rises",
     "severity": "medium"},
    {"key": "analyser_drift", "label": "Lump on-belt analyser drift (alumina channel)", "type": "sensor",
     "unit_id": "lump_jig", "start_h": 128, "end_h": 156,
     "signature": "302_AIC_025 reads progressively low against the twin", "severity": "medium"},
    {"key": "density_flatline", "label": "Classifier overflow densimeter frozen", "type": "sensor",
     "unit_id": "spiral_classifier", "start_h": 144, "end_h": 158,
     "signature": "401_DI_032 zero variance while dilution water moves", "severity": "low"},
]
EVENT_BY_KEY = {e["key"]: e for e in EVENTS}


class _LRU(OrderedDict):
    def __init__(self, size: int = 2400):
        super().__init__()
        self.size = size

    def put(self, k, v):  # noqa: ANN001, ANN201
        self[k] = v
        self.move_to_end(k)
        if len(self) > self.size:
            self.popitem(last=False)


def _active(hour: float) -> list[dict]:
    return [e for e in EVENTS if e["start_h"] <= (hour % REPLAY_HOURS) < e["end_h"]]


class HistorianService:
    """Deterministic 168 h replay, cached per (plant, hour)."""

    def __init__(self) -> None:
        self._truth = _LRU()
        self._model = _LRU()
        self.fixed_anchor = datetime.fromisoformat(get_settings().REPLAY_ANCHOR_UTC.replace("Z", "+00:00"))

    @property
    def anchor(self) -> datetime:
        """Start of the replay week, rolled forward so that the current replay hour reads as now.

        The demo historian loops a deterministic 168 h week; anchoring it to wall-clock time keeps
        the operator desk honest — a live snapshot carries the current timestamp rather than a date
        from whenever the replay was defined.
        """
        now = datetime.now(timezone.utc)
        return now - timedelta(hours=(now.timestamp() / 3600.0) % REPLAY_HOURS)

    # ---- drivers -------------------------------------------------------------------------------
    def drivers(self, plant_id: str, hour: float) -> dict:
        """Ore and operating drivers for this replay hour (deterministic)."""
        ps = get_plant_service()
        fs, ore, op, ec = ps.configs(plant_id)
        h = hour % REPLAY_HOURS
        seed = abs(hash((plant_id, int(h)))) % (2 ** 31)
        rng = np.random.default_rng(seed)
        day = 2 * math.pi * h / 24.0
        week = 2 * math.pi * h / REPLAY_HOURS
        ore_d = ore.model_dump()
        active = {e["key"] for e in _active(h)}
        #: the pit delivers a blend, not a constant: grade, clay content and friability all move
        #: together on a bench-to-bench scale, and it is the clay that drives this plant
        ore_d["fe_head_pct"] = float(np.clip(ore.fe_head_pct + 1.8 * math.sin(week * 2) + 0.7 * math.sin(day)
                                             + rng.normal(0, 0.30), 44.0, 62.0))
        ore_d["sio2_head_pct"] = float(np.clip(ore.sio2_head_pct - 1.1 * math.sin(week * 2)
                                               + rng.normal(0, 0.35), 4.0, 16.0))
        clay_surge = 2.1 if "clay_surge" in active else 0.0
        ore_d["al2o3_head_pct"] = float(np.clip(ore.al2o3_head_pct + clay_surge
                                                - 0.9 * math.sin(week * 2) + rng.normal(0, 0.22), 2.0, 10.0))
        ore_d["clay_share"] = float(np.clip(ore.clay_share + (0.12 if clay_surge else 0.0)
                                            + 0.06 * math.sin(week * 3 + 0.4) + rng.normal(0, 0.015),
                                            0.15, 0.85))
        ore_d["lump_friability"] = float(np.clip(ore.lump_friability + (0.10 if clay_surge else 0.0)
                                                 + 0.05 * math.sin(week * 3) + rng.normal(0, 0.012), 0.05, 0.7))
        ore_d["liberation_d50_um"] = float(np.clip(ore.liberation_d50_um + 2600.0 * math.sin(week * 3 + 1.1)
                                                   + rng.normal(0, 420.0), 6_000.0, 40_000.0))
        ore_d["axb"] = float(np.clip(ore.axb - 5.0 * math.sin(week * 2 + 0.7) + rng.normal(0, 1.0), 30.0, 90.0))
        op_d = op.model_dump()
        op_d["rom_feed_tph"] = float(np.clip(op.rom_feed_tph * (1.0 + 0.030 * math.sin(day + 0.4))
                                             + rng.normal(0, 5.0), 300.0, 900.0))
        # operator trims through the week
        op_d["lump_jig_cut_sg"] = float(np.clip(op.lump_jig_cut_sg + 0.12 * math.sin(week * 4)
                                                + rng.normal(0, 0.02), 3.2, 4.85))
        op_d["scrubber_speed_pct_critical"] = float(np.clip(
            op.scrubber_speed_pct_critical + 2.0 * math.sin(week * 3 + 0.9) + rng.normal(0, 0.4), 20.0, 41.0))
        op_d["whims_field_tesla"] = float(np.clip(op.whims_field_tesla + 0.06 * math.sin(week * 5)
                                                  + rng.normal(0, 0.012), 0.5, 1.55))
        # scripted process faults act on the *actual* plant, not on the set-point
        if "hutch_pump_fault" in active:
            op_d["lump_jig_hutch_water_m3_h"] *= 0.58
        if "jig_screen_blind" in active:
            op_d["lump_jig_bed_depth_mm"] *= 0.80
        if "spiral_choke" in active:
            op_d["spiral_feed_solids_pct"] = float(np.clip(op_d["spiral_feed_solids_pct"] * 1.22, 16.0, 42.0))
        if "whims_matrix_blind" in active:
            op_d["whims_wash_water_m3_h"] *= 0.62
        return {"ore": ore_d, "operating": op_d, "events": _active(h),
                "timestamp": (self.anchor + timedelta(hours=h)).isoformat(timespec="seconds")}

    # ---- views ---------------------------------------------------------------------------------
    def truth(self, plant_id: str, hour: float) -> dict:
        key = (plant_id, round(hour % REPLAY_HOURS, 3))
        if key in self._truth:
            return self._truth[key]
        ps = get_plant_service()
        fs, _, _, ec = ps.configs(plant_id)
        d = self.drivers(plant_id, hour)
        ore = OreConfig(**d["ore"])
        op_d = dict(d["operating"])
        fs_d = fs.model_dump()
        for e in d["events"]:                      # process events perturb the real plant
            if e["key"] == "hpgr_stud_wear":
                fs_d["hpgr"]["m_dot_ts_hm3"] *= 0.88
            elif e["key"] == "cyclone_roping":
                op_d["mill_discharge_solids_pct"] = min(op_d["mill_discharge_solids_pct"] + 9.0, 78.0)
                op_d["cyclone_pressure_kpa"] = min(op_d["cyclone_pressure_kpa"] * 1.18, 260.0)
            elif e["key"] == "amine_pump_fault":
                op_d["amine_collector_g_t"] *= 0.55
            elif e["key"] == "floc_pump_trip":
                op_d["conc_thickener_flocculant_g_t"] = 0.0
        from app.models.domain import FlowsheetConfig
        res = solve(FlowsheetConfig(**fs_d), ore, OperatingConfig(**op_d), ec)
        out = {"plant_id": plant_id, "hour": key[1], "timestamp": d["timestamp"], "kpis": res["kpis"],
               "units": res["units"], "water": res["water"], "economics": res["economics"],
               "power": res["power"], "mvs": op_d, "ore": d["ore"], "events": d["events"]}
        self._truth.put(key, out)
        return out

    def model(self, plant_id: str, hour: float) -> dict:
        """The on-line twin's own view: setpoints as entered, ore from lagged estimates, no events."""
        key = (plant_id, round(hour % REPLAY_HOURS, 3))
        if key in self._model:
            return self._model[key]
        ps = get_plant_service()
        fs, _, _, ec = ps.configs(plant_id)
        d = self.drivers(plant_id, hour)
        d_lag = self.drivers(plant_id, (hour - 2) % REPLAY_HOURS)
        ore = OreConfig(**d_lag["ore"])            # the model only knows the last assay
        res = solve(fs, ore, OperatingConfig(**d["operating"]), ec)
        out = {"plant_id": plant_id, "hour": key[1], "timestamp": d["timestamp"], "kpis": res["kpis"],
               "units": res["units"], "water": res["water"], "economics": res["economics"],
               "power": res["power"], "mvs": d["operating"], "ore": d_lag["ore"]}
        self._model.put(key, out)
        return out

    # ---- tag values ----------------------------------------------------------------------------
    def tag_value(self, plant_id: str, tag: str, hour: float, view: str = "measurement") -> float | None:
        spec = next((t for t in TAGS if t["tag"] == tag), None)
        if spec is None:
            return None
        src = self.truth(plant_id, hour) if view != "model" else self.model(plant_id, hour)
        value = self._resolve(src, spec["path"])
        if value is None:
            return None
        if view == "truth" or view == "model":
            return float(value)
        rng = np.random.default_rng(abs(hash((plant_id, tag, round(hour, 3)))) % (2 ** 31))
        v = float(value) * (1.0 + rng.normal(0.0, spec["noise_pct"] / 100.0))
        for e in _active(hour):                     # sensor faults act on the measurement only
            if e["key"] == "analyser_drift" and tag == "302_AIC_025":
                prog = (hour % REPLAY_HOURS - e["start_h"]) / max(e["end_h"] - e["start_h"], 1)
                v *= 1.0 - 0.26 * prog            # the alumina channel reads progressively low
            if e["key"] == "density_flatline" and tag == "401_DI_032":
                v = float(self._resolve(self.truth(plant_id, e["start_h"]), spec["path"]) or v)
            if e["key"] == "whims_matrix_blind" and tag == "801_DI_073":
                v *= 1.12
        return round(v, 4)

    def series(self, plant_id: str, tags: list[str], start_h: float = 0.0, end_h: float = REPLAY_HOURS,
               step_h: float = 1.0, view: str = "measurement") -> dict:
        hours = np.arange(start_h, min(end_h, start_h + REPLAY_HOURS), max(step_h, 0.25))
        out: dict[str, list] = {"timestamps": [], "hours": [round(float(h), 3) for h in hours]}
        for h in hours:
            out["timestamps"].append((self.anchor + timedelta(hours=float(h % REPLAY_HOURS))).isoformat(timespec="seconds"))
        for tag in tags:
            out[tag] = [self.tag_value(plant_id, tag, float(h), view) for h in hours]
        return out

    def kpi_series(self, plant_id: str, keys: list[str], start_h: float = 0.0, end_h: float = REPLAY_HOURS,
                   step_h: float = 1.0, view: str = "truth") -> dict:
        hours = np.arange(start_h, min(end_h, start_h + REPLAY_HOURS), max(step_h, 0.25))
        snap = self.truth if view == "truth" else self.model
        out: dict[str, list] = {"hours": [round(float(h), 3) for h in hours], "timestamps": []}
        for k in keys:
            out[k] = []
        for h in hours:
            s = snap(plant_id, float(h))
            out["timestamps"].append(s["timestamp"])
            for k in keys:
                out[k].append(s["kpis"].get(k))
        return out

    def events(self) -> list[dict]:
        return [{**e, "window_h": [e["start_h"], e["end_h"]]} for e in EVENTS]

    @staticmethod
    def _resolve(snapshot: dict, path: str):  # noqa: ANN205
        node = snapshot
        for part in path.split("."):
            if part == "operating":
                node = snapshot.get("mvs", {})
                continue
            if part == "ore":
                node = snapshot.get("ore", {})
                continue
            if isinstance(node, dict):
                node = node.get(part)
            else:
                return None
        return node


@lru_cache(maxsize=1)
def get_historian() -> HistorianService:
    return HistorianService()
