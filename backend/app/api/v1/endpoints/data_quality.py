from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.data_quality_service import get_data_quality_service

router = APIRouter()


@router.get("/report", summary="Instrument health, coverage, noise and calibration bias")
def report(plant_id: str = "IX-OB-01", hours: float = Query(24.0, ge=2.0, le=168.0),
           step_h: float = Query(0.5, ge=0.25, le=4.0)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_data_quality_service().report(plant_id, hours, step_h)


@router.get("/missing", summary="Data availability per tag")
def missing(plant_id: str = "IX-OB-01", hours: float = Query(48.0, ge=4.0, le=168.0)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_data_quality_service().missing_data(plant_id, hours)
