"""Historian / DCS integration interface.

Every source (mock replay, OPC UA, OSIsoft/AVEVA PI, MQTT, Kafka, CSV, SQL, REST)
implements the same three calls so that services never depend on the transport.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any


class HistorianAdapter(ABC):
    name: str = "abstract"

    @abstractmethod
    def read_current(self, plant_id: str, tags: list[str] | None = None, ts: datetime | None = None
                     ) -> dict[str, dict[str, Any]]:
        """Return {tag: {value, quality, timestamp, age_s}} for the latest samples."""

    @abstractmethod
    def read_history(self, plant_id: str, tags: list[str], start: datetime, end: datetime,
                     step: timedelta) -> dict[str, Any]:
        """Return {"timestamps": [...], "values": {tag: [...]}, "quality": {tag: [...]}} on a regular grid."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Connection / adapter status for the health and admin pages."""
