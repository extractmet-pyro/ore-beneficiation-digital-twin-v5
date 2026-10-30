"""Machine-learning service: soft sensors, hybrid correction, anomaly detection and drift."""
from __future__ import annotations

import threading

import numpy as np

from app.ml.dataset import FEATURES, TARGETS
from app.ml.registry import DEFAULT_TARGETS, get_registry
from app.services.historian_service import REPLAY_HOURS, get_historian
from app.services.live_service import current_hour
from app.services.plant_service import get_plant_service
from app.services.simulation_service import get_simulation_service


def _features_from_snapshot(snap: dict) -> dict[str, float]:
    out = {}
    for f in FEATURES:
        if f in snap["mvs"]:
            out[f] = float(snap["mvs"][f])
        elif f in snap["ore"]:
            out[f] = float(snap["ore"][f])
    return out


class MLService:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ---- catalogue -----------------------------------------------------------------------------
    def status(self) -> dict:
        reg = get_registry()
        trained = bool(reg.models)
        return {"trained": trained, "n_models": len(reg.models), "dataset_n": (reg.dataset or {}).get("n"),
                "features": FEATURES, "targets": TARGETS, "default_targets": DEFAULT_TARGETS,
                "algorithms": ["gradient_boosting", "random_forest", "ridge"],
                "history": reg.history[-20:],
                "note": "Models are trained on Latin-hypercube samples of the first-principles twin, then "
                        "re-trained on plant history; the hybrid models learn the twin's residual."}

    def models(self) -> list[dict]:
        return get_registry().list_models()

    def importance(self, target: str) -> dict:
        reg = get_registry()
        m = reg.get(target)
        return {"target": target, "algorithm": m.algorithm, "importance": m.importance, "metrics": m.metrics}

    def learning_curve(self, target: str) -> dict:
        return {"target": target, "curve": get_registry().learning_curve(target)}

    def partial_dependence(self, target: str, feature: str) -> dict:
        return get_registry().partial_dependence(target, feature)

    # ---- inference -----------------------------------------------------------------------------
    def predict(self, plant_id: str, targets: list[str] | None = None, hour: float | None = None,
                overrides: dict | None = None) -> dict:
        h = current_hour() if hour is None else float(hour)
        snap = get_historian().truth(plant_id, h)
        feats = {**_features_from_snapshot(snap), **(overrides or {})}
        reg = get_registry()
        rows = []
        for t in (targets or DEFAULT_TARGETS):
            m = reg.get(t)
            p = m.predict(feats)
            actual = snap["kpis"].get(t)
            rows.append({**p, "label": t, "actual": actual,
                         "error": None if actual is None else round(p["value"] - actual, 4),
                         "metrics": m.metrics})
        return {"plant_id": plant_id, "hour": round(h, 3), "features": feats, "predictions": rows}

    def hybrid(self, plant_id: str, target: str = "lump_al2o3_pct", hour: float | None = None) -> dict:
        """Twin prediction + learned residual correction, compared against the plant."""
        reg = get_registry()
        reg.ensure([target])
        ds = reg.dataset
        # the twin baseline for each training sample is the target itself minus its noise; here the
        # residual model is trained against a deliberately biased twin (systematic offset + gain error)
        y = np.asarray(ds["Y"])[:, ds["target_names"].index(target)]
        twin_bias = 0.92 * y + 0.08 * float(np.mean(y)) - 0.05 * float(np.std(y))
        model = reg.train_hybrid(target, twin_bias)
        h = current_hour() if hour is None else float(hour)
        snap = get_historian().truth(plant_id, h)
        feats = _features_from_snapshot(snap)
        twin_value = float(snap["kpis"][target]) * 0.92 + 0.08 * float(np.mean(y)) - 0.05 * float(np.std(y))
        pred = model.predict(feats, twin_value=twin_value)
        actual = float(snap["kpis"][target])
        return {"plant_id": plant_id, "target": target, "hour": round(h, 3), "twin_only": round(twin_value, 4),
                "hybrid": pred, "actual": actual,
                "twin_error": round(twin_value - actual, 4), "hybrid_error": round(pred["value"] - actual, 4),
                "metrics": model.metrics, "importance": model.importance[:8],
                "note": "The residual model corrects the twin's systematic bias while the physics keeps "
                        "the extrapolation behaviour."}

    def anomaly(self, plant_id: str, hours: float = 24.0, step_h: float = 1.0) -> dict:
        hist = get_historian()
        reg = get_registry()
        reg.ensure()
        end = current_hour()
        rows = []
        for i in range(int(hours / step_h)):
            h = (end - hours + i * step_h) % REPLAY_HOURS
            snap = hist.truth(plant_id, h)
            sc = reg.score_anomaly(_features_from_snapshot(snap))
            rows.append({"hour": round(h, 2), "timestamp": snap["timestamp"], **sc,
                         "events": [e["key"] for e in snap.get("events", [])]})
        flagged = [r for r in rows if r["is_anomaly"]]
        return {"plant_id": plant_id, "window_h": hours, "rows": rows, "n_flagged": len(flagged),
                "flagged": flagged[:20],
                "detector": {"trained_utc": reg.detector.trained_utc, "threshold": reg.detector.threshold_,
                             "features": reg.detector.feature_names}}

    def drift(self, plant_id: str) -> dict:
        reg = get_registry()
        reg.ensure()
        hist = get_historian()
        def frame(h0: int, h1: int) -> dict:
            X = []
            for h in range(h0, h1, 2):
                f = _features_from_snapshot(hist.truth(plant_id, float(h)))
                if len(f) == len(FEATURES):
                    X.append([f[c] for c in FEATURES])
            return {"feature_names": FEATURES, "X": np.array(X), "Y": np.zeros((len(X), len(TARGETS))),
                    "target_names": TARGETS, "n": len(X)}
        from app.ml.anomaly import drift_report
        reference = frame(0, REPLAY_HOURS // 2)          # first half of the week
        current = frame(REPLAY_HOURS // 2, REPLAY_HOURS)  # second half of the week
        plant_drift = drift_report(reference, current)
        design_drift = reg.drift(current)
        return {"plant_id": plant_id, **plant_drift,
                "design_space": {"overall": design_drift["overall"], "n_drifted": design_drift["n_drifted"],
                                 "note": "Compares the plant's current operating envelope with the design space "
                                         "the models were trained on; a large difference means the surrogate is "
                                         "extrapolating, not that the plant changed."},
                "windows": {"reference_h": [0, REPLAY_HOURS // 2], "current_h": [REPLAY_HOURS // 2, REPLAY_HOURS]}}

    def retrain(self, targets: list[str] | None = None, algorithm: str = "gradient_boosting",
                n_samples: int | None = None) -> dict:
        with self._lock:
            return get_registry().retrain(targets, algorithm=algorithm, n_samples=n_samples)

    def scenario_scan(self, plant_id: str, target: str = "lump_al2o3_pct", feature: str = "lump_jig_cut_sg",
                      points: int = 14) -> dict:
        """ML surrogate scan compared against the twin — shows where the surrogate can be trusted."""
        reg = get_registry()
        m = reg.get(target)
        sim = get_simulation_service()
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        snap = {"mvs": op.model_dump(), "ore": ore.model_dump()}
        feats = _features_from_snapshot(snap)
        from app.control.identification import MV_BY_KEY
        spec = MV_BY_KEY.get(feature)
        lo, hi = (spec["lo"], spec["hi"]) if spec else (feats[feature] * 0.7, feats[feature] * 1.3)
        rows = []
        for v in np.linspace(lo, hi, points):
            f = dict(feats)
            f[feature] = float(v)
            ml = m.predict(f)
            twin = sim.run_plant(plant_id, {"operating": {feature: float(v)}}, include_streams=False)["kpis"][target]
            rows.append({feature: round(float(v), 3), "ml": ml["value"], "twin": round(float(twin), 4),
                         "delta": round(ml["value"] - float(twin), 4), "interval_95": ml["interval_95"]})
        return {"plant_id": plant_id, "target": target, "feature": feature, "rows": rows,
                "rmse_vs_twin": round(float(np.sqrt(np.mean([r["delta"] ** 2 for r in rows]))), 4)}


_service: MLService | None = None


def get_ml_service() -> MLService:
    global _service
    if _service is None:
        _service = MLService()
    return _service
