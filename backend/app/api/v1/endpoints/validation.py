"""Validation and acceptance endpoints.

The specification endpoints (``/criteria``, ``/scenarios``, ``/protocol``, ``/envelope``) are
the ones a client reads before signing anything. The execution endpoints (``/run``,
``/report``, ``/certificate``) are the ones that produce the evidence.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.services.plant_service import get_plant_service
from app.services.validation_service import get_validation_service

router = APIRouter()


def _check(plant_id: str) -> None:
    if plant_id not in get_plant_service().ids():
        raise HTTPException(status_code=404, detail=f"Unknown plant '{plant_id}'")


@router.get("/criteria", summary="The measurable acceptance criteria")
def criteria() -> dict[str, Any]:
    return get_validation_service().criteria()


@router.get("/scenarios", summary="Operating envelope and the scenario catalogue")
def scenarios() -> dict[str, Any]:
    return get_validation_service().scenarios()


@router.get("/protocol", summary="Demonstration and acceptance procedure, gates and roles")
def protocol() -> dict[str, Any]:
    return get_validation_service().protocol()


@router.get("/envelope", summary="Validated operating envelope, and where the plant sits in it")
def envelope(plant_id: str | None = Query(None)) -> dict[str, Any]:
    if plant_id:
        _check(plant_id)
    return get_validation_service().envelope(plant_id)


@router.post("/envelope/check", summary="Classify an arbitrary operating point against the envelope")
def envelope_check(payload: dict = Body(..., examples=[{"values": {"rom_feed_tph": 900.0,
                                                                   "clay_share": 0.9}}])) -> dict[str, Any]:
    vals = payload.get("values") or {}
    if not isinstance(vals, dict) or not vals:
        raise HTTPException(status_code=400, detail="Supply a non-empty 'values' object.")
    return get_validation_service().check_point({k: float(v) for k, v in vals.items()})


@router.get("/run", summary="Execute a validation run and return every verdict")
def run(plant_id: str = Query("IX-OB-01"),
        hours: int = Query(168, ge=24, le=168),
        section: str = Query("all", description="all | accuracy | behaviour | fail_safe | system"),
        tests_pass: bool | None = Query(None, description="Result of the regression suite, "
                                                          "supplied as evidence"),
        refresh: bool = Query(False, description="Force a fresh run rather than replaying the "
                                                 "stored result for this model version and window")
        ) -> dict[str, Any]:
    _check(plant_id)
    if section not in ("all", "accuracy", "behaviour", "fail_safe", "system"):
        raise HTTPException(status_code=400, detail=f"Unknown section '{section}'")
    return get_validation_service().run(plant_id, hours=hours, section=section,
                                        tests_pass=tests_pass, refresh=refresh)


@router.get("/report", summary="Acceptance test report as Markdown")
def report(plant_id: str = Query("IX-OB-01"), hours: int = Query(168, ge=24, le=168),
           gate: str = Query("G1"), tests_pass: bool | None = Query(None)) -> dict[str, Any]:
    _check(plant_id)
    return get_validation_service().report(plant_id, hours=hours, gate=gate, tests_pass=tests_pass)


@router.get("/report.md", response_class=PlainTextResponse,
            summary="Acceptance test report as a downloadable Markdown file")
def report_md(plant_id: str = Query("IX-OB-01"), hours: int = Query(168, ge=24, le=168),
              gate: str = Query("G1"), tests_pass: bool | None = Query(None)) -> str:
    _check(plant_id)
    return get_validation_service().report(plant_id, hours=hours, gate=gate,
                                           tests_pass=tests_pass)["markdown"]


@router.get("/certificate", summary="One-page acceptance summary")
def certificate(plant_id: str = Query("IX-OB-01"), gate: str = Query("G1")) -> dict[str, Any]:
    _check(plant_id)
    return get_validation_service().certificate(plant_id, gate=gate)
