"""Crushing, screening and hydrocyclone classification for the ore-beneficiation circuit.

This plant does not grind. Size reduction stops at the tertiary crusher, because the ore is
naturally banded on a centimetre scale: hard massive hematite and soft shaly gangue separate at
lump and chip sizes, which is what makes a jig-and-spiral flowsheet viable and what keeps the
energy intensity of the plant an order of magnitude below a magnetite concentrator's.

The models kept here are therefore the classification-and-breakage crusher, the screen partition,
and the hydrocyclone — the last used twice, once for desliming and once for preparing spiral feed.

Implemented from first principles / accepted unit models:

* **Crushing**      – Whiten classification-breakage with a t10 appearance function.
* **HPGR**          – Klymowsky/Morrell specific throughput constant (m-dot), specific pressing
                      force Fsp, specific energy from Fsp, edge/centre product split and a
                      t10-based product size distribution (micro-cracking increases fines).
* **Tower mill**    – fine/ultra-fine grinding by signature-plot (Jankovic) with a Bond-type
                      check: E = k (P80^-a - F80^-a); stirred mills are ~30-40 % more efficient
                      than ball mills below ~100 um, which is why the circuit uses FTMs.
* **Screen**        – Whiten partition with sharpness and water split.
* **Hydrocyclone**  – Plitt d50c with a Whiten efficiency curve, bypass = water split.

All models operate on the 32-class size x 4-mineral matrix defined in :mod:`app.twin.psd`, so
mineral-by-size behaviour (quartz is harder than hematite, hematite reports finer) is preserved.
"""
from __future__ import annotations

import numpy as np

from app.twin.psd import (G, GEO_MEAN_UM, N_BINS, N_CLASSES, SIZES_UM, Stream, apply_liberation,
                          liberation_curve, p_passing)

# tn / t10 family (Narayanan & Whiten style): fraction passing 1/n of the parent size
_TN_N = np.array([75.0, 50.0, 25.0, 10.0, 4.0, 2.0])
_TN_TABLE = {  # t10 (%) -> [t75, t50, t25, t10, t4, t2] (%)
    10: [2.6, 3.4, 5.3, 10.0, 22.0, 42.0],
    20: [5.8, 7.4, 11.2, 20.0, 40.0, 63.0],
    30: [9.6, 12.1, 17.7, 30.0, 55.0, 77.0],
    40: [14.2, 17.6, 24.9, 40.0, 68.0, 87.0],
    50: [19.7, 24.0, 33.0, 50.0, 79.0, 93.0],
}
_T10_KEYS = np.array(sorted(_TN_TABLE))
_T10_VALS = np.array([_TN_TABLE[k] for k in _T10_KEYS])


def appearance_matrix(t10_pct: float) -> np.ndarray:
    """Breakage (appearance) matrix A[j, i]: mass fraction of broken class-i material reporting to class j."""
    t10 = float(np.clip(t10_pct, 1.0, 60.0))
    tn = np.array([np.interp(t10, _T10_KEYS, _T10_VALS[:, k]) for k in range(len(_TN_N))]) / 100.0
    # cumulative passing curve of progeny relative to parent size, anchored at 1.0 for x/xp = 1
    ratios = np.concatenate([1.0 / _TN_N, [1.0]])
    passing = np.concatenate([tn, [1.0]])
    order = np.argsort(ratios)
    ratios, passing = ratios[order], passing[order]
    A = np.zeros((N_CLASSES, N_CLASSES))
    for i in range(N_CLASSES):
        parent = GEO_MEAN_UM[i]
        cum = np.interp(np.log(np.maximum(SIZES_UM / parent, 1e-6)), np.log(ratios), passing,
                        left=0.0, right=1.0)
        cum = np.clip(cum, 0.0, 1.0)
        lower = np.concatenate([cum[1:], [0.0]])
        col = np.clip(cum - lower, 0.0, None)
        col[:i] = 0.0  # progeny can never be coarser than the parent class
        s = col.sum()
        A[:, i] = col / s if s > 1e-12 else 0.0
        if s <= 1e-12:
            A[i, i] = 1.0
    return A


