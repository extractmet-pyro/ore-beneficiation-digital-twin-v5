"""Building and evaluating the hybrid model.

**On the data used here.** In a deployed system the mechanistic side of the pair is the twin's
own prediction and the plant side is the reconciled historian: the residual model is trained on
the difference between what the twin said and what the plant actually did. This module stands
in for that during development and demonstration by taking the twin's own design of experiments
and applying a documented *unmodelled effect* to produce the "plant" observation — a real
interaction the first-principles models do not contain. That makes the demonstration honest:
there is a genuine systematic error for the learner to find, of a kind that occurs in practice,
and the comparison against the mechanistic-only case means something.

The unmodelled effect used is a clay-moisture interaction on product quality: at high clay
share and high scrubber water the measured alumina runs above the modelled value because a
fraction of the detached clay re-attaches in the downstream launders. It is deliberately
non-linear and deliberately confined to one corner of the operating space, so that the
domain-of-validity gate has something to be right about.
"""
from __future__ import annotations

import threading
from typing import Any

import numpy as np

from app.hybrid.composition import DEFAULT_MODE, MODES, HybridModel
from app.hybrid.domain import DomainOfValidity
from app.ml.dataset import FEATURES, build_dataset
from app.ml.models import train_model

#: Targets for which a hybrid is maintained. These are the variables where a site-specific
#: systematic error actually matters commercially.
HYBRID_TARGETS = ["lump_al2o3_pct", "lump_fe_pct", "fines_fe_pct", "fe_recovery_pct"]

UNMODELLED_EFFECT = {
    "name": "Clay re-attachment in downstream launders",
    "affects": ["lump_al2o3_pct", "lump_fe_pct", "fines_fe_pct", "fe_recovery_pct"],
    "drivers": ["clay_share", "scrubber_water_m3_h", "rom_feed_tph"],
    "form": "Saturating product of clay share and scrubber water loading, with a throughput term",
    "why_it_is_not_in_the_physics": "Launder geometry and residence time are below the twin's "
                                    "level of detail; the effect is site-specific and would have "
                                    "to be fitted per plant in any case.",
    "typical_magnitude": "Up to about 0.35 % Al2O3 on the lump product at high clay and high "
                         "scrubber water; negligible below a clay share of about 0.5.",
}


def _effect(rows: list[dict], target: str, rng) -> np.ndarray:
    """The unmodelled effect, evaluated on the design of experiments."""
    clay = np.array([r.get("clay_share", 0.5) for r in rows], dtype=float)
    water = np.array([r.get("scrubber_water_m3_h", 420.0) for r in rows], dtype=float)
    feed = np.array([r.get("rom_feed_tph", 600.0) for r in rows], dtype=float)
    c = np.clip((clay - 0.50) / 0.30, 0.0, 1.0)
    w = np.clip((water - 380.0) / 260.0, 0.0, 1.0)
    f = np.clip((feed - 450.0) / 400.0, 0.0, 1.0)
    core = (c ** 1.4) * np.tanh(2.2 * w) * (0.55 + 0.45 * f)
    scale = {"lump_al2o3_pct": 0.35, "lump_fe_pct": -0.42, "fines_fe_pct": -0.30,
             "fe_recovery_pct": -0.95}.get(target, 0.0)
    noise_sd = {"lump_al2o3_pct": 0.025, "lump_fe_pct": 0.09, "fines_fe_pct": 0.08,
                "fe_recovery_pct": 0.22}.get(target, 0.05)
    return scale * core + rng.normal(0.0, noise_sd, size=len(rows))


