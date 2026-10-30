"""Environment-driven application settings (pydantic-settings).

All secrets / URLs come from environment variables or a local ``.env`` file.
Nothing sensitive is hard-coded; see ``.env.example`` for the full list.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Ore Beneficiation Digital Twin v5 — Gravity + WHIMS, plant 3-D model, hybrid mechanistic/data-driven layer, MPC and acceptance framework"
    APP_ENV: str = Field("development", description="development | staging | production")
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGINS: str = Field(
        "http://localhost:8080,http://127.0.0.1:8080",
        description="Comma-separated list of CORS origins (operator-desk URL). Use * only for demos.",
    )
    ALLOWED_ORIGIN_REGEX: str = Field(r"https://.*\.onrender\.com", description="Regex of additional allowed origins")
    MODEL_VERSION: str = "OBDT-2026.10.5"
    DEMO_MODE: bool = True
    API_KEY: str = Field("", description="Optional shared API key; if set, X-API-Key header is required on /api/v1")

    # ---- historian / integration placeholders ------------------------------------
    HISTORIAN_TYPE: str = Field("mock", description="mock | opcua | pi | mqtt | kafka | csv | sql | rest")
    OPCUA_ENDPOINT: str = ""
    OPCUA_USERNAME: str = ""
    OPCUA_PASSWORD: str = ""
    OPCUA_NAMESPACE: str = "ns=2;s="
    PI_WEB_API_URL: str = ""
    PI_DATA_SERVER: str = ""
    PI_USERNAME: str = ""
    PI_PASSWORD: str = ""
    MQTT_BROKER_URL: str = ""
    MQTT_TOPIC_PREFIX: str = "plant/tags/"
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_TOPIC: str = "plant-tags"
    SQL_DATABASE_URL: str = ""
    SQL_TABLE: str = "historian"
    REST_HISTORIAN_URL: str = ""
    REST_HISTORIAN_TOKEN: str = ""
    CSV_HISTORIAN_PATH: str = ""

    # ---- engine tuning --------------------------------------------------------------
    OPTIMIZER_MAX_EVALS: int = Field(260, ge=40, le=5000)
    # ---- start-up warm-up ------------------------------------------------------------------
    # The hybrid and validation layers train models on first use. Left lazy, the first operator
    # to open those pages waits for the whole build; on a fractional-CPU host that is minutes.
    # Warming them in a background thread at start-up moves that cost off the request path.
    WARM_ON_START: bool = Field(True, description="Pre-build replay cache, ML registry and hybrid models at start-up")
    WARM_HYBRID: bool = Field(True, description="Include the hybrid and ML models in the warm-up (the slow part)")
    HYBRID_SAMPLES: int = Field(320, ge=60, le=1200,
                                description="Design-of-experiments rows behind the hybrid models. "
                                            "Each row is one twin solve; lower it on constrained hardware.")
    MONTE_CARLO_SAMPLES: int = Field(14, ge=4, le=200)
    SIM_CACHE_SIZE: int = Field(1500, ge=50, le=20000)
    REPLAY_ANCHOR_UTC: str = Field("2026-01-05T00:00:00Z", description="Epoch at which the 168 h demo replay cycle starts")

    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
