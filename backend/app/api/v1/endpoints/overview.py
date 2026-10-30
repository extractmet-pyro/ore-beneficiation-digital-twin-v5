from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.overview_service import get_overview_service

router = APIRouter()


@router.get("", summary="Plant overview with area cards")
def overview(plant_id: str = "IX-OB-01", hour: float | None = None):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_overview_service().overview(plant_id, hour)


@router.get("/flowsheet", summary="Flowsheet nodes, edges and live stream data")
def flowsheet(plant_id: str = "IX-OB-01", hour: float | None = None):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_overview_service().flowsheet(plant_id, hour)


@router.get("/shifts", summary="Shift-by-shift performance")
def shifts(plant_id: str = "IX-OB-01", shifts: int = Query(6, ge=1, le=21)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_overview_service().shift_performance(plant_id, shifts)
