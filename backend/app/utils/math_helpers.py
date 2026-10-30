"""Numerical helpers: robust statistics, interpolation, FOPDT responses, RGA."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np


def clamp(v: float, lo: float, hi: float) -> float:
    return float(min(max(v, lo), hi))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return float(a / b) if b not in (0, 0.0) and math.isfinite(b) else default


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mad_zscores(x: Sequence[float]) -> np.ndarray:
    """Robust z-score using the median absolute deviation (NaNs preserved)."""
    arr = np.asarray(x, dtype=float)
    ok = np.isfinite(arr)
    if ok.sum() < 3:
        return np.zeros_like(arr)
    med = np.median(arr[ok])
    mad = np.median(np.abs(arr[ok] - med)) * 1.4826
    if mad < 1e-12:
        mad = np.std(arr[ok]) + 1e-12
    return (arr - med) / mad


def flatline_fraction(x: Sequence[float], rel_tol: float = 1e-9) -> float:
    """Fraction of consecutive samples that do not change (stuck transmitter detection)."""
    arr = np.asarray([v for v in x if v is not None and np.isfinite(v)], dtype=float)
    if arr.size < 3:
        return 0.0
    d = np.abs(np.diff(arr)) <= rel_tol * (np.abs(arr[:-1]) + 1e-9)
    return float(d.mean())


def longest_run(mask: Iterable[bool]) -> int:
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def fopdt_response(t_min: np.ndarray, y0: float, y1: float, tau_min: float, dead_min: float,
                   overshoot: float = 0.0) -> np.ndarray:
    """First-order-plus-dead-time step response with optional under-damped overshoot term."""
    t = np.clip(t_min - dead_min, 0.0, None)
    base = 1.0 - np.exp(-t / max(tau_min, 1e-6))
    if overshoot > 0:
        base = base + overshoot * np.exp(-t / (1.6 * tau_min)) * np.sin(np.pi * t / (2.2 * tau_min))
    return y0 + (y1 - y0) * base


def relative_gain_array(g: np.ndarray) -> np.ndarray:
    """Bristol RGA  Λ = G ∘ (G⁻¹)ᵀ  (pseudo-inverse for ill-conditioned blocks)."""
    g = np.asarray(g, dtype=float)
    return g * np.linalg.pinv(g).T


def condition_number(g: np.ndarray) -> float:
    s = np.linalg.svd(np.asarray(g, dtype=float), compute_uv=False)
    return float(s[0] / max(s[-1], 1e-12))


def percentile_band(samples: Sequence[float], lo: float = 10, hi: float = 90) -> dict[str, float]:
    a = np.asarray(samples, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"p10": float("nan"), "p50": float("nan"), "p90": float("nan")}
    return {"p10": float(np.percentile(a, lo)), "p50": float(np.percentile(a, 50)), "p90": float(np.percentile(a, hi))}


def mcnulty_curve(months: np.ndarray, series: int = 2) -> np.ndarray:
    """McNulty (1998) ramp-up curve (% of design) for series 1–4 projects."""
    params = {1: (0.95, 0.9), 2: (0.85, 0.25), 3: (0.70, 0.12), 4: (0.60, 0.05)}
    plateau, k = params.get(series, params[2])
    return 100.0 * plateau * (1 - np.exp(-k * np.asarray(months, dtype=float))) + \
        (100.0 - 100.0 * plateau) * (1 - np.exp(-0.04 * np.asarray(months, dtype=float)))


def get_path(obj: dict, path: str):
    """Resolve dotted paths into a twin result; list nodes are matched by ``stream_id``."""
    node = obj
    for part in path.split("."):
        if isinstance(node, dict):
            if part not in node:
                return None
            node = node[part]
        elif isinstance(node, list):
            match = [x for x in node if isinstance(x, dict) and x.get("stream_id") == part]
            if not match:
                return None
            node = match[0]
        else:
            return None
    return node
