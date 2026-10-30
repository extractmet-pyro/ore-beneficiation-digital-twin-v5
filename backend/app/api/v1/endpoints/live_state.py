from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.live_service import get_live_service

router = APIRouter()


@router.get("/snapshot", summary="Current plant state, tags, alarms and constraints")
def snapshot(plant_id: str = "IX-OB-01", hour: float | None = None):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_live_service().snapshot(plant_id, hour)


@router.get("/soft-sensors", summary="Soft-sensor estimates against measured values")
def soft_sensors(plant_id: str = "IX-OB-01", hour: float | None = None):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"plant_id": plant_id, "soft_sensors": get_live_service().soft_sensors(plant_id, hour)}


@router.get("/trend", summary="KPI trend over the recent window")
def trend(plant_id: str = "IX-OB-01", keys: str = "product_fe_pct,product_sio2_pct,fe_recovery_pct",
          hours: float = Query(24.0, ge=1.0, le=168.0), step_h: float = Query(0.5, ge=0.25, le=4.0),
          view: str = "truth"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_live_service().trend(plant_id, [k.strip() for k in keys.split(",") if k.strip()], hours, step_h, view)


@router.get("/tag-trend", summary="Instrument trend over the recent window")
def tag_trend(plant_id: str = "IX-OB-01", tags: str = "701_AIC_070,701_FIC_070",
              hours: float = Query(24.0, ge=1.0, le=168.0), step_h: float = Query(0.25, ge=0.25, le=4.0),
              view: str = "measurement"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_live_service().tag_trend(plant_id, [t.strip() for t in tags.split(",") if t.strip()],
                                        hours, step_h, view)
