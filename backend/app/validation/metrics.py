"""Validation statistics.

One function per statistic, each returning a plain number, so that an acceptance report can be
audited line by line. Nothing here is specific to this plant or to this twin: these are the
measures a metallurgist, a statistician and a third-party assessor would all recognise.

Two of them deserve a note, because they are the ones that stop a model passing on a
technicality:

* **Theil's U2** compares the model against the naive "tomorrow equals today" forecast. A model
  with a flattering R-squared can still be worse than persistence; U2 above 1 says so plainly.
* **Prediction-interval coverage** checks the model's own stated uncertainty. A model that is
  accurate but claims to be far more accurate than it is will fail an operator the first time
  it is wrong, so its honesty is tested separately from its accuracy.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _clean(y_true, y_pred):
    a = np.asarray(y_true, dtype=float).ravel()
    b = np.asarray(y_pred, dtype=float).ravel()
    m = np.isfinite(a) & np.isfinite(b)
    return a[m], b[m]


def bias(y_true, y_pred) -> float:
    a, b = _clean(y_true, y_pred)
    return float(np.mean(b - a))


def mae(y_true, y_pred) -> float:
    a, b = _clean(y_true, y_pred)
    return float(np.mean(np.abs(b - a)))


def rmse(y_true, y_pred) -> float:
    a, b = _clean(y_true, y_pred)
    return float(np.sqrt(np.mean((b - a) ** 2)))


def mape(y_true, y_pred) -> float:
    a, b = _clean(y_true, y_pred)
    d = np.abs(a)
    m = d > 1e-9
    return float(np.mean(np.abs((b[m] - a[m]) / d[m])) * 100.0) if m.any() else float("nan")


def r2(y_true, y_pred) -> float:
    a, b = _clean(y_true, y_pred)
    ss_res = float(np.sum((a - b) ** 2))
    ss_tot = float(np.sum((a - np.mean(a)) ** 2))
    return float("nan") if ss_tot < 1e-12 else 1.0 - ss_res / ss_tot


def nash_sutcliffe(y_true, y_pred) -> float:
    """Identical in form to R-squared but computed against the observed mean, which is the
    convention in process and hydrological model validation."""
    return r2(y_true, y_pred)


def theil_u2(y_true, y_pred) -> float:
    """Model error divided by the error of a no-change forecast. Below 1 beats persistence."""
    a, b = _clean(y_true, y_pred)
    if len(a) < 3:
        return float("nan")
    num = float(np.sqrt(np.mean((b[1:] - a[1:]) ** 2)))
    den = float(np.sqrt(np.mean((a[:-1] - a[1:]) ** 2)))
    return float("inf") if den < 1e-12 else num / den


def index_of_agreement(y_true, y_pred) -> float:
    """Willmott's d. Bounded in [0, 1] and less forgiving than R-squared of a biased model."""
    a, b = _clean(y_true, y_pred)
    am = float(np.mean(a))
    den = float(np.sum((np.abs(b - am) + np.abs(a - am)) ** 2))
    return float("nan") if den < 1e-12 else 1.0 - float(np.sum((a - b) ** 2)) / den


def bland_altman(y_true, y_pred) -> dict[str, float]:
    """Mean difference and 95 % limits of agreement — the standard way of asking whether two
    methods of measuring the same quantity may be used interchangeably."""
    a, b = _clean(y_true, y_pred)
    d = b - a
    m, sd = float(np.mean(d)), float(np.std(d, ddof=1)) if len(d) > 1 else 0.0
    return {"mean_difference": m, "sd_difference": sd,
            "loa_lower": m - 1.96 * sd, "loa_upper": m + 1.96 * sd,
            "loa_width": 3.92 * sd}


def paired_t_on_bias(y_true, y_pred) -> dict[str, Any]:
    """Is the mean error distinguishable from zero? A significant bias is a model defect; a
    non-significant one is noise and should not be 'corrected'."""
    a, b = _clean(y_true, y_pred)
    d = b - a
    n = len(d)
    if n < 3:
        return {"n": n, "t": None, "p_approx": None, "significant_bias": None}
    sd = float(np.std(d, ddof=1))
    if sd < 1e-12:
        return {"n": n, "t": 0.0, "p_approx": 1.0, "significant_bias": False}
    t = float(np.mean(d) / (sd / math.sqrt(n)))
    # two-sided normal approximation; adequate at the sample sizes an acceptance test uses
    p = float(math.erfc(abs(t) / math.sqrt(2.0)))
    return {"n": n, "t": round(t, 3), "p_approx": round(p, 5), "significant_bias": bool(p < 0.05)}


