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


class LiveService:
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

    def trend(self, plant_id: str, keys: list[str], hours: float = 24.0, step_h: float = 0.5,
              view: str = "truth") -> dict:
        end = current_hour()
        start = end - hours
        hist = get_historian()
        out = hist.kpi_series(plant_id, keys, start_h=start % REPLAY_HOURS, end_h=start % REPLAY_HOURS + hours,
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
        start = (end - hours) % REPLAY_HOURS
        return {"plant_id": plant_id, "view": view,
                **get_historian().series(plant_id, tags, start_h=start, end_h=start + hours, step_h=step_h, view=view)}


_service: LiveService | None = None


def get_live_service() -> LiveService:
    global _service
    if _service is None:
        _service = LiveService()
    return _service
