"""Domain of validity for the data-driven part of the hybrid model.

The single most important safety property of a hybrid twin is knowing when the learned part
should not be trusted. A gradient-boosted model asked about an operating point outside its
training data does not refuse — it returns the nearest leaf, confidently and wrongly. The
mechanistic model, by contrast, degrades gracefully because it is solving the physics.

So the hybrid gates the correction on a measured distance from the training distribution.
Inside the envelope the correction is applied in full; at the edge it is tapered; well
outside it is switched off and the twin answers alone. That is the behaviour a plant needs
and the behaviour an acceptance test can demonstrate.
"""
from __future__ import annotations

from typing import Any

import numpy as np


class DomainOfValidity:
    """Three independent checks, combined into one confidence in [0, 1].

    1. **Box check** — is each feature inside the range the model was trained on?
    2. **Mahalanobis distance** — is the *combination* of features plausible? A feed rate and a
       cut density can each be ordinary while the pair has never been run together.
    3. **Local density** — how far is the nearest training point? This catches holes inside the
       convex hull, which the first two checks miss entirely.
    """

    def __init__(self, *, taper_from: float = 0.80, cutoff: float = 1.60) -> None:
        self.taper_from = float(taper_from)
        self.cutoff = float(cutoff)
        self.names: list[str] = []
        self.lo = self.hi = self.mu = self.inv = None
        self.chi_ref = 1.0
        self.nn_ref = 1.0
        self._X = None

    def fit(self, X: np.ndarray, feature_names: list[str]) -> "DomainOfValidity":
        X = np.asarray(X, dtype=float)
        self.names = list(feature_names)
        self.lo, self.hi = X.min(axis=0), X.max(axis=0)
        self.mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd[sd < 1e-12] = 1.0
        self._sd = sd
        Z = (X - self.mu) / sd
        cov = np.cov(Z, rowvar=False) + 1e-6 * np.eye(Z.shape[1])
        self.inv = np.linalg.pinv(cov)
        d = np.sqrt(np.einsum("ij,jk,ik->i", Z, self.inv, Z))
        self.chi_ref = float(np.percentile(d, 95)) or 1.0
        # reference nearest-neighbour spacing, on the standardised scale
        idx = np.random.default_rng(0).choice(len(Z), size=min(len(Z), 400), replace=False)
        S = Z[idx]
        D = np.linalg.norm(S[:, None, :] - S[None, :, :], axis=-1)
        np.fill_diagonal(D, np.inf)
        self.nn_ref = float(np.percentile(D.min(axis=1), 95)) or 1.0
        self._X = Z
        return self

    def score(self, x: dict[str, float] | np.ndarray) -> dict[str, Any]:
        v = (np.array([float(x[f]) for f in self.names]) if isinstance(x, dict)
             else np.asarray(x, dtype=float).ravel())
        span = np.where((self.hi - self.lo) < 1e-12, 1.0, self.hi - self.lo)
        below, above = (self.lo - v) / span, (v - self.hi) / span
        excess = np.maximum(np.maximum(below, above), 0.0)
        offenders = [{"feature": self.names[i], "value": round(float(v[i]), 4),
                      "trained_lo": round(float(self.lo[i]), 4), "trained_hi": round(float(self.hi[i]), 4),
                      "outside_by_pct_of_range": round(100 * float(excess[i]), 2)}
                     for i in np.argsort(-excess) if excess[i] > 1e-9][:6]

        z = (v - self.mu) / self._sd
        maha = float(np.sqrt(z @ self.inv @ z))
        maha_ratio = maha / max(self.chi_ref, 1e-9)
        nn = float(np.linalg.norm(self._X - z, axis=1).min())
        nn_ratio = nn / max(self.nn_ref, 1e-9)
        box_ratio = 1.0 + float(excess.max()) * 4.0 if offenders else 0.0

        # the binding constraint decides; a point is only as trustworthy as its worst check
        worst = max(maha_ratio, nn_ratio, box_ratio)
        if worst <= self.taper_from:
            conf, verdict = 1.0, "inside"
        elif worst >= self.cutoff:
            conf, verdict = 0.0, "outside"
        else:
            conf = (self.cutoff - worst) / max(self.cutoff - self.taper_from, 1e-9)
            verdict = "edge"
        driver = max((("box", box_ratio), ("combination", maha_ratio), ("sparse_region", nn_ratio)),
                     key=lambda t: t[1])[0]
        return {
            "verdict": verdict, "confidence": round(float(conf), 4),
            "in_box": not offenders,
            "mahalanobis": round(maha, 3), "mahalanobis_ratio": round(maha_ratio, 3),
            "nearest_neighbour": round(nn, 3), "nearest_neighbour_ratio": round(nn_ratio, 3),
            "box_ratio": round(box_ratio, 3),
            "binding_check": driver if verdict != "inside" else None,
            "features_outside": offenders,
            "thresholds": {"taper_from": self.taper_from, "cutoff": self.cutoff},
        }

    def envelope(self) -> list[dict[str, Any]]:
        return [{"feature": n, "lo": round(float(self.lo[i]), 4), "hi": round(float(self.hi[i]), 4),
                 "mean": round(float(self.mu[i]), 4)} for i, n in enumerate(self.names)]
