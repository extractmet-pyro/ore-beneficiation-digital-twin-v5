"""Machine-learning models: soft sensors, hybrid twin correction and quality prediction.

Every model is trained, cross-validated and scored here, and reports the diagnostics an
engineer needs before trusting it: hold-out R2/RMSE/MAE, k-fold spread, permutation importance,
residual distribution and a prediction interval from the residual sigma.

The **hybrid** model is the important one for a digital twin: the first-principles twin supplies
the prediction, and a gradient-boosted model learns the *residual* between the twin and the plant.
That keeps the physics in charge of extrapolation while the data corrects for what the physics
does not know (ore variability, wear, reagent quality).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ALGORITHMS = {
    "gradient_boosting": lambda **kw: GradientBoostingRegressor(random_state=0, n_estimators=kw.get("n_estimators", 220),
                                                                max_depth=kw.get("max_depth", 3),
                                                                learning_rate=kw.get("learning_rate", 0.06)),
    "random_forest": lambda **kw: RandomForestRegressor(random_state=0, n_estimators=kw.get("n_estimators", 250),
                                                        min_samples_leaf=kw.get("min_samples_leaf", 2), n_jobs=-1),
    "ridge": lambda **kw: Pipeline([("scale", StandardScaler()),
                                    ("model", RidgeCV(alphas=np.logspace(-3, 3, 25)))]),
}


@dataclass
class TrainedModel:
    key: str
    target: str
    algorithm: str
    feature_names: list[str]
    estimator: object
    metrics: dict
    importance: list[dict]
    residual_sigma: float
    trained_utc: str
    n_train: int
    n_test: int
    hybrid: bool = False
    version: str = "1"
    notes: str = ""

    def predict(self, x: dict[str, float] | np.ndarray, twin_value: float | None = None) -> dict:
        arr = (np.array([[x[f] for f in self.feature_names]], dtype=float)
               if isinstance(x, dict) else np.atleast_2d(np.asarray(x, dtype=float)))
        raw = float(self.estimator.predict(arr)[0])
        value = raw + (twin_value or 0.0) if self.hybrid else raw
        return {"value": round(value, 4), "model": self.key, "target": self.target,
                "algorithm": self.algorithm, "hybrid": self.hybrid,
                "residual_correction": round(raw, 4) if self.hybrid else None,
                "twin_value": twin_value,
                "interval_95": [round(value - 1.96 * self.residual_sigma, 4),
                                round(value + 1.96 * self.residual_sigma, 4)],
                "sigma": round(self.residual_sigma, 4)}

    def as_dict(self) -> dict:
        return {"key": self.key, "target": self.target, "algorithm": self.algorithm, "hybrid": self.hybrid,
                "metrics": self.metrics, "importance": self.importance, "residual_sigma": self.residual_sigma,
                "trained_utc": self.trained_utc, "n_train": self.n_train, "n_test": self.n_test,
                "feature_names": self.feature_names, "version": self.version, "notes": self.notes}


def train_model(dataset: dict, target: str, *, algorithm: str = "gradient_boosting", test_size: float = 0.25,
                cv_folds: int = 5, hybrid_baseline: np.ndarray | None = None, seed: int = 0,
                **hyper) -> TrainedModel:
    """Train one supervised model with hold-out and k-fold diagnostics."""
    t0 = time.perf_counter()
    names = dataset["feature_names"]
    X = np.asarray(dataset["X"], dtype=float)
    y = np.asarray(dataset["Y"], dtype=float)[:, dataset["target_names"].index(target)]
    if hybrid_baseline is not None:
        y = y - np.asarray(hybrid_baseline, dtype=float)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=seed)
    est = ALGORITHMS[algorithm](**hyper)
    est.fit(X_tr, y_tr)
    pred_te = est.predict(X_te)
    pred_tr = est.predict(X_tr)
    kf = KFold(n_splits=min(cv_folds, max(2, len(X) // 12)), shuffle=True, random_state=seed)
    cv_scores = []
    for tr, te in kf.split(X):
        e = ALGORITHMS[algorithm](**hyper)
        e.fit(X[tr], y[tr])
        cv_scores.append(r2_score(y[te], e.predict(X[te])))
    resid = y_te - pred_te
    try:
        imp = permutation_importance(est, X_te, y_te, n_repeats=8, random_state=seed)
        importance = sorted(({"feature": names[i], "importance": round(float(imp.importances_mean[i]), 5),
                              "std": round(float(imp.importances_std[i]), 5)} for i in range(len(names))),
                            key=lambda d: -d["importance"])
    except Exception:  # pragma: no cover
        importance = []
    metrics = {
        "r2_test": round(float(r2_score(y_te, pred_te)), 4),
        "r2_train": round(float(r2_score(y_tr, pred_tr)), 4),
        "rmse_test": round(float(np.sqrt(mean_squared_error(y_te, pred_te))), 4),
        "mae_test": round(float(mean_absolute_error(y_te, pred_te)), 4),
        "cv_r2_mean": round(float(np.mean(cv_scores)), 4),
        "cv_r2_std": round(float(np.std(cv_scores)), 4),
        "cv_folds": len(cv_scores),
        "bias": round(float(np.mean(resid)), 5),
        "train_seconds": round(time.perf_counter() - t0, 3),
        "target_std": round(float(np.std(y)), 4),
    }
    from datetime import datetime, timezone
    return TrainedModel(
        key=f"{target}:{algorithm}{':hybrid' if hybrid_baseline is not None else ''}", target=target,
        algorithm=algorithm, feature_names=names, estimator=est, metrics=metrics, importance=importance[:12],
        residual_sigma=float(np.std(resid)), trained_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        n_train=len(X_tr), n_test=len(X_te), hybrid=hybrid_baseline is not None,
        notes=("Residual model on top of the first-principles twin." if hybrid_baseline is not None
               else "Direct data-driven model."))


def learning_curve(dataset: dict, target: str, *, algorithm: str = "gradient_boosting",
                   fractions: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8, 1.0), seed: int = 0) -> list[dict]:
    """How much data does this soft sensor actually need?"""
    X = np.asarray(dataset["X"], dtype=float)
    y = np.asarray(dataset["Y"], dtype=float)[:, dataset["target_names"].index(target)]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=seed)
    out = []
    for f in fractions:
        n = max(int(len(X_tr) * f), 12)
        est = ALGORITHMS[algorithm]()
        est.fit(X_tr[:n], y_tr[:n])
        out.append({"fraction": f, "n_train": n,
                    "r2_test": round(float(r2_score(y_te, est.predict(X_te))), 4),
                    "rmse_test": round(float(np.sqrt(mean_squared_error(y_te, est.predict(X_te)))), 4)})
    return out


def partial_dependence(model: TrainedModel, dataset: dict, feature: str, points: int = 18) -> dict:
    """1-D partial dependence of a trained model on one feature (with the rest held at the median)."""
    names = model.feature_names
    X = np.asarray(dataset["X"], dtype=float)
    j = names.index(feature)
    grid = np.linspace(np.percentile(X[:, j], 2), np.percentile(X[:, j], 98), points)
    base = np.median(X, axis=0)
    xs = np.tile(base, (points, 1))
    xs[:, j] = grid
    ys = model.estimator.predict(xs)
    return {"feature": feature, "target": model.target, "x": [round(float(v), 4) for v in grid],
            "y": [round(float(v), 4) for v in ys]}