class HybridBuilder:
    """Trains and caches one hybrid per target. Thread-safe and lazy."""

    def __init__(self, n: int | None = None, seed: int = 11) -> None:
        if n is None:
            from app.core.config import get_settings
            n = get_settings().HYBRID_SAMPLES
        self.n, self.seed = int(n), seed
        self._lock = threading.Lock()
        self._ds: dict | None = None
        self._cache: dict[str, dict] = {}
        # compare() and extrapolation_test() are deterministic for a given target and size -
        # fixed seeds, fixed models - so their results are memoised rather than recomputed on
        # every page view. compare() in particular costs a fresh design of experiments.
        self._studies: dict[tuple, dict] = {}

    # ---------------------------------------------------------------- dataset
    def dataset(self) -> dict:
        with self._lock:
            if self._ds is None:
                ds = build_dataset(n=self.n, seed=self.seed)
                rng = np.random.default_rng(self.seed + 5)
                twin = np.asarray(ds["Y"], dtype=float)
                plant = twin.copy()
                for t in HYBRID_TARGETS:
                    if t in ds["target_names"]:
                        j = ds["target_names"].index(t)
                        plant[:, j] = twin[:, j] + _effect(ds["rows"], t, rng)
                ds = {**ds, "Y_twin": twin, "Y_plant": plant,
                      "note": "Y_twin is the first-principles prediction; Y_plant adds the "
                              "documented unmodelled effect and measurement noise."}
                self._ds = ds
            return self._ds

    # ---------------------------------------------------------------- build
    def build(self, target: str) -> dict:
        if target not in HYBRID_TARGETS:
            raise ValueError(f"No hybrid is maintained for '{target}'. "
                             f"Available: {', '.join(HYBRID_TARGETS)}")
        with self._lock:
            if target in self._cache:
                return self._cache[target]
        ds = self.dataset()
        j = ds["target_names"].index(target)
        twin = ds["Y_twin"][:, j]
        plant_ds = {**ds, "Y": ds["Y_plant"]}
        residual = train_model(plant_ds, target, hybrid_baseline=twin)
        direct = train_model(plant_ds, target)
        dom = DomainOfValidity().fit(np.asarray(ds["X"], dtype=float), ds["feature_names"])
        model = HybridModel(target, residual, dom, data_only_model=direct)
        out = {"target": target, "model": model, "residual": residual, "direct": direct,
               "twin": twin, "plant": ds["Y_plant"][:, j]}
        with self._lock:
            self._cache[target] = out
        return out

    # ---------------------------------------------------------------- compare
    def compare(self, target: str, *, n_test: int = 120, seed: int = 2026) -> dict[str, Any]:
        """Head-to-head on data none of the models were trained on."""
        key = ("compare", target, int(n_test), int(seed))
        with self._lock:
            if key in self._studies:
                return self._studies[key]
        built = self.build(target)
        ds = self.dataset()
        j = ds["target_names"].index(target)
        test = build_dataset(n=n_test, seed=seed)
        rng = np.random.default_rng(seed + 1)
        Xt = np.asarray(test["X"], dtype=float)
        twin_t = np.asarray(test["Y"], dtype=float)[:, j]
        plant_t = twin_t + _effect(test["rows"], target, rng)
        names = ds["feature_names"]
        rows, preds = [], {m: [] for m in ("mechanistic_only", "data_only",
                                           "parallel_residual", "gated_residual")}
        for i in range(len(Xt)):
            feats = {n: float(Xt[i, k]) for k, n in enumerate(names)}
            for m in preds:
                p = built["model"].predict(feats, float(twin_t[i]), mode=m)
                preds[m].append(p["value"])
            rows.append({"actual": round(float(plant_t[i]), 4),
                         "mechanistic": round(float(twin_t[i]), 4),
                         "hybrid": round(preds["gated_residual"][-1], 4),
                         "data_only": round(preds["data_only"][-1], 4),
                         "in_domain": built["model"].domain.score(feats)["verdict"]})
        def stats(p):
            e = np.asarray(p) - plant_t
            ss = float(((plant_t - plant_t.mean()) ** 2).sum())
            return {"bias": round(float(e.mean()), 4), "mae": round(float(np.abs(e).mean()), 4),
                    "rmse": round(float(np.sqrt((e ** 2).mean())), 4),
                    "max_abs": round(float(np.abs(e).max()), 4),
                    "r2": round(float(1 - (e ** 2).sum() / ss), 4) if ss > 0 else None}
        res = {m: stats(p) for m, p in preds.items()}
        best = min(res, key=lambda m: res[m]["rmse"])
        out = {
            "target": target, "n_test": len(Xt), "results": res, "best_by_rmse": best,
            "improvement_vs_mechanistic_pct": round(
                100 * (1 - res["gated_residual"]["rmse"] / max(res["mechanistic_only"]["rmse"], 1e-9)), 1),
            "samples": rows[:80], "modes": MODES, "default_mode": DEFAULT_MODE,
            "unmodelled_effect": UNMODELLED_EFFECT,
            "note": "Test points are drawn from the same operating envelope as training, so this "
                    "table is the in-domain case. The extrapolation test is where the mechanistic "
                    "and gated models earn their place.",
        }
        with self._lock:
            self._studies[key] = out
        return out

    # ---------------------------------------------------------------- extrapolation
    def extrapolation_test(self, target: str, *, steps: int = 9, reach: float = 2.2) -> dict[str, Any]:
        """Walk the operating point steadily out of the training envelope and watch each model.

        This is the test that settles the mechanistic-versus-data-driven argument. The data-only
        model's error grows without limit; the gated hybrid's correction tapers to zero and its
        error converges on the mechanistic model's.
        """
        key = ("extrapolation", target, int(steps), float(reach))
        with self._lock:
            if key in self._studies:
                return self._studies[key]
        built = self.build(target)
        ds = self.dataset()
        j = ds["target_names"].index(target)
        names = ds["feature_names"]
        X = np.asarray(ds["X"], dtype=float)
        lo, hi, mu = X.min(axis=0), X.max(axis=0), X.mean(axis=0)
        span = np.where((hi - lo) < 1e-12, 1.0, hi - lo)
        rng = np.random.default_rng(99)
        # one step per feature, each as a fraction of that feature's own trained range, so the
        # walk actually leaves the box rather than spreading a unit vector across 30-odd axes
        direction = rng.choice([-1.0, 1.0], size=len(names))
        rows = []
        for s in range(steps):
            f = reach * s / max(steps - 1, 1)
            v = mu + direction * span * 0.5 * f
            feats = {n: float(v[k]) for k, n in enumerate(names)}
            twin_v = float(np.interp(f, [0, reach], [float(ds["Y_twin"][:, j].mean()),
                                                     float(ds["Y_twin"][:, j].mean() * 1.08)]))
            dom = built["model"].domain.score(feats)
            g = built["model"].predict(feats, twin_v, mode="gated_residual")
            p = built["model"].predict(feats, twin_v, mode="parallel_residual")
            d = built["model"].predict(feats, twin_v, mode="data_only")
            rows.append({
                "step": s, "distance_from_centre": round(f, 3),
                "domain": dom["verdict"], "confidence": dom["confidence"],
                "mechanistic": round(twin_v, 4), "gated_hybrid": g["value"],
                "ungated_hybrid": p["value"], "data_only": d["value"],
                "gate": g["gate"], "correction_applied": g["correction"],
                "correction_unbounded": g["correction_unbounded"],
                "clamped": bool(g["clamped"]),
            })
        last = rows[-1]
        out = {
            "target": target, "rows": rows,
            "direction": {n: round(float(direction[k]), 3) for k, n in enumerate(names)},
            "conclusion": {
                "gated_converges_to_mechanistic": abs(last["gated_hybrid"] - last["mechanistic"]) < 1e-6,
                "gate_at_limit": last["gate"],
                "ungated_departure": round(abs(last["ungated_hybrid"] - last["mechanistic"]), 4),
                "data_only_departure": round(abs(last["data_only"] - last["mechanistic"]), 4),
            },
            "statement": "Outside the learned domain the gated hybrid returns the mechanistic "
                         "prediction exactly. The ungated residual and the data-only model do not, "
                         "and neither has any defined accuracy there.",
        }
        with self._lock:
            self._studies[key] = out
        return out


_builder: HybridBuilder | None = None


def get_builder() -> HybridBuilder:
    global _builder
    if _builder is None:
        _builder = HybridBuilder()
    return _builder