def coverage(y_true, lo, hi) -> float:
    """Fraction of observations inside the model's own 95 % prediction interval."""
    a = np.asarray(y_true, dtype=float).ravel()
    l = np.asarray(lo, dtype=float).ravel()
    h = np.asarray(hi, dtype=float).ravel()
    m = np.isfinite(a) & np.isfinite(l) & np.isfinite(h)
    return float(np.mean((a[m] >= l[m]) & (a[m] <= h[m])) * 100.0) if m.any() else float("nan")


def ks_statistic(y_true, y_pred) -> dict[str, Any]:
    """Two-sample Kolmogorov-Smirnov on the two distributions. Catches a model that gets the
    average right while getting the spread badly wrong."""
    a, b = _clean(y_true, y_pred)
    if len(a) < 5 or len(b) < 5:
        return {"d": None, "critical_05": None, "same_distribution": None}
    grid = np.sort(np.concatenate([a, b]))
    fa = np.searchsorted(np.sort(a), grid, side="right") / len(a)
    fb = np.searchsorted(np.sort(b), grid, side="right") / len(b)
    d = float(np.max(np.abs(fa - fb)))
    crit = 1.36 * math.sqrt(1 / len(a) + 1 / len(b))
    return {"d": round(d, 4), "critical_05": round(crit, 4), "same_distribution": bool(d <= crit)}


def durbin_watson(y_true, y_pred) -> float:
    """Autocorrelation in the residuals. Values far from 2 mean the model is missing a
    time-varying effect rather than being merely noisy."""
    a, b = _clean(y_true, y_pred)
    d = b - a
    if len(d) < 3:
        return float("nan")
    return float(np.sum(np.diff(d) ** 2) / max(np.sum(d ** 2), 1e-12))


def residual_profile(y_true, y_pred, bins: int = 12) -> list[dict[str, Any]]:
    """Error against the observed level, which is how a plant discovers that a model is fine
    in the middle of its range and wrong at the ends."""
    a, b = _clean(y_true, y_pred)
    if len(a) < bins:
        bins = max(3, len(a) // 3)
    edges = np.linspace(a.min(), a.max(), bins + 1)
    out = []
    for i in range(bins):
        m = (a >= edges[i]) & (a <= edges[i + 1] if i == bins - 1 else a < edges[i + 1])
        if m.sum() == 0:
            continue
        out.append({"from": round(float(edges[i]), 4), "to": round(float(edges[i + 1]), 4),
                    "n": int(m.sum()), "bias": round(float(np.mean(b[m] - a[m])), 4),
                    "rmse": round(float(np.sqrt(np.mean((b[m] - a[m]) ** 2))), 4)})
    return out


def full_report(y_true, y_pred, lo=None, hi=None) -> dict[str, Any]:
    """Every statistic in one call, which is what a criterion is evaluated against."""
    a, b = _clean(y_true, y_pred)
    ba = bland_altman(a, b)
    out = {
        "n": int(len(a)),
        "observed": {"mean": round(float(np.mean(a)), 4), "sd": round(float(np.std(a, ddof=1)), 4)
                     if len(a) > 1 else 0.0,
                     "min": round(float(np.min(a)), 4), "max": round(float(np.max(a)), 4)},
        "predicted": {"mean": round(float(np.mean(b)), 4),
                      "sd": round(float(np.std(b, ddof=1)), 4) if len(b) > 1 else 0.0},
        "bias": round(bias(a, b), 5), "mae": round(mae(a, b), 5), "rmse": round(rmse(a, b), 5),
        "mape_pct": round(mape(a, b), 4), "r2": round(r2(a, b), 5),
        "nash_sutcliffe": round(nash_sutcliffe(a, b), 5),
        "index_of_agreement": round(index_of_agreement(a, b), 5),
        "theil_u2": round(theil_u2(a, b), 4),
        "durbin_watson": round(durbin_watson(a, b), 4),
        "bland_altman": {k: round(v, 5) for k, v in ba.items()},
        "paired_t": paired_t_on_bias(a, b),
        "ks": ks_statistic(a, b),
        "residual_profile": residual_profile(a, b),
    }
    if lo is not None and hi is not None:
        out["coverage_95_pct"] = round(coverage(a, lo, hi), 2)
    return out
