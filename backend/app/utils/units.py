"""Unit conversion and normalisation helpers used by ingestion and the API."""
from __future__ import annotations

from typing import Callable

# (from_unit, to_unit) -> function
_CONV: dict[tuple[str, str], Callable[[float], float]] = {
    ("t/h", "t/d"): lambda v: v * 24.0,
    ("t/d", "t/h"): lambda v: v / 24.0,
    ("t/h", "kt/d"): lambda v: v * 24.0 / 1000.0,
    ("st/h", "t/h"): lambda v: v * 0.907185,
    ("t/h", "st/h"): lambda v: v / 0.907185,
    ("kPa", "psi"): lambda v: v * 0.145038,
    ("psi", "kPa"): lambda v: v / 0.145038,
    ("kPa", "bar"): lambda v: v / 100.0,
    ("bar", "kPa"): lambda v: v * 100.0,
    ("m³/h", "L/s"): lambda v: v / 3.6,
    ("L/s", "m³/h"): lambda v: v * 3.6,
    ("m³/h", "USgpm"): lambda v: v * 4.402868,
    ("USgpm", "m³/h"): lambda v: v / 4.402868,
    ("µm", "mesh_equiv_um"): lambda v: v,
    ("µm", "mm"): lambda v: v / 1000.0,
    ("mm", "µm"): lambda v: v * 1000.0,
    ("kW", "MW"): lambda v: v / 1000.0,
    ("MW", "kW"): lambda v: v * 1000.0,
    ("kW", "hp"): lambda v: v * 1.341022,
    ("hp", "kW"): lambda v: v / 1.341022,
    ("°C", "°F"): lambda v: v * 9 / 5 + 32,
    ("°F", "°C"): lambda v: (v - 32) * 5 / 9,
    ("g/t", "lb/st"): lambda v: v * 0.002,
    ("lb/st", "g/t"): lambda v: v / 0.002,
    ("m", "ft"): lambda v: v * 3.28084,
    ("ft", "m"): lambda v: v / 3.28084,
    ("kWh/t", "kWh/st"): lambda v: v * 0.907185,
    ("kWh/st", "kWh/t"): lambda v: v / 0.907185,
    ("% Cu", "ppm Cu"): lambda v: v * 1e4,
    ("ppm Cu", "% Cu"): lambda v: v / 1e4,
}

UNIT_SYSTEMS = {
    "metric": {"mass_flow": "t/h", "pressure": "kPa", "flow": "m³/h", "size": "µm", "power": "kW", "energy": "kWh/t"},
    "imperial": {"mass_flow": "st/h", "pressure": "psi", "flow": "USgpm", "size": "µm", "power": "hp", "energy": "kWh/st"},
}

ALIASES = {"tph": "t/h", "tpd": "t/d", "m3/h": "m³/h", "um": "µm", "micron": "µm", "microns": "µm", "degC": "°C",
           "degF": "°F", "gpt": "g/t", "kwh/t": "kWh/t", "kpa": "kPa", "kw": "kW", "mw": "MW", "%cs": "% Cs"}


def normalise_unit(unit: str) -> str:
    """Map vendor/historian unit spellings onto canonical engineering units."""
    u = (unit or "").strip()
    return ALIASES.get(u, ALIASES.get(u.lower(), u))


def convert(value: float | None, from_unit: str, to_unit: str) -> float | None:
    """Convert a value; identical units are passed through; unknown pairs raise ValueError."""
    if value is None:
        return None
    f, t = normalise_unit(from_unit), normalise_unit(to_unit)
    if f == t:
        return float(value)
    if (f, t) not in _CONV:
        raise ValueError(f"No conversion from '{f}' to '{t}'")
    return float(_CONV[(f, t)](float(value)))


def supported_conversions() -> list[dict[str, str]]:
    return [{"from": a, "to": b} for a, b in _CONV]
