"""Hybrid model service — mechanistic + data-driven, exposed to the desk and the API."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.hybrid.builder import HYBRID_TARGETS, UNMODELLED_EFFECT, get_builder
from app.hybrid.composition import DEFAULT_MODE, MODES
from app.ml.dataset import FEATURES
from app.services.historian_service import get_historian
from app.services.live_service import current_hour
from app.services.simulation_service import get_simulation_service


def _features(snap: dict) -> dict[str, float]:
    out = {}
    for f in FEATURES:
        if f in snap.get("mvs", {}):
            out[f] = float(snap["mvs"][f])
        elif f in snap.get("ore", {}):
            out[f] = float(snap["ore"][f])
    return out


class HybridService:
    # ---- description -----------------------------------------------------------------------
    def config(self, target: str = "lump_al2o3_pct") -> dict[str, Any]:
        built = get_builder().build(target)
        cfg = built["model"].config()
        cfg.update({"targets": HYBRID_TARGETS, "default_mode": DEFAULT_MODE,
                    "unmodelled_effect": UNMODELLED_EFFECT,
                    "architecture": {
                        "mechanistic": "Size-by-liberation population balance solved across the "
                                       "whole circuit, including recycles.",
                        "data_driven": "Gradient-boosted model trained on the residual between "
                                       "the mechanistic prediction and the reconciled plant "
                                       "measurement.",
                        "composition": "Gated residual: correction bounded in magnitude and "
                                       "tapered to zero outside the learned domain.",
                        "training_source": "Twin design of experiments for bootstrap; reconciled "
                                           "historian for re-training once the plant is running.",
                        "retraining_trigger": "Population-stability index on features or residuals, "
                                              "not a calendar.",
                    }})
        return cfg

    def modes(self) -> dict[str, Any]:
        return {"modes": MODES, "default": DEFAULT_MODE, "targets": HYBRID_TARGETS}

    # ---- inference -------------------------------------------------------------------------
    def predict(self, plant_id: str, target: str = "lump_al2o3_pct", *, hour: float | None = None,
                mode: str | None = None, features: dict[str, float] | None = None,
                mechanistic: float | None = None) -> dict[str, Any]:
        built = get_builder().build(target)
        h = current_hour() if hour is None else float(hour)
        snap = get_historian().truth(plant_id, h)
        feats = {**_features(snap), **(features or {})}
        missing = [f for f in built["model"].domain.names if f not in feats]
        if missing:
            ds = get_builder().dataset()
            mu = np.asarray(ds["X"], dtype=float).mean(axis=0)
            for f in missing:
                feats[f] = float(mu[ds["feature_names"].index(f)])
        if mechanistic is None:
            sim = get_simulation_service().run_plant(plant_id, include_streams=False)
            mechanistic = float(sim["kpis"].get(target, snap["kpis"].get(target, 0.0)))
        out = built["model"].predict(feats, float(mechanistic), mode=mode)
        actual = snap["kpis"].get(target)
        if actual is not None:
            out["plant_measurement"] = round(float(actual), 4)
            out["mechanistic_error"] = round(float(mechanistic) - float(actual), 4)
            out["hybrid_error"] = round(out["value"] - float(actual), 4)
            out["error_reduction_pct"] = (
                None if abs(out["mechanistic_error"]) < 1e-9 else
                round(100 * (1 - abs(out["hybrid_error"]) / abs(out["mechanistic_error"])), 1))
        out["plant_id"] = plant_id
        out["hour"] = round(h, 3)
        out["defaulted_features"] = missing
        return out

    def attribution(self, plant_id: str, target: str = "lump_al2o3_pct",
                    hour: float | None = None) -> dict[str, Any]:
        """Every mode side by side at the current operating point, with the split shown."""
        rows = []
        for m in ("mechanistic_only", "data_only", "parallel_residual", "gated_residual",
                  "ensemble_weighted"):
            try:
                p = self.predict(plant_id, target, hour=hour, mode=m)
            except ValueError as exc:  # a mode with no model configured
                rows.append({"mode": m, "error": str(exc)})
                continue
            rows.append({"mode": m, "value": p["value"], "attribution": p.get("attribution"),
                         "gate": p.get("gate"), "error": p.get("hybrid_error"),
                         "note": p.get("note")})
        base = self.predict(plant_id, target, hour=hour)
        return {"plant_id": plant_id, "target": target, "hour": base["hour"],
                "in_service_mode": base["mode"], "rows": rows,
                "domain": base["domain"], "plant_measurement": base.get("plant_measurement"),
                "modes": MODES}

    # ---- evidence --------------------------------------------------------------------------
    def domain_check(self, plant_id: str, target: str = "lump_al2o3_pct",
                     hour: float | None = None) -> dict[str, Any]:
        built = get_builder().build(target)
        h = current_hour() if hour is None else float(hour)
        snap = get_historian().truth(plant_id, h)
        feats = _features(snap)
        ds = get_builder().dataset()
        mu = np.asarray(ds["X"], dtype=float).mean(axis=0)
        for f in built["model"].domain.names:
            feats.setdefault(f, float(mu[ds["feature_names"].index(f)]))
        return {"plant_id": plant_id, "target": target, "hour": round(h, 3),
                "domain": built["model"].domain.score(feats),
                "envelope": built["model"].domain.envelope(),
                "features": {k: round(v, 4) for k, v in feats.items()}}

    def compare(self, target: str = "lump_al2o3_pct", n_test: int = 120) -> dict[str, Any]:
        return get_builder().compare(target, n_test=n_test)

    def extrapolation(self, target: str = "lump_al2o3_pct", steps: int = 9) -> dict[str, Any]:
        return get_builder().extrapolation_test(target, steps=steps)


_service: HybridService | None = None


def get_hybrid_service() -> HybridService:
    global _service
    if _service is None:
        _service = HybridService()
    return _service
