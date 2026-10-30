"""Magnetic separation for the ore-beneficiation twin.

Hematite and goethite are **paramagnetic**, not ferromagnetic: their mass susceptibility is three
orders of magnitude below magnetite's. Recovering them magnetically therefore needs a *high*
intensity separator — a matrix of expanded metal or grooved plates inside a 1.0-1.5 T field, where
the field gradient at the matrix surface supplies the capture force. That is the WHIMS in this
flowsheet, and it exists for one reason: to recover the fine hematite in the desliming-cyclone
underflow that no gravity unit in the plant can hold, and to turn it into pellet feed.

The capture model balances the three forces acting on a particle at the matrix wire:

* magnetic, proportional to susceptibility (so to the particle's iron content) and to ``B * grad B``;
* hydrodynamic drag, proportional to particle diameter and slurry velocity;
* gravity, proportional to the cube of the diameter,

which gives the characteristic capture window: too fine and drag wins, too coarse and gravity
strips the particle off the matrix. Reference: Svoboda, *Magnetic Techniques for the Treatment of
Materials* (2004); Oberteuffer (1974).
"""
from __future__ import annotations

import numpy as np

from app.twin.psd import GEO_MEAN_UM, G, Stream, magnetic_susceptibility, split


def whims(feed: Stream, *, field_tesla: float, matrix: str, gap_mm: float, ring_speed_rpm: float,
          wash_water_m3_h: float, feed_solids_pct_target: float, n_units: int = 2,
          capacity_tph_per_unit: float = 45.0, installed_kw: float = 110.0
          ) -> tuple[Stream, Stream, dict]:
    """Wet high-intensity magnetic separator. Returns (magnetic concentrate, non-magnetic tail, info)."""
    chi = magnetic_susceptibility(feed.goethite_share)
    b = float(np.clip(field_tesla, 0.3, 1.8))
    gap = float(np.clip(gap_mm, 1.0, 12.0))
    speed = float(np.clip(ring_speed_rpm, 1.0, 8.0))

    #: matrix type sets the field gradient and therefore the capture force per tesla
    matrix_gain = {"expanded_metal": 1.0, "grooved_plate": 0.82, "steel_wool": 1.35, "rod": 0.70}.get(matrix, 1.0)
    grad_factor = matrix_gain * (4.0 / gap) ** 0.45
    force = b ** 1.75 * grad_factor                      # ~ B * grad(B) at the matrix surface

    loading = feed.solids_tph / max(n_units * capacity_tph_per_unit, 1e-6)
    slurry_factor = (1.0 + 0.55 * max(loading - 1.0, 0.0)) * (1.0 + 0.010 * abs(feed_solids_pct_target - 30.0))
    wash_factor = 1.0 - 0.22 * np.tanh(max(wash_water_m3_h, 0.0) / max(20.0 * n_units, 1e-6))

    # susceptibility at which a particle is captured half the time
    chi50 = float(np.clip(0.34 * slurry_factor / max(force, 1e-6), 0.02, 0.95))
    sharpness = 3.4 + 1.7 * b
    sel = 1.0 / (1.0 + (np.maximum(chi, 1e-6) / chi50) ** (-sharpness))

    # size window: drag-limited below ~8 um, detachment-limited above ~500 um
    d = np.maximum(GEO_MEAN_UM, 1e-6)
    fine = 1.0 / (1.0 + (7.0 / d) ** 1.5)
    coarse = 1.0 / (1.0 + (d / (520.0 * (b / 1.2) ** 0.6)) ** 2.4)
    size_eff = fine * coarse * float(np.clip(1.0 - 0.10 * (speed / 4.0 - 1.0), 0.75, 1.05))

    rec = np.clip(sel[None, :] * size_eff[:, None], 0.0, 1.0)
    # mechanical entrainment of fine gangue into the magnetic product, reduced by wash water
    entrain = 0.045 * wash_factor * fine[:, None] * np.ones((1, len(G)))
    rec = np.clip(rec + entrain * (1.0 - rec), 0.0, 1.0)

    water_split = float(np.clip(0.30 + 0.30 * wash_water_m3_h / max(wash_water_m3_h + feed.water_tph, 1e-6), 0.15, 0.7))
    feed_w = feed.copy(water_tph=feed.water_tph + max(wash_water_m3_h, 0.0))
    mags, non_mags = split(feed_w, rec, water_split, ("whims_conc", "whims_tail"),
                           goethite_bias=1.08, alumina_bias=0.68)
    a_in, a_c, a_t = feed.assay(), mags.assay(), non_mags.assay()
    power = installed_kw * n_units * float(np.clip(0.45 + 0.5 * (b / 1.2) ** 2, 0.3, 1.2))
    info = {"n_units": n_units, "field_tesla": round(b, 3), "matrix": matrix, "gap_mm": round(gap, 2),
            "ring_speed_rpm": round(speed, 2), "matrix_gain": round(matrix_gain, 3),
            "capture_force_index": round(float(force), 3), "chi50": round(chi50, 4),
            "loading_fraction": round(loading, 3), "capacity_tph": round(n_units * capacity_tph_per_unit, 1),
            "wash_water_m3_h": round(max(wash_water_m3_h, 0.0), 1),
            "feed_tph": round(feed.solids_tph, 2), "conc_tph": round(mags.solids_tph, 2),
            "tail_tph": round(non_mags.solids_tph, 2),
            "mass_recovery_pct": round(100 * mags.solids_tph / max(feed.solids_tph, 1e-6), 2),
            "feed_fe_pct": round(a_in["fe_pct"], 2), "conc_fe_pct": round(a_c["fe_pct"], 2),
            "tail_fe_pct": round(a_t["fe_pct"], 2), "conc_sio2_pct": round(a_c["sio2_pct"], 2),
            "conc_al2o3_pct": round(a_c["al2o3_pct"], 2), "conc_loi_pct": round(a_c["loi_pct"], 2),
            "conc_p80_um": round(mags.p80_um, 2), "conc_blaine_cm2_g": round(mags.blaine, 0),
            "fe_recovery_pct": round(100 * mags.fe_tph / max(feed.fe_tph, 1e-9), 2),
            "upgrade_ratio": round(a_c["fe_pct"] / max(a_in["fe_pct"], 1e-6), 3),
            "power_kw": round(power, 1), "installed_kw": round(installed_kw * n_units, 1)}
    return mags, non_mags, info


