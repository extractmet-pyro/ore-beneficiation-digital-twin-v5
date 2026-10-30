from __future__ import annotations

from fastapi import APIRouter

from app.services.metadata_service import get_metadata_service

router = APIRouter()


@router.get("", summary="Model metadata, assumptions and validation plan")
def metadata():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_metadata_service().metadata()


@router.get("/constraints", summary="Constraint hierarchy")
def constraints():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"constraints": get_metadata_service().constraints()}


@router.get("/objectives", summary="Optimisation objectives")
def objectives():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"objectives": get_metadata_service().objectives()}


@router.get("/config-schema", summary="JSON schema and defaults for every configuration model")
def config_schema():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_metadata_service().config_schema()
