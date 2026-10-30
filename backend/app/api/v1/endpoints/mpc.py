from __future__ import annotations

from fastapi import APIRouter, Query

from app.control.mpc import handover_payload
from app.models.api_models import MPCSimulateRequest, MPCSolveRequest
from app.services.data_quality_service import get_data_quality_service
from app.services.mpc_service import get_mpc_service

router = APIRouter()


@router.get("/config", summary="Controller configuration: MVs, CVs and default tuning")
def config():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_mpc_service().config()


@router.get("/identification", summary="FOPDT model matrix identified from the twin")
def identification(plant_id: str = "IX-OB-01", refresh: bool = False):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_mpc_service().identification(plant_id, refresh=refresh)


@router.get("/step-response", summary="Step responses of one CV to each MV")
def step_response(plant_id: str = "IX-OB-01", cv: str = "product_sio2_pct",
                  horizon_min: float = Query(120.0, ge=20.0, le=600.0)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_mpc_service().step_responses(plant_id, cv, horizon_min=horizon_min)


@router.post("/solve", summary="Solve the MPC for the current state and return the move plan")
def solve(req: MPCSolveRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_mpc_service().solve(req.plant_id, hour=req.hour, tuning=req.tuning, targets=req.targets,
                                   mode=req.mode)


@router.post("/simulate", summary="Closed-loop simulation against a disturbance (MPC vs open loop)")
def simulate(req: MPCSimulateRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_mpc_service().simulate(req.plant_id, steps=req.steps, disturbance=req.disturbance,
                                      tuning=req.tuning, controller_on=req.controller_on, compare=req.compare,
                                      noise_pct=req.noise_pct)


@router.get("/advisory", summary="Pairing analysis, control readiness and operator guidance")
def advisory(plant_id: str = "IX-OB-01", use_tag_health: bool = True):  # noqa: ANN201 — serialised by NumpyJSONResponse
    health = get_data_quality_service().tag_health(plant_id) if use_tag_health else None
    return get_mpc_service().advisory(plant_id, health)


@router.post("/handover", summary="DCS hand-over payload for a solved move plan")
def handover(req: MPCSolveRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    sol = get_mpc_service().solve(req.plant_id, hour=req.hour, tuning=req.tuning, targets=req.targets,
                                  mode=req.mode)
    return {"plant_id": req.plant_id, "payload": handover_payload(sol, mode=req.mode),
            "twin_verification": sol["twin_verification"]}
