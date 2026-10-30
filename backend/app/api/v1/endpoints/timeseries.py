from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.historian_service import REPLAY_HOURS, get_historian

router = APIRouter()


@router.get("/kpis", summary="KPI history from the replay historian")
def kpis(plant_id: str = "IX-OB-01", keys: str = "product_fe_pct,product_sio2_pct,fe_recovery_pct",
         start_h: float = 0.0, end_h: float = Query(168.0, ge=1.0, le=168.0),
         step_h: float = Query(1.0, ge=0.25, le=8.0), view: str = "truth"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"plant_id": plant_id, "view": view,
            **get_historian().kpi_series(plant_id, [k.strip() for k in keys.split(",") if k.strip()],
                                         start_h, end_h, step_h, view)}


@router.get("/tags", summary="Tag history from the replay historian")
def tags(plant_id: str = "IX-OB-01", tags: str = "701_AIC_070,401_JIC_030", start_h: float = 0.0,
         end_h: float = Query(168.0, ge=1.0, le=168.0), step_h: float = Query(1.0, ge=0.25, le=8.0),
         view: str = "measurement"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"plant_id": plant_id, "view": view,
            **get_historian().series(plant_id, [t.strip() for t in tags.split(",") if t.strip()],
                                     start_h, end_h, step_h, view)}


@router.get("/replay-info", summary="Replay window definition and scripted events")
def replay_info():  # noqa: ANN201 — serialised by NumpyJSONResponse
    h = get_historian()
    return {"replay_hours": REPLAY_HOURS, "anchor_utc": h.anchor.isoformat(), "events": h.events()}
