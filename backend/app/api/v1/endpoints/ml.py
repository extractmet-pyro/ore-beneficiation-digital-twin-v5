from __future__ import annotations

from fastapi import APIRouter, Query

from app.models.api_models import MLPredictRequest, MLRetrainRequest
from app.services.ml_service import get_ml_service

router = APIRouter()


@router.get("/status", summary="Model registry status")
def status():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().status()


@router.get("/models", summary="Trained models with metrics")
def models():  # noqa: ANN201 — serialised by NumpyJSONResponse
    return {"models": get_ml_service().models()}


@router.post("/predict", summary="Soft-sensor predictions for the current state")
def predict(req: MLPredictRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().predict(req.plant_id, req.targets, req.hour, req.overrides)


@router.get("/hybrid", summary="Hybrid twin + residual-model prediction")
def hybrid(plant_id: str = "IX-OB-01", target: str = "product_sio2_pct", hour: float | None = None):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().hybrid(plant_id, target, hour)


@router.get("/importance", summary="Permutation importance for a target")
def importance(target: str = "product_sio2_pct"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().importance(target)


@router.get("/learning-curve", summary="How performance scales with training data")
def learning_curve(target: str = "product_sio2_pct"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().learning_curve(target)


@router.get("/partial-dependence", summary="Partial dependence of a model on one feature")
def partial_dependence(target: str = "product_sio2_pct", feature: str = "amine_collector_g_t"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().partial_dependence(target, feature)


@router.get("/anomaly", summary="Anomaly scores over the recent window")
def anomaly(plant_id: str = "IX-OB-01", hours: float = Query(24.0, ge=2.0, le=168.0),
            step_h: float = Query(1.0, ge=0.5, le=6.0)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().anomaly(plant_id, hours, step_h)


@router.get("/drift", summary="Feature drift (PSI) against the reference window")
def drift(plant_id: str = "IX-OB-01"):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().drift(plant_id)


@router.get("/scan", summary="ML surrogate vs twin across one variable")
def scan(plant_id: str = "IX-OB-01", target: str = "product_sio2_pct",
         feature: str = "amine_collector_g_t", points: int = Query(14, ge=4, le=40)):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().scenario_scan(plant_id, target, feature, points)


@router.post("/retrain", summary="Rebuild the dataset and retrain the models")
def retrain(req: MLRetrainRequest):  # noqa: ANN201 — serialised by NumpyJSONResponse
    return get_ml_service().retrain(req.targets, req.algorithm, req.n_samples)
