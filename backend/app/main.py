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
    """Build everything that is otherwise built lazily on a user's first request.

    Three things in this service are expensive the first time and nearly free afterwards: the
    168 h replay nodes, the machine-learning registry, and the hybrid models. Left lazy, the
    first operator to open the hybrid or validation page pays for the whole build - measured at
    25 s and 37 s on a full core, and minutes on a fractional-CPU host. Doing it here, on a
    daemon thread, moves that cost off the request path and into the deploy.

    Nothing here is allowed to fail the service: a warm-up error is logged and dropped, and the
    affected layer simply builds lazily as before.
    """
    s = get_settings()
    if s.HISTORIAN_TYPE == "mock":
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

    if not s.WARM_HYBRID:
        log.info("hybrid warm-up disabled (WARM_HYBRID=false); first request will build lazily")
        return
    try:
        from app.hybrid.builder import HYBRID_TARGETS, get_builder
        t0 = time.time()
        b = get_builder()
        b.dataset()
        log.info(f"hybrid design of experiments ({b.n} rows) built in {time.time() - t0:.1f}s")
        for target in HYBRID_TARGETS:
            t1 = time.time()
            b.build(target)
            log.info(f"hybrid model '{target}' trained in {time.time() - t1:.1f}s")
        # the two study endpoints each build a fresh held-out design of experiments; they are
        # deterministic and memoised, so warming them here is the difference between a page that
        # opens instantly and one that stalls for half a minute
        for target in HYBRID_TARGETS:
            b.compare(target)
            b.extrapolation_test(target)
        log.info(f"hybrid layer warmed in {time.time() - t0:.1f}s")
    except Exception:  # noqa: BLE001
        log.exception("hybrid warm-up failed")

    try:
        from app.ml.registry import get_registry
        t0 = time.time()
        get_registry().ensure()
        log.info(f"ML registry warmed in {time.time() - t0:.1f}s")
    except Exception:  # noqa: BLE001
        log.exception("ML registry warm-up failed")

    # A validation run is deterministic for a model version and window, and the result is stored.
    # Running it here means the acceptance page opens on a verdict instead of building one.
    try:
        from app.services.plant_service import get_plant_service
        from app.services.validation_service import get_validation_service
        t0 = time.time()
        vs = get_validation_service()
        for pid in get_plant_service().ids():
            # tests_pass is part of the cache key, and the desk sends it as true, so warm the
            # variant the operator desk actually asks for
            vs.run(pid, section="all", tests_pass=True)
        log.info(f"validation runs warmed in {time.time() - t0:.1f}s")
    except Exception:  # noqa: BLE001
        log.exception("validation warm-up failed")


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
