from __future__ import annotations

from fastapi import APIRouter, Query

from app.models.api_models import FullSimulationRequest, ScenarioRequest, SensitivityRequest, SimulationRequest
from app.services.simulation_service import get_simulation_service

router = APIRouter()


@router.post("/run", summary="Solve the flowsheet for a plant (with optional overrides)")
def run(req: SimulationRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    overrides = {k: v for k, v in req.model_dump().items()
                 if k in ("flowsheet", "ore", "operating", "economics") and v}
    return get_simulation_service().run_plant(req.plant_id, overrides, include_streams=req.include_streams,
                                              constraint_overrides=req.constraint_overrides)


@router.post("/run-config", summary="Solve an arbitrary configuration (no plant register lookup)")
def run_config(req: FullSimulationRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_simulation_service().run(req.flowsheet, req.ore, req.operating, req.economics,
                                        include_streams=req.include_streams)


@router.post("/sensitivity", summary="One-variable sweep")
def sensitivity(req: SensitivityRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_simulation_service().sensitivity(req.plant_id, req.variable, req.values, req.kpis, req.group)


@router.get("/tornado", summary="Ranked influence of every input on a KPI")
def tornado(plant_id: str = "IX-OB-01", kpi: str = "margin_usd_h",
            delta_pct: float = Query(8.0, ge=1.0, le=30.0)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_simulation_service().tornado(plant_id, kpi, delta_pct)


@router.post("/compare", summary="Compare named scenarios side by side")
def compare(req: ScenarioRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_simulation_service().compare(req.plant_id, req.scenarios)


@router.get("/grade-recovery", summary="Grade-recovery envelope traced by the lump jig cut density")
def grade_recovery(plant_id: str = "IX-OB-01", points: int = Query(9, ge=3, le=30)):  # noqa: ANN201
    return get_simulation_service().grade_recovery(plant_id, points=points)


@router.get("/washability", summary="Float-and-sink (washability) analysis of the feed and products")
def washability(plant_id: str = "IX-OB-01"):  # noqa: ANN201
    return get_simulation_service().washability(plant_id)
