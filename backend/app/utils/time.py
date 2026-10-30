"""Time helpers: UTC timestamps, window parsing and demo replay clock."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

WINDOWS = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "8h": timedelta(hours=8),
           "24h": timedelta(hours=24), "7d": timedelta(days=7)}
# sample interval chosen so every window returns 60–170 points
WINDOW_STEP = {"15m": timedelta(seconds=15), "1h": timedelta(minutes=1), "8h": timedelta(minutes=5),
               "24h": timedelta(minutes=15), "7d": timedelta(hours=1)}
REPLAY_HOURS = 168


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_window(window: str) -> tuple[timedelta, timedelta]:
    if window not in WINDOWS:
        raise ValueError(f"window must be one of {list(WINDOWS)}")
    return WINDOWS[window], WINDOW_STEP[window]


def replay_hour(ts: datetime, anchor: datetime) -> float:
    """Continuous position (hours) in the 168 h periodic demo replay cycle."""
    return ((ts - anchor).total_seconds() / 3600.0) % REPLAY_HOURS


def shift_of(ts: datetime) -> str:
    h = ts.astimezone(timezone.utc).hour
    return "A (06–14)" if 6 <= h < 14 else ("B (14–22)" if 14 <= h < 22 else "C (22–06)")


def age_seconds(ts: datetime, now: datetime | None = None) -> float:
    return ((now or utcnow()) - ts).total_seconds()
