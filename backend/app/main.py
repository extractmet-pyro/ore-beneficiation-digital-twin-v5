"""FastAPI application factory — Ore Beneficiation (gravity + WHIMS) Digital Twin backend.

Run locally:   uvicorn app.main:app --reload --port 8000
Render start:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.endpoints.health import health as health_handler
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.utils.serialization import NumpyJSONResponse

log = get_logger("app")


def _warm_caches() -> None:
    """Make the service fully warm without retraining anything if we can avoid it.

    Order matters. The precomputed cache written at build time is tried first: it restores the
    hybrid and ML layers in under a second. Only if it is missing or stale do we fall back to
    training here, which is right on a full core and wrong on a fractional one — see
    app/services/warm_cache.py.
    """
    s = get_settings()
    from app.services.warm_cache import load_cache

    warm = load_cache()

    if s.HISTORIAN_TYPE == "mock" and s.WARM_REPLAY and not warm:
        try:
            from app.services.historian_service import get_historian
            from app.services.plant_service import get_plant_service
            h, ps = get_historian(), get_plant_service()
            t0 = time.time()
            for pid in ps.ids():
                ps.tags(pid)
                for i in range(168):
                    h.truth(pid, float(i))
                    h.model(pid, float(i))
            log.info(f"replay cache warmed in {time.time() - t0:.1f}s")
        except Exception:  # noqa: BLE001 — warm-up must never kill the app
            log.exception("replay cache warm-up failed")

    if not warm and s.WARM_HYBRID:
        log.warning("no usable warm cache; training the hybrid and ML layers now. On a small "
                    "instance this saturates the CPU for several minutes — run "
                    "`python scripts/precompute.py` in the build instead.")
        try:
            from app.hybrid.builder import HYBRID_TARGETS, get_builder
            t0 = time.time()
            b = get_builder()
            b.dataset()
            for target in HYBRID_TARGETS:
                b.build(target)
                b.compare(target)
                b.extrapolation_test(target)
            log.info(f"hybrid layer trained in {time.time() - t0:.1f}s")
        except Exception:  # noqa: BLE001
            log.exception("hybrid warm-up failed")
        try:
            from app.ml.registry import get_registry
            t0 = time.time()
            get_registry().ensure()
            log.info(f"ML registry trained in {time.time() - t0:.1f}s")
        except Exception:  # noqa: BLE001
            log.exception("ML registry warm-up failed")

    if s.WARM_VALIDATION and not warm:
        try:
            from app.services.plant_service import get_plant_service
            from app.services.validation_service import get_validation_service
            t0 = time.time()
            vs = get_validation_service()
            for pid in get_plant_service().ids():
                # tests_pass is part of the cache key and the desk sends it as true
                vs.run(pid, section="all", tests_pass=True)
            log.info(f"validation runs warmed in {time.time() - t0:.1f}s")
        except Exception:  # noqa: BLE001
            log.exception("validation warm-up failed")

    log.info("warm-up complete")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    s = get_settings()
    configure_logging(s.LOG_LEVEL)
    log.info(f"starting {s.APP_NAME} env={s.APP_ENV} model={s.MODEL_VERSION} historian={s.HISTORIAN_TYPE}")
    if s.WARM_ON_START:
        threading.Thread(target=_warm_caches, daemon=True, name="warm-caches").start()
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Ore Beneficiation Digital Twin API (v5)", version=s.MODEL_VERSION, lifespan=lifespan,
                  description="First-principles process simulator, model-predictive control and machine-learning "
                              "layer for a gravity and magnetic iron-ore beneficiation plant: rotary "
                              "scrubbing, lump and fines jigging, screw classification, spiral "
                              "concentrators, shaking tables and WHIMS, making lump ore, sinter fines and "
                              "pellet-plant feed from one ROM stream.\n\n"
                              "v5 adds a tagged plant 3-D model bound to live twin state, an explicitly composed "
                              "hybrid mechanistic and data-driven layer with domain-of-validity gating, and a "
                              "verification, validation and acceptance framework with measurable criteria, a test "
                              "scenario catalogue, a gated demonstration protocol and a generated acceptance test "
                              "report.\n\nAll plants anonymised as Industry-X.",
                  docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
                  default_response_class=NumpyJSONResponse)
    origins = s.origins
    app.add_middleware(CORSMiddleware, allow_origins=["*"] if "*" in origins else origins,
                       allow_origin_regex=s.ALLOWED_ORIGIN_REGEX or None, allow_credentials="*" not in origins,
                       allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=2000)

    @app.middleware("http")
    async def timing(request: Request, call_next):  # noqa: ANN001, ANN202
        t0 = time.perf_counter()
        resp = await call_next(request)
        resp.headers["X-Process-Time-ms"] = f"{1000 * (time.perf_counter() - t0):.1f}"
        return resp

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.add_api_route("/health", health_handler, methods=["GET"], tags=["health"], summary="Render health check")

    @app.get("/", tags=["health"], summary="Service banner")
    def root() -> dict:
        return {"service": s.APP_NAME, "version": s.MODEL_VERSION, "docs": "/docs", "health": "/health", "api": "/api/v1"}

    return app


app = create_app()
