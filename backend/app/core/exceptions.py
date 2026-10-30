"""Domain exceptions and FastAPI exception handlers with clear, structured error payloads."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger("errors")


class TwinError(Exception):
    status_code = 400
    code = "twin_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(TwinError):
    status_code = 404
    code = "not_found"


class ValidationFailure(TwinError):
    status_code = 422
    code = "validation_failure"


class SimulationError(TwinError):
    status_code = 500
    code = "simulation_error"


class IntegrationNotConfigured(TwinError):
    status_code = 503
    code = "integration_not_configured"


class AuthError(TwinError):
    status_code = 401
    code = "unauthorised"


def _payload(code: str, message: str, path: str, detail: dict | list | None = None) -> dict:
    return {"status": "error", "error": {"code": code, "message": message, "detail": detail or {}},
            "path": path, "timestamp": datetime.now(timezone.utc).isoformat()}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TwinError)
    async def _twin(request: Request, exc: TwinError):  # noqa: ANN202
        log.warning(f"{exc.code}: {exc.message}")
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.code, exc.message, request.url.path, exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):  # noqa: ANN202
        errs = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_payload("request_validation", "Request payload failed validation",
                                                              request.url.path, errs))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN202
        log.exception(f"unhandled error on {request.url.path}")
        return JSONResponse(status_code=500, content=_payload("internal_error", f"{type(exc).__name__}: {exc}",
                                                              request.url.path))
