"""Live plant state: current snapshot, trends, alarms and constraint status."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.services.historian_service import REPLAY_HOURS, get_historian
from app.services.plant_service import TAGS, get_plant_service
from app.twin.constraints import evaluate_all
from app.twin.soft_sensors import estimate as estimate_soft_sensors


def current_hour() -> float:
    """Map wall-clock time onto the 168 h replay."""
    now = datetime.now(timezone.utc)
    return float((now.timestamp() / 3600.0) % REPLAY_HOURS)


def whole_hour(h: float) -> float:
    """Snap an hour onto the replay's whole-hour grid.

    The replay is cached per (plant, hour) and pre-computed on whole hours. A sweep that starts
    at a fractional hour therefore misses on every single sample and rebuilds snapshots that
    already exist - the difference between a page that opens in 100 ms and one that takes ten
    seconds. Use this for any window sampled at an hour or coarser; sub-hourly tag trends
    genuinely need the intermediate points and should not use it.
    """
    return float(int(h) % REPLAY_HOURS)


class LiveService:
    """Live snapshot, KPI trends and instrument traces off the replay.

    Instrument traces are sampled every quarter hour on purpose - an operator reading a density
    loop wants to see it move - so they cannot be snapped to the whole-hour grid the replay
    cache is built on, and the first view of a window pays for the intermediate snapshots. The
    result is memoised on the replay hour, so every later view inside that hour is free.
    """

    def __init__(self) -> None:
        self._tag_trend: dict[tuple, dict] = {}

    def snapshot(self, plant_id: str, hour: float | None = None) -> dict:
        h = current_hour() if hour is None else float(hour)
        hist = get_historian()
        truth = hist.truth(plant_id, h)
        model = hist.model(plant_id, h)
        tags = []
        for t in TAGS:
            meas = hist.tag_value(plant_id, t["tag"], h, "measurement")
            mdl = hist.tag_value(plant_id, t["tag"], h, "model")
            resid = None if meas is None or mdl is None else round(meas - mdl, 4)
            resid_pct = None if resid is None or not mdl else round(100 * resid / mdl, 2)
            tags.append({**t, "value": meas, "model_value": mdl, "residual": resid, "residual_pct": resid_pct,
                         "quality": "bad" if meas is None else ("suspect" if resid_pct is not None
                                                                and abs(resid_pct) > 12 else "good")})
        cons = evaluate_all({"kpis": truth["kpis"], "units": truth["units"], "water": truth["water"]})
        alarms = [{"severity": "alarm" if c["status"] == "alarm" else "warning", "label": c["label"],
                   "value": c["value"], "limit": c["limit"], "unit": c["unit"], "priority": c["priority"],
                   "group": c["group"]} for c in cons if c["status"] in ("alarm", "caution")]
        for e in truth.get("events", []):
            alarms.append({"severity": "alarm" if e["severity"] == "high" else "warning",
                           "label": f"Event: {e['label']}", "value": None, "limit": None, "unit": "",
                           "priority": 1 if e["severity"] == "high" else 3, "group": e["type"]})
        return {"plant_id": plant_id, "hour": round(h, 3), "timestamp": truth["timestamp"],
                "kpis": truth["kpis"], "model_kpis": model["kpis"], "units": truth["units"],
                "water": truth["water"], "power": truth["power"], "economics": truth["economics"],
                "ore": truth["ore"], "setpoints": truth["mvs"], "tags": tags, "constraints": cons,
                "alarms": sorted(alarms, key=lambda a: a["priority"]),
                "events": truth.get("events", []), "soft_sensors": self.soft_sensors(plant_id, h)}

    def soft_sensors(self, plant_id: str, hour: float | None = None) -> list[dict]:
        """Soft-sensor estimates against the value the twin says is true.

        The estimate is what an operator would infer from the instruments that exist; the
        comparison column is what the twin computes from the full state. The gap between them is
        the honest measure of how much the plant is flying blind, and it is what the machine-learning
        layer is asked to close.
        """
        h = current_hour() if hour is None else float(hour)
        truth = get_historian().truth(plant_id, h)
        model = get_historian().model(plant_id, h)
        est = estimate_soft_sensors(model)
        rows = []
        for row in est:
            key = row["key"]
            actual = truth["kpis"].get(key)
            if actual is None:
                actual = {
                    "jig_cut_sg": truth["units"]["lump_jig"].get("cut_sg_achieved"),
                    "classifier_d50_um": truth["units"]["spiral_classifier"].get("d50_quartz_um"),
                    "spiral_feed_p80_um": truth["units"]["spiral_cyclone"].get("overflow_p80_um"),
                    "whims_feed_fe_pct": truth["units"]["whims"].get("feed_fe_pct"),
                    "slimes_fraction_pct": round(100.0 * truth["units"]["spiral_classifier"].get("overflow_tph", 0.0)
                                                 / max(truth["kpis"]["throughput_tph"], 1e-6), 3),
                }.get(key)
            err = None if (actual is None or row["value"] is None) else round(row["value"] - float(actual), 4)
            rows.append({**row, "measured": None if actual is None else round(float(actual), 4), "error": err})
        return rows

    def trend(self, plant_id: str, keys: list[str], hours: float = 24.0, step_h: float = 1.0,
              view: str = "truth") -> dict:
        end = current_hour()
        hist = get_historian()
        start = whole_hour(end - hours) if step_h >= 1.0 else (end - hours) % REPLAY_HOURS
        out = hist.kpi_series(plant_id, keys, start_h=start, end_h=start + hours,
                              step_h=step_h, view=view)
        for k in keys:
            vals = [v for v in out.get(k, []) if v is not None]
            if vals:
                out[f"{k}_stats"] = {"mean": round(float(np.mean(vals)), 3), "min": round(float(np.min(vals)), 3),
                                     "max": round(float(np.max(vals)), 3), "std": round(float(np.std(vals)), 3)}
        return {"plant_id": plant_id, "hours": hours, "view": view, **out}

    def tag_trend(self, plant_id: str, tags: list[str], hours: float = 24.0, step_h: float = 0.25,
                  view: str = "measurement") -> dict:
        end = current_hour()
        key = (plant_id, tuple(tags), float(hours), float(step_h), view, int(end))
        cached = self._tag_trend.get(key)
        if cached is not None:
            return cached
        start = whole_hour(end - hours)          # whole-hour anchor, sub-hourly samples within it
        out = {"plant_id": plant_id, "view": view,
               **get_historian().series(plant_id, tags, start_h=start, end_h=start + hours,
                                        step_h=step_h, view=view)}
        self._tag_trend = {key: out}             # one window per replay hour is all that is asked for
        return out


_service: LiveService | None = None


def get_live_service() -> LiveService:
    global _service
    if _service is None:
        _service = LiveService()
    return _service
