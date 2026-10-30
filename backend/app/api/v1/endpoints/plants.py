from __future__ import annotations

from fastapi import APIRouter

from app.services.metadata_service import get_metadata_service
from app.services.plant_service import get_plant_service

router = APIRouter()


@router.get("", summary="List demo plants")
def list_plants():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"plants": get_plant_service().list()}


@router.get("/{plant_id}", summary="Plant detail with full configuration")
def get_plant(plant_id: str):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_plant_service().get(plant_id)


@router.get("/{plant_id}/tags", summary="Instrument register for a plant")
def get_tags(plant_id: str):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"plant_id": plant_id, "tags": get_plant_service().tags(plant_id)}


@router.get("/{plant_id}/config-schema", summary="JSON schema and defaults for every editable input")
def config_schema(plant_id: str):  # noqa: ANN201 — serialised by NumpyJSONResponse
    p = get_plant_service().get(plant_id)
    return {"plant_id": plant_id, "current": {k: p[k] for k in ("flowsheet", "ore", "operating", "economics")},
            **get_metadata_service().config_schema()}
