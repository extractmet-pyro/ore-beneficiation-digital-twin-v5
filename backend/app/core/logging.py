"""Structured logging configuration (JSON-ish single line, Render log friendly)."""
from __future__ import annotations

import logging
import sys
import time
from typing import Any

_CONFIGURED = False


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f'{time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))}Z level={record.levelname} ' \
               f'logger={record.name} msg="{record.getMessage()}"'
        extra: dict[str, Any] = getattr(record, "ctx", {}) or {}
        if extra:
            base += " " + " ".join(f"{k}={v}" for k, v in extra.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    root = logging.getLogger()
    if not _CONFIGURED:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(_Formatter())
        root.handlers = [h]
        _CONFIGURED = True
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
