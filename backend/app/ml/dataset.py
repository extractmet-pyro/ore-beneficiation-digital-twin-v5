"""Training-data generation for the machine-learning layer.

Two sources are supported:

1. **Twin-sampled design of experiments** — Latin-hypercube sampling of the manipulated variables
   and of the ore disturbances, each point solved with the first-principles twin. This is how a
   soft sensor is bootstrapped before enough plant history exists, and it lets the ML models
   explore regions the plant has never run in.
2. **Historian windows** — the replay historian (or a site historian through the adapters) with
   measurement noise, sensor drift and the usual missing data, which is what the models are
   re-trained on once the plant is running.
"""
from __future__ import annotations

import numpy as np

from app.control.identification import MVS
from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.twin.circuit import solve

FEATURES: list[str] = [m["key"] for m in MVS] + [
    "fe_head_pct", "sio2_head_pct", "al2o3_head_pct", "clay_share", "liberation_d50_um",
    "lump_friability", "axb", "goethite_share", "f80_mm",
]
TARGETS: list[str] = ["lump_fe_pct", "lump_al2o3_pct", "fines_fe_pct", "pellet_fines_fe_pct",
                      "fe_recovery_pct", "mass_yield_pct", "lump_yield_pct", "tailings_fe_pct",
                      "energy_kwh_t", "margin_usd_h", "saleable_tph"]

#: ore-disturbance ranges used for sampling (the plant cannot choose these). The ranges are wide
#: on purpose: an ore-variability study is the main reason a site buys a twin, and a surrogate
#: trained only on the last month of operation cannot answer one.
ORE_RANGES: dict[str, tuple[float, float]] = {
    "fe_head_pct": (48.0, 60.0), "sio2_head_pct": (5.0, 14.0), "al2o3_head_pct": (2.5, 8.0),
    "clay_share": (0.25, 0.80), "liberation_d50_um": (9_000.0, 32_000.0),
    "lump_friability": (0.10, 0.60), "axb": (38.0, 78.0), "goethite_share": (0.10, 0.40),
    "f80_mm": (130.0, 240.0),
}


def _lhs(n: int, d: int, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    cut = np.linspace(0, 1, n + 1)
    u = rng.random((n, d))
    pts = cut[:n, None] + u * (1.0 / n)
    for j in range(d):
        pts[:, j] = rng.permutation(pts[:, j])
    return pts


def build_dataset(n: int = 320, *, seed: int = 11, flowsheet: FlowsheetConfig | None = None,
                  economics: EconomicsConfig | None = None, noise_pct: float = 0.0) -> dict:
    """Sample the twin and return a design matrix plus targets."""
    fs = flowsheet or FlowsheetConfig()
    ec = economics or EconomicsConfig()
    mv_specs = {m["key"]: m for m in MVS}
    cols = FEATURES
    pts = _lhs(n, len(cols), seed)
    rng = np.random.default_rng(seed + 1)
    X, Y, rows = [], [], []
    base_op, base_ore = OperatingConfig(), OreConfig()
    for p in pts:
        op_data = base_op.model_dump()
        ore_data = base_ore.model_dump()
        vals = {}
        for j, c in enumerate(cols):
            if c in mv_specs:
                lo, hi = mv_specs[c]["lo"], mv_specs[c]["hi"]
                v = lo + p[j] * (hi - lo)
                op_data[c] = round(v) if isinstance(base_op.model_dump()[c], int) else float(v)
                vals[c] = float(op_data[c])
            else:
                lo, hi = ORE_RANGES[c]
                v = float(lo + p[j] * (hi - lo))
                ore_data[c] = v
                vals[c] = v
        try:
            res = solve(fs, OreConfig(**ore_data), OperatingConfig(**op_data), ec, iterations=12)
        except Exception:  # noqa: BLE001 — skip infeasible samples
            continue
        y = {t: float(res["kpis"][t]) for t in TARGETS}
        if noise_pct:
            for t in y:
                y[t] *= 1.0 + rng.normal(0.0, noise_pct / 100.0)
        X.append([vals[c] for c in cols])
        Y.append([y[t] for t in TARGETS])
        rows.append({**vals, **y})
    return {"feature_names": cols, "target_names": TARGETS, "X": np.array(X), "Y": np.array(Y),
            "rows": rows, "n": len(rows), "source": "twin_lhs", "seed": seed, "noise_pct": noise_pct}


def historian_frame(historian, plant_id: str, hours: int = 168) -> dict:
    """Assemble a supervised frame from the replay historian (operational data, with noise)."""
    X, Y, rows = [], [], []
    for h in range(hours):
        snap = historian.truth(plant_id, float(h))
        feats = {k: snap["mvs"].get(k) for k in FEATURES if k in snap["mvs"]}
        feats.update({k: snap["ore"].get(k) for k in FEATURES if k in snap["ore"]})
        if any(v is None for v in feats.values()):
            continue
        y = {t: snap["kpis"].get(t) for t in TARGETS}
        if any(v is None for v in y.values()):
            continue
        X.append([feats[c] for c in FEATURES])
        Y.append([y[t] for t in TARGETS])
        rows.append({**feats, **y, "hour": h})
    return {"feature_names": FEATURES, "target_names": TARGETS, "X": np.array(X), "Y": np.array(Y),
            "rows": rows, "n": len(rows), "source": f"historian:{plant_id}", "hours": hours}