#: quartz is the more competent mineral, so gangue-rich particles break a little less readily
_HARDNESS = 0.86 + 0.28 * G


def break_stream(m: np.ndarray, selection: np.ndarray, t10_pct: float, axb: float,
                 lib_d50_um: float | None = None) -> np.ndarray:
    """One breakage pass over the (size x liberation) matrix.

    Selected mass is redistributed to finer size classes with the appearance matrix; the progeny
    are then re-liberated according to the liberation curve of their new size class.
    """
    A = appearance_matrix(t10_pct)
    out = np.zeros_like(m)
    for j in range(m.shape[1]):
        s = np.clip(selection * _HARDNESS[j], 0.0, 0.995)
        broken = m[:, j] * s
        out[:, j] = m[:, j] - broken + A @ broken
    if lib_d50_um:
        out = apply_liberation(out, liberation_curve(lib_d50_um))
    return out


# ---------------------------------------------------------------------------------------------
def crusher(feed: Stream, css_mm: float, axb: float, installed_kw: float, wi_kwh_t: float,
            stage: str = "secondary", lib_d50_um: float | None = None) -> tuple[Stream, dict]:
    """Cone/gyratory crusher: classification function on CSS + t10 breakage, Bond power draw."""
    css_um = css_mm * 1000.0
    k1, k2 = 0.35 * css_um, 1.9 * css_um
    sel = np.clip((GEO_MEAN_UM - k1) / max(k2 - k1, 1e-6), 0.0, 1.0) ** 1.4
    ecs = np.clip(6.0 / max(axb, 10.0) * 25.0, 0.25, 2.2)  # kWh/t specific comminution energy
    t10 = float(np.clip(axb * (1 - np.exp(-0.0004 * axb * ecs * 1000.0)) * 0.55, 6.0, 45.0))
    m = break_stream(feed.m, sel, t10, axb, lib_d50_um)
    product = feed.copy(m=m, name=f"{stage}_crusher_product")
    f80, p80 = feed.p80_um, product.p80_um
    power = feed.solids_tph * 10.0 * wi_kwh_t * (1 / np.sqrt(max(p80, 1.0)) - 1 / np.sqrt(max(f80, 1.0)))
    power = float(np.clip(power, 0.0, installed_kw * 1.05))
    return product, {"feed_tph": round(feed.solids_tph, 1), "css_mm": css_mm, "f80_mm": round(f80 / 1000, 2),
                     "p80_mm": round(p80 / 1000, 2), "reduction_ratio": round(f80 / max(p80, 1e-6), 2),
                     "power_kw": round(power, 1), "installed_kw": installed_kw,
                     "power_utilisation_pct": round(100 * power / max(installed_kw, 1e-6), 1),
                     "specific_energy_kwh_t": round(power / max(feed.solids_tph, 1e-6), 3)}


