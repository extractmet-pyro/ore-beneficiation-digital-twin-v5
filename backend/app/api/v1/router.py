"""API v1 router."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_api_key
from app.api.v1.endpoints import (data_quality, diagnostics, hybrid, live_state, ml, model_metadata, mpc,
                                  optimization, overview, plant3d, plants, simulation, timeseries,
                                  unit_ops, validation)

api_router = APIRouter(dependencies=[Depends(require_api_key)])
api_router.include_router(plants.router, prefix="/plants", tags=["plants"])
api_router.include_router(simulation.router, prefix="/simulation", tags=["simulation"])
api_router.include_router(optimization.router, prefix="/optimization", tags=["optimization"])
api_router.include_router(mpc.router, prefix="/mpc", tags=["model predictive control"])
api_router.include_router(ml.router, prefix="/ml", tags=["machine learning"])
api_router.include_router(hybrid.router, prefix="/hybrid", tags=["hybrid model"])
api_router.include_router(plant3d.router, prefix="/plant3d", tags=["plant 3-D model"])
api_router.include_router(validation.router, prefix="/validation", tags=["validation and acceptance"])
api_router.include_router(live_state.router, prefix="/live", tags=["live"])
api_router.include_router(overview.router, prefix="/overview", tags=["overview"])
api_router.include_router(unit_ops.router, prefix="/units", tags=["unit operations"])
api_router.include_router(diagnostics.router, prefix="/diagnostics", tags=["diagnostics"])
api_router.include_router(data_quality.router, prefix="/data-quality", tags=["data quality"])
api_router.include_router(timeseries.router, prefix="/timeseries", tags=["timeseries"])
api_router.include_router(model_metadata.router, prefix="/metadata", tags=["metadata"])
