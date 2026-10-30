"""Data quality: instrument health, coverage, noise, calibration drift and readiness gating."""
from __future__ import annotations

import numpy as np

from app.services.historian_service import REPLAY_HOURS, get_historian
from app.services.live_service import current_hour
from app.services.plant_service import TAGS, get_plant_service


class DataQualityService:
    def report(self, plant_id: str, hours: float = 24.0, step_h: float = 0.5) -> dict:
        hist = get_historian()
        end = current_hour()
        rows = []
        for spec in TAGS:
            vals, models = [], []
            for i in range(int(hours / step_h)):
                h = (end - hours + i * step_h) % REPLAY_HOURS
                vals.append(hist.tag_value(plant_id, spec["tag"], h, "measurement"))
                models.append(hist.tag_value(plant_id, spec["tag"], h, "model"))
            v = np.array([x for x in vals if x is not None], dtype=float)
            m = np.array([x for x in models if x is not None], dtype=float)
            coverage = 100.0 * len(v) / max(len(vals), 1)
            noise = float(np.std(np.diff(v)) / max(abs(np.mean(v)), 1e-9) * 100) if v.size > 3 else None
            frozen = bool(v.size > 6 and float(np.std(v)) < 1e-6)
            bias = (float(np.mean(v - m[:len(v)])) if v.size and m.size >= v.size else None)
            bias_pct = None if bias is None or not np.mean(m[:len(v)]) else round(100 * bias / float(np.mean(m[:len(v)])), 2)
            status = ("bad" if coverage < 90 or frozen else
                      "suspect" if (bias_pct is not None and abs(bias_pct) > 6) or (noise or 0) > 8 else "good")
            rows.append({"tag": spec["tag"], "label": spec["label"], "area": spec["area"], "type": spec["type"],
                         "unit": spec["unit"], "coverage_pct": round(coverage, 1),
                         "noise_pct": None if noise is None else round(noise, 2), "frozen": frozen,
                         "bias_pct": bias_pct, "sample_s": spec["sample_s"], "status": status,
                         "mean": round(float(np.mean(v)), 4) if v.size else None,
                         "std": round(float(np.std(v)), 4) if v.size else None})
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("good", "suspect", "bad")}
        score = 100.0 * (counts["good"] + 0.5 * counts["suspect"]) / max(len(rows), 1)
        return {"plant_id": plant_id, "window_h": hours, "tags": rows, "counts": counts,
                "quality_score_pct": round(score, 1),
                "gate": "closed-loop control permitted" if score > 85 and counts["bad"] == 0
                        else "advisory only — repair flagged instruments",
                "recommendations": [f"{r['label']} ({r['tag']}): " +
                                    ("frozen signal — check the analyser" if r["frozen"] else
                                     "calibration bias against the twin" if (r["bias_pct"] or 0) and abs(r["bias_pct"]) > 6
                                     else "noisy signal — check earthing and damping")
                                    for r in rows if r["status"] != "good"]}

    def tag_health(self, plant_id: str) -> dict[str, str]:
        rep = self.report(plant_id, hours=12.0, step_h=1.0)
        return {r["tag"]: r["status"] for r in rep["tags"]}

    def missing_data(self, plant_id: str, hours: float = 48.0) -> dict:
        hist = get_historian()
        end = current_hour()
        out = []
        for spec in TAGS:
            gaps = 0
            for i in range(int(hours)):
                h = (end - hours + i) % REPLAY_HOURS
                if hist.tag_value(plant_id, spec["tag"], h, "measurement") is None:
                    gaps += 1
            out.append({"tag": spec["tag"], "label": spec["label"], "gaps_h": gaps,
                        "availability_pct": round(100 * (1 - gaps / max(hours, 1)), 2)})
        return {"plant_id": plant_id, "hours": hours, "tags": out}


_service: DataQualityService | None = None


def get_data_quality_service() -> DataQualityService:
    global _service
    if _service is None:
        _service = DataQualityService()
    return _service