def screen(feed: Stream, aperture_um: float, sharpness: float = 2.6, water_to_oversize: float = 0.25,
           ) -> tuple[Stream, Stream, dict]:
    """Vibrating screen: Whiten partition to oversize. Returns (oversize, undersize, info)."""
    part = 1.0 / (1.0 + (aperture_um / np.maximum(GEO_MEAN_UM, 1e-6)) ** sharpness)
    part = np.clip(part, 0.0, 0.995)
    m_over = feed.m * part[:, None]
    m_under = feed.m - m_over
    mo, mu = m_over.sum(), m_under.sum()
    over = feed.copy(solids_tph=feed.solids_tph * mo, m=m_over / max(mo, 1e-12),
                     water_tph=feed.water_tph * water_to_oversize, name="screen_oversize")
    under = feed.copy(solids_tph=feed.solids_tph * mu, m=m_under / max(mu, 1e-12),
                      water_tph=feed.water_tph * (1 - water_to_oversize), name="screen_undersize")
    true_under = float((feed.size_frac * (GEO_MEAN_UM < aperture_um)).sum())
    recovered = float((feed.size_frac * (1 - part) * (GEO_MEAN_UM < aperture_um)).sum())
    eff = 100.0 * recovered / max(true_under, 1e-9)  # recovery of true undersize to the undersize stream
    return over, under, {"aperture_mm": round(aperture_um / 1000, 2), "oversize_tph": round(over.solids_tph, 1),
                         "undersize_tph": round(under.solids_tph, 1),
                         "circulating_load_pct": round(100 * over.solids_tph / max(under.solids_tph, 1e-6), 1),
                         "screening_efficiency_pct": round(float(np.clip(eff, 0, 100)), 1)}


def hydrocyclone(feed: Stream, *, n_open: int, diameter_mm: float, vortex_mm: float, apex_mm: float,
                 pressure_kpa: float) -> tuple[Stream, Stream, dict]:
    """Plitt d50c + Whiten efficiency curve. Returns (underflow, overflow, info)."""
    q_total = max(feed.slurry_m3_h, 1e-6)
    q_per = q_total / max(n_open, 1)
    cv = 100.0 * (feed.solids_tph / feed.sg) / q_total  # % solids by volume
    rho_s = feed.sg
    # Plitt (1976), dimensions in cm and flow per cyclone in m3/h
    dc, do, du = diameter_mm / 10.0, vortex_mm / 10.0, apex_mm / 10.0
    di = 0.25 * dc                      # inlet diameter (standard geometry)
    h = 2.5 * dc                        # free vortex height
    d50c = (50.5 * dc ** 0.46 * di ** 0.6 * do ** 1.21 * np.exp(0.063 * cv)
            / (du ** 0.71 * h ** 0.38 * max(q_per, 1e-3) ** 0.45 * (rho_s - 1.0) ** 0.5))
    d50c = float(np.clip(d50c, 3.0, 600.0))
    m = 1.9  # sharpness
    mx = np.clip(m * GEO_MEAN_UM / max(d50c, 1e-6), 0.0, 60.0)
    ec = (np.exp(mx) - 1.0) / (np.exp(mx) + np.exp(m) - 2.0)
    rf = float(np.clip(0.08 + 0.004 * cv + 0.28 * (apex_mm / max(vortex_mm, 1e-6)) ** 2.5, 0.08, 0.55))  # water split
    part = rf + (1 - rf) * np.clip(ec, 0.0, 1.0)
    m_uf = feed.m * part[:, None]
    m_of = feed.m - m_uf
    mu, mo = m_uf.sum(), m_of.sum()
    uf = feed.copy(solids_tph=feed.solids_tph * mu, m=m_uf / max(mu, 1e-12), water_tph=feed.water_tph * rf,
                   name="cyclone_underflow")
    of = feed.copy(solids_tph=feed.solids_tph * mo, m=m_of / max(mo, 1e-12), water_tph=feed.water_tph * (1 - rf),
                   name="cyclone_overflow")
    return uf, of, {"cyclones_open": n_open, "diameter_mm": diameter_mm, "pressure_kpa": round(pressure_kpa, 1),
                    "feed_m3_h": round(q_total, 1), "feed_per_cyclone_m3_h": round(q_per, 1),
                    "feed_solids_pct": round(feed.solids_pct, 1), "d50c_um": round(d50c, 1),
                    "water_split_to_uf_pct": round(100 * rf, 1),
                    "circulating_load_pct": round(100 * uf.solids_tph / max(of.solids_tph, 1e-6), 1),
                    "overflow_p80_um": round(of.p80_um, 1), "underflow_solids_pct": round(uf.solids_pct, 1)}