def capture_curve(field_tesla: float, matrix: str = "expanded_metal", gap_mm: float = 4.0,
                  goethite_share: float = 0.22, loading: float = 1.0) -> list[dict]:
    """Probability of reporting to the magnetic product against particle iron content."""
    matrix_gain = {"expanded_metal": 1.0, "grooved_plate": 0.82, "steel_wool": 1.35, "rod": 0.70}.get(matrix, 1.0)
    force = float(np.clip(field_tesla, 0.3, 1.8)) ** 1.75 * matrix_gain * (4.0 / max(gap_mm, 1.0)) ** 0.45
    chi50 = float(np.clip(0.34 * (1.0 + 0.55 * max(loading - 1.0, 0.0)) / max(force, 1e-6), 0.02, 0.95))
    sharpness = 3.4 + 1.7 * float(np.clip(field_tesla, 0.3, 1.8))
    chi = magnetic_susceptibility(goethite_share)
    sel = 1.0 / (1.0 + (np.maximum(chi, 1e-6) / chi50) ** (-sharpness))
    return [{"particle_iron_fraction": round(float(g), 3), "capture_probability": round(float(p), 4)}
            for g, p in zip(G, sel)]


def size_recovery_curve(field_tesla: float) -> list[dict]:
    """Magnetic recovery of liberated hematite against particle size — the WHIMS capture window."""
    b = float(np.clip(field_tesla, 0.3, 1.8))
    d = np.maximum(GEO_MEAN_UM, 1e-6)
    eff = (1.0 / (1.0 + (7.0 / d) ** 1.5)) * (1.0 / (1.0 + (d / (520.0 * (b / 1.2) ** 0.6)) ** 2.4))
    keep = d < 5000.0
    return [{"size_um": round(float(x), 2), "recovery_pct": round(float(100 * y), 2)}
            for x, y in zip(d[keep], eff[keep])]
