"""Hybrid model endpoints — the mechanistic and data-driven pair, and the evidence for it."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.hybrid.builder import HYBRID_TARGETS
from app.services.hybrid_service import get_hybrid_service
from app.services.plant_service import get_plant_service

router = APIRouter()


def _check(plant_id: str, target: str | None = None) -> None:
    if plant_id not in get_plant_service().ids():
        raise HTTPException(status_code=404, detail=f"Unknown plant '{plant_id}'")
    if target is not None and target not in HYBRID_TARGETS:
        raise HTTPException(status_code=400,
                            detail=f"No hybrid for '{target}'. Available: {', '.join(HYBRID_TARGETS)}")


@router.get("/config", summary="Hybrid architecture, bounds, gate and envelope")
def config(target: str = Query("lump_al2o3_pct")) -> dict[str, Any]:
    _check(get_plant_service().ids()[0], target)
    return get_hybrid_service().config(target)


@router.get("/modes", summary="Available compositions of mechanistic and data-driven models")
def modes() -> dict[str, Any]:
    return get_hybrid_service().modes()


@router.get("/predict", summary="Hybrid prediction with attribution and gate state")
def predict(plant_id: str = Query("IX-OB-01"), target: str = Query("lump_al2o3_pct"),
            mode: str | None = Query(None), hour: float | None = Query(None)) -> dict[str, Any]:
    _check(plant_id, target)
    try:
        return get_hybrid_service().predict(plant_id, target, hour=hour, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/attribution", summary="All compositions side by side at the current operating point")
def attribution(plant_id: str = Query("IX-OB-01"), target: str = Query("lump_al2o3_pct"),
                hour: float | None = Query(None)) -> dict[str, Any]:
    _check(plant_id, target)
    return get_hybrid_service().attribution(plant_id, target, hour=hour)


@router.get("/domain-check", summary="Is the current operating point inside the learned domain?")
def domain_check(plant_id: str = Query("IX-OB-01"), target: str = Query("lump_al2o3_pct"),
                 hour: float | None = Query(None)) -> dict[str, Any]:
    _check(plant_id, target)
    return get_hybrid_service().domain_check(plant_id, target, hour=hour)


@router.get("/compare", summary="Head-to-head on held-out data: mechanistic, data-driven, hybrid")
def compare(target: str = Query("lump_al2o3_pct"), n_test: int = Query(120, ge=30, le=400)) -> dict[str, Any]:
    _check(get_plant_service().ids()[0], target)
    return get_hybrid_service().compare(target, n_test=n_test)


@router.get("/extrapolation", summary="Behaviour as the operating point leaves the learned domain")
def extrapolation(target: str = Query("lump_al2o3_pct"), steps: int = Query(9, ge=4, le=25)) -> dict[str, Any]:
    _check(get_plant_service().ids()[0], target)
    return get_hybrid_service().extrapolation(target, steps=steps)
