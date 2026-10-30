from __future__ import annotations

from fastapi import APIRouter

from app.services.unit_service import get_unit_service

router = APIRouter()


@router.get("", summary="List unit operations")
def list_units():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"units": get_unit_service().list()}


@router.get("/{unit_id}", summary="Unit detail with feed/product streams and characteristic curves")
def unit_detail(unit_id: str, plant_id: str = "IX-OB-01"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_unit_service().detail(plant_id, unit_id)


@router.get("/{unit_id}/curves", summary="Characteristic curves only")
def unit_curves(unit_id: str, plant_id: str = "IX-OB-01"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"plant_id": plant_id, "unit_id": unit_id, "curves": get_unit_service().curves(plant_id, unit_id)}
