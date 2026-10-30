from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.diagnostics_service import get_diagnostics_service

router = APIRouter()


@router.get("/balance", summary="Mass, iron, silica and water balance closure")
def balance(plant_id: str = "IX-OB-01"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_diagnostics_service().balance(plant_id)


@router.get("/reconcile", summary="Weighted least-squares data reconciliation")
def reconcile(plant_id: str = "IX-OB-01", hour: float | None = None):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_diagnostics_service().reconcile(plant_id, hour)


@router.get("/residuals", summary="Measurement-vs-model residuals and fault flags")
def residuals(plant_id: str = "IX-OB-01", hours: float = Query(48.0, ge=4.0, le=168.0),
              step_h: float = Query(1.0, ge=0.5, le=6.0)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_diagnostics_service().residuals(plant_id, hours, step_h)


@router.get("/events", summary="Scripted event catalogue in the replay week")
def events():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"events": get_diagnostics_service().event_catalogue()}
