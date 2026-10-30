"""Unsupervised condition monitoring: anomaly detection and data drift."""
from __future__ import annotations

import numpy as np
from sklearn.covariance import EmpiricalCovariance
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class AnomalyDetector:
    """Isolation forest on the operating envelope plus a Mahalanobis distance for attribution.

    The forest gives a robust anomaly score for the whole operating point; the Mahalanobis
    decomposition tells the operator *which* tags are responsible, which is what makes the alarm
    actionable rather than a black box.
    """

    def __init__(self, contamination: float = 0.04, seed: int = 0):
        self.scaler = StandardScaler()
        self.forest = IsolationForest(contamination=contamination, random_state=seed, n_estimators=220)
        self.cov = EmpiricalCovariance()
        self.feature_names: list[str] = []
        self.threshold_: float = 0.0
        self.trained_utc: str = ""

    def fit(self, X: np.ndarray, feature_names: list[str]) -> "AnomalyDetector":
        from datetime import datetime, timezone
        self.feature_names = list(feature_names)
        Z = self.scaler.fit_transform(np.asarray(X, dtype=float))
        self.forest.fit(Z)
        self.cov.fit(Z)
        scores = -self.forest.score_samples(Z)
        self.threshold_ = float(np.percentile(scores, 96))
        self.trained_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return self

    def score(self, x: dict[str, float] | np.ndarray) -> dict:
        arr = (np.array([[x[f] for f in self.feature_names]], dtype=float)
               if isinstance(x, dict) else np.atleast_2d(np.asarray(x, dtype=float)))
        z = self.scaler.transform(arr)
        score = float(-self.forest.score_samples(z)[0])
        maha = float(self.cov.mahalanobis(z)[0])
        contrib = (z[0] ** 2)
        total = max(contrib.sum(), 1e-9)
        drivers = sorted(({"feature": self.feature_names[i], "z_score": round(float(z[0, i]), 3),
                           "contribution_pct": round(100 * float(contrib[i]) / total, 1)}
                          for i in range(len(self.feature_names))), key=lambda d: -d["contribution_pct"])
        return {"anomaly_score": round(score, 4), "threshold": round(self.threshold_, 4),
                "is_anomaly": bool(score > self.threshold_), "mahalanobis": round(maha, 3),
                "severity": ("high" if score > self.threshold_ * 1.25 else
                             "medium" if score > self.threshold_ else "normal"),
                "drivers": drivers[:6], "trained_utc": self.trained_utc}


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population stability index between two samples of one variable."""
    ref, cur = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    edges = np.unique(np.percentile(ref, np.linspace(0, 100, bins + 1)))
    if len(edges) < 3:
        return 0.0
    r, _ = np.histogram(ref, bins=edges)
    c, _ = np.histogram(cur, bins=edges)
    r = np.clip(r / max(r.sum(), 1), 1e-4, None)
    c = np.clip(c / max(c.sum(), 1), 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def drift_report(reference: dict, current: dict) -> dict:
    """Feature-by-feature drift between a reference window and the current window."""
    names = reference["feature_names"]
    R = np.asarray(reference["X"], dtype=float)
    C = np.asarray(current["X"], dtype=float)
    rows = []
    for i, n in enumerate(names):
        value = psi(R[:, i], C[:, i])
        status = "stable" if value < 0.1 else ("shifting" if value < 0.25 else "drifted")
        rows.append({"feature": n, "psi": round(value, 4), "status": status,
                     "reference_mean": round(float(R[:, i].mean()), 4),
                     "current_mean": round(float(C[:, i].mean()), 4),
                     "shift_pct": round(100 * (float(C[:, i].mean()) - float(R[:, i].mean()))
                                        / max(abs(float(R[:, i].mean())), 1e-9), 2)})
    drifted = [r for r in rows if r["status"] == "drifted"]
    return {"features": sorted(rows, key=lambda d: -d["psi"]), "n_drifted": len(drifted),
            "overall": "retrain recommended" if drifted else "model valid",
            "reference_n": len(R), "current_n": len(C)}
