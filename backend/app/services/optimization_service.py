"""Supervisory optimisation: constrained set-point search, robustness and trade-off curves."""
from __future__ import annotations

import time

import numpy as np
from scipy.optimize import minimize

from app.control.identification import MVS, MV_BY_KEY
from app.core.config import get_settings
from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.services.plant_service import get_plant_service
from app.twin.circuit import solve
from app.twin.constraints import evaluate_all, penalty
from app.twin.objectives import OBJECTIVE_BY_KEY, OBJECTIVES

DEFAULT_MVS = ["lump_jig_cut_sg", "lump_jig_hutch_water_m3_h", "scrubber_speed_pct_critical",
               "scrubber_water_m3_h", "fines_jig_cut_sg", "spiral_conc_splitter",
               "spiral_middling_splitter", "table_conc_cut", "whims_field_tesla",
               "deslime_cyclone_pressure_kpa", "classifier_dilution_water_m3_h"]


class OptimizationService:
    def objectives(self) -> list[dict]:
        return [o.as_dict() for o in OBJECTIVES]

    def decision_variables(self) -> list[dict]:
        return MVS

    # ---- core search ---------------------------------------------------------------------------
    def optimise(self, plant_id: str, *, objective: str = "margin", mv_keys: list[str] | None = None,
                 bounds_override: dict | None = None, constraint_overrides: dict | None = None,
                 max_evals: int | None = None, ore_override: dict | None = None,
                 start_from_current: bool = True) -> dict:
        t0 = time.perf_counter()
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        if ore_override:
            ore = OreConfig(**{**ore.model_dump(), **ore_override})
        obj = OBJECTIVE_BY_KEY[objective]
        keys = mv_keys or DEFAULT_MVS
        lo = np.array([(bounds_override or {}).get(k, {}).get("lo", MV_BY_KEY[k]["lo"]) for k in keys])
        hi = np.array([(bounds_override or {}).get(k, {}).get("hi", MV_BY_KEY[k]["hi"]) for k in keys])
        base = op.model_dump()
        x0 = np.array([float(base[k]) for k in keys]) if start_from_current else (lo + hi) / 2
        x0 = np.clip(x0, lo, hi)
        span = np.maximum(hi - lo, 1e-9)
        evals = {"n": 0}
        base_res = solve(fs, ore, op, ec)
        obj_scale = max(abs(obj.value(base_res)), 1e-6)   # normalise so constraint penalties stay dominant
        budget = max_evals or get_settings().OPTIMIZER_MAX_EVALS
        trace: list[dict] = []

        def unpack(z):
            x = lo + np.clip(z, 0, 1) * span
            d = dict(base)
            for i, k in enumerate(keys):
                d[k] = round(x[i]) if isinstance(base[k], int) else float(x[i])
            return OperatingConfig(**d), x

        def cost(z):
            if evals["n"] >= budget:
                return 1e12
            evals["n"] += 1
            cfg, x = unpack(z)
            try:
                res = solve(fs, ore, cfg, ec, iterations=8)
            except Exception:  # noqa: BLE001
                return 1e9
            v = obj.value(res)
            base_term = -v / obj_scale * 100.0
            score = base_term + penalty(res, constraint_overrides)
            trace.append({"eval": evals["n"], "objective": v, "score": round(float(score), 4),
                          "penalty": round(penalty(res, constraint_overrides), 3)})
            return float(score)

        z0 = (x0 - lo) / span
        res_opt = minimize(cost, z0, method="Powell",
                           bounds=[(0.0, 1.0)] * len(keys),
                           options={"maxfev": budget, "xtol": 2e-3, "ftol": 2e-3})
        best_cfg, x_best = unpack(res_opt.x)
        best = solve(fs, ore, best_cfg, ec)
        baseline = base_res
        return {
            "plant_id": plant_id, "objective": obj.as_dict(), "mv_keys": keys,
            "status": "converged" if res_opt.success else "budget exhausted",
            "evaluations": evals["n"], "runtime_s": round(time.perf_counter() - t0, 2),
            "setpoints": {k: (round(float(x_best[i]), 4)) for i, k in enumerate(keys)},
            "current": {k: float(base[k]) for k in keys},
            "delta": {k: round(float(x_best[i]) - float(base[k]), 4) for i, k in enumerate(keys)},
            "baseline_kpis": baseline["kpis"], "optimised_kpis": best["kpis"],
            "improvement": {k: round(best["kpis"][k] - baseline["kpis"][k], 4)
                            for k in ("margin_usd_h", "fe_recovery_pct", "lump_fe_pct", "lump_al2o3_pct", "fines_fe_pct",
                                      "energy_kwh_t", "saleable_tph", "mass_yield_pct", "cost_usd_product_t")},
            "constraints": evaluate_all(best, constraint_overrides),
            "constraint_penalty": round(penalty(best, constraint_overrides), 3),
            "convergence": trace[-140:], "warnings": best["warnings"],
        }

    # ---- robustness ----------------------------------------------------------------------------
    def monte_carlo(self, plant_id: str, setpoints: dict | None = None, samples: int | None = None,
                    ore_sigma_pct: float = 4.0, seed: int = 3) -> dict:
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        if setpoints:
            op = OperatingConfig(**{**op.model_dump(), **setpoints})
        n = samples or get_settings().MONTE_CARLO_SAMPLES
        rng = np.random.default_rng(seed)
        rows, penalties = [], []
        for _ in range(n):
            d = ore.model_dump()
            for k in ("fe_head_pct", "sio2_head_pct", "liberation_d50_um", "bond_wi_kwh_t", "axb"):
                d[k] = float(max(d[k] * (1 + rng.normal(0, ore_sigma_pct / 100.0)), 1e-3))
            res = solve(fs, OreConfig(**d), op, ec, iterations=8)
            pen = penalty(res)
            penalties.append(pen)
            rows.append({"fe_head_pct": round(d["fe_head_pct"], 2), "liberation_d50_um": round(d["liberation_d50_um"], 1),
                         **{k: res["kpis"][k] for k in ("lump_fe_pct", "lump_al2o3_pct", "fines_fe_pct", "fe_recovery_pct",
                                                        "margin_usd_h", "energy_kwh_t")},
                         "penalty": round(pen, 2), "feasible": bool(pen <= 0)})
        arr = {k: np.array([r[k] for r in rows], dtype=float)
               for k in ("lump_fe_pct", "lump_al2o3_pct", "fines_fe_pct", "fe_recovery_pct", "margin_usd_h")}
        return {"plant_id": plant_id, "samples": n, "ore_sigma_pct": ore_sigma_pct, "rows": rows,
                "feasible_pct": round(100.0 * float(np.mean([r["feasible"] for r in rows])), 1),
                "summary": {k: {"mean": round(float(v.mean()), 3), "p05": round(float(np.percentile(v, 5)), 3),
                                "p95": round(float(np.percentile(v, 95)), 3), "std": round(float(v.std()), 3)}
                            for k, v in arr.items()}}

    # ---- trade-offs ----------------------------------------------------------------------------
    def pareto(self, plant_id: str, x_kpi: str = "fe_recovery_pct", y_kpi: str = "lump_fe_pct",
               samples: int = 48, mv_keys: list[str] | None = None, seed: int = 5) -> dict:
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        keys = mv_keys or DEFAULT_MVS
        lo = np.array([MV_BY_KEY[k]["lo"] for k in keys])
        hi = np.array([MV_BY_KEY[k]["hi"] for k in keys])
        rng = np.random.default_rng(seed)
        cut = (np.arange(samples)[:, None] + rng.random((samples, len(keys)))) / samples
        for j in range(len(keys)):
            cut[:, j] = rng.permutation(cut[:, j])
        pts = []
        base = op.model_dump()
        for row in cut:
            d = dict(base)
            x = lo + row * (hi - lo)
            for i, k in enumerate(keys):
                d[k] = round(x[i]) if isinstance(base[k], int) else float(x[i])
            res = solve(fs, ore, OperatingConfig(**d), ec, iterations=7)
            pts.append({"setpoints": {k: round(float(x[i]), 3) for i, k in enumerate(keys)},
                        "x": res["kpis"][x_kpi], "y": res["kpis"][y_kpi],
                        "margin_usd_h": res["kpis"]["margin_usd_h"],
                        "lump_al2o3_pct": res["kpis"]["lump_al2o3_pct"],
                        "feasible": bool(penalty(res) <= 0)})
        front = []
        for p in sorted([p for p in pts if p["feasible"]], key=lambda q: (-q["x"], -q["y"])):
            if not front or p["y"] > front[-1]["y"]:
                front.append(p)
        return {"plant_id": plant_id, "x_kpi": x_kpi, "y_kpi": y_kpi, "points": pts,
                "frontier": front, "n": len(pts)}


_service: OptimizationService | None = None


def get_optimization_service() -> OptimizationService:
    global _service
    if _service is None:
        _service = OptimizationService()
    return _service
