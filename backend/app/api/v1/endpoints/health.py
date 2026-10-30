"""Liveness / readiness."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import get_settings


def health():  # noqa: ANN201 — serialised by NumpyJSONResponse
    s = get_settings()
    return {"status": "ok", "service": s.APP_NAME, "version": s.MODEL_VERSION, "env": s.APP_ENV,
            "historian": s.HISTORIAN_TYPE, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
