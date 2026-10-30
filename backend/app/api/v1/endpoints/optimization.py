from __future__ import annotations

from fastapi import APIRouter

from app.models.api_models import MonteCarloRequest, OptimizationRequest, ParetoRequest
from app.services.optimization_service import get_optimization_service

router = APIRouter()


@router.get("/objectives", summary="Available objectives")
def objectives():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"objectives": get_optimization_service().objectives(),
            "decision_variables": get_optimization_service().decision_variables()}


@router.post("/run", summary="Constrained set-point optimisation")
def run(req: OptimizationRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_optimization_service().optimise(
        req.plant_id, objective=req.objective, mv_keys=req.mv_keys, bounds_override=req.bounds_override,
        constraint_overrides=req.constraint_overrides, max_evals=req.max_evals, ore_override=req.ore_override,
        start_from_current=req.start_from_current)


@router.post("/monte-carlo", summary="Robustness of a set-point against ore variability")
def monte_carlo(req: MonteCarloRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_optimization_service().monte_carlo(req.plant_id, req.setpoints, req.samples, req.ore_sigma_pct)


@router.post("/pareto", summary="Trade-off frontier between two KPIs")
def pareto(req: ParetoRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_optimization_service().pareto(req.plant_id, req.x_kpi, req.y_kpi, req.samples, req.mv_keys)
