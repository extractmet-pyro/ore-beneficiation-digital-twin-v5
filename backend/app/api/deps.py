"""FastAPI dependencies: settings, optional API-key auth, service singletons."""
from __future__ import annotations

from fastapi import Header

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthError


def settings_dep() -> Settings:
    return get_settings()


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Enforced only when API_KEY is configured (pilot / production); open in demo mode."""
    key = get_settings().API_KEY
    if key and x_api_key != key:
        raise AuthError("Missing or invalid X-API-Key header")
