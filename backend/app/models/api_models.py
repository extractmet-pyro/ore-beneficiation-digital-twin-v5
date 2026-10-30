"""Request/response models for the HTTP API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig


class SimulationRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    flowsheet: dict[str, Any] | None = Field(None, description="Partial override of the flowsheet configuration")
    ore: dict[str, Any] | None = None
    operating: dict[str, Any] | None = None
    economics: dict[str, Any] | None = None
    include_streams: bool = True
    constraint_overrides: dict[str, dict] | None = None


class FullSimulationRequest(BaseModel):
    flowsheet: FlowsheetConfig = FlowsheetConfig()
    ore: OreConfig = OreConfig()
    operating: OperatingConfig = OperatingConfig()
    economics: EconomicsConfig = EconomicsConfig()
    include_streams: bool = True


class SensitivityRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    group: Literal["flowsheet", "ore", "operating", "economics"] = "operating"
    variable: str = "amine_collector_g_t"
    values: list[float] = Field(default_factory=lambda: [60, 80, 100, 120, 140, 160])
    kpis: list[str] = Field(default_factory=lambda: ["product_sio2_pct", "fe_recovery_pct", "margin_usd_h"])


class ScenarioRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    scenarios: list[dict] = Field(default_factory=list)


class OptimizationRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    objective: str = "margin"
    mv_keys: list[str] | None = None
    bounds_override: dict[str, dict] | None = None
    constraint_overrides: dict[str, dict] | None = None
    max_evals: int | None = Field(None, ge=20, le=4000)
    ore_override: dict[str, Any] | None = None
    start_from_current: bool = True


class MonteCarloRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    setpoints: dict[str, float] | None = None
    samples: int | None = Field(None, ge=4, le=200)
    ore_sigma_pct: float = Field(4.0, ge=0.5, le=25.0)


class ParetoRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    x_kpi: str = "fe_recovery_pct"
    y_kpi: str = "product_fe_pct"
    samples: int = Field(48, ge=8, le=250)
    mv_keys: list[str] | None = None


class MPCSolveRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    hour: float | None = None
    targets: dict[str, float] | None = None
    tuning: dict[str, Any] | None = None
    mode: Literal["advisory", "closed_loop"] = "advisory"


class MPCSimulateRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    steps: int = Field(48, ge=6, le=240)
    disturbance: dict[str, list[float]] | None = None
    tuning: dict[str, Any] | None = None
    controller_on: bool = True
    compare: bool = True
    noise_pct: float = Field(0.35, ge=0.0, le=5.0)


class MLPredictRequest(BaseModel):
    plant_id: str = "IX-OB-01"
    targets: list[str] | None = None
    hour: float | None = None
    overrides: dict[str, float] | None = None


class MLRetrainRequest(BaseModel):
    targets: list[str] | None = None
    algorithm: Literal["gradient_boosting", "random_forest", "ridge"] = "gradient_boosting"
    n_samples: int | None = Field(None, ge=60, le=1200)
