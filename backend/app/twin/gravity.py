"""Gravity concentration and scrubbing units for the ore-beneficiation twin.

Every unit here separates on **particle density**, which the state matrix already carries: the
liberation axis ``g`` maps one-to-one onto specific gravity (2.65 free quartz to 5.15 free
hematite). Each model therefore reduces to two things:

* a **density partition** — a generalised Tromp curve with a cut density ``SG50`` and a probable
  error ``Ep`` set by the machine and its operating point;
* a **size window** — the range of particle sizes over which the machine actually works, outside
  which material either short-circuits (too coarse) or is lost hydraulically (too fine).

The size dependence of ``Ep`` is what distinguishes the machines from one another. A jig is
sharp on 40 mm lumps and hopeless below 1 mm; a spiral takes over from 3 mm to 75 um; a table is
the sharpest of the three but only on a narrow, fine, closely sized feed. Putting all three in
one circuit — as this flowsheet does — is precisely a response to that.

References: Burt, *Gravity Concentration Technology* (1984); Wills & Finch, *Mineral Processing
Technology*, 8th ed. (2016); Gaudin (1939) for equal-settling ratios; Rong & Lyman (1985) for
the partition-curve form.
"""
from __future__ import annotations

import numpy as np

from app.twin.psd import (G, GEO_MEAN_UM, N_BINS, N_CLASSES, SG_QZ, SG_WATER, SIZES_UM, Stream, blend,
                          pct_passing_size, split, uplift_grade)

LN3 = float(np.log(3.0))


# ---------------------------------------------------------------------------------------------
def density_partition(sg: np.ndarray, sg50: float, ep: np.ndarray | float) -> np.ndarray:
    """Tromp partition to the sinks for particles of density ``sg`` at cut point ``sg50``.

    ``Ep`` is the probable error, (SG75 - SG25)/2; it may be supplied per size class, which is how
    the size dependence of every gravity machine enters the model.
    """
    ep_arr = np.maximum(np.asarray(ep, dtype=float), 1e-3)
    return 1.0 / (1.0 + np.exp(-LN3 * (np.asarray(sg)[None, :] - sg50) / ep_arr[:, None]))


def size_window(lo_um: float, hi_um: float, lo_sharp: float = 1.6, hi_sharp: float = 2.2) -> np.ndarray:
    """Fraction of each size class the machine can actually treat (1 inside the window)."""
    d = GEO_MEAN_UM
    fine = 1.0 / (1.0 + (lo_um / np.maximum(d, 1e-6)) ** lo_sharp)
    coarse = 1.0 / (1.0 + (np.maximum(d, 1e-6) / hi_um) ** hi_sharp)
    return fine * coarse


def _ep_by_size(ep_ref: float, d_ref_um: float, exponent: float, floor: float = 1.0) -> np.ndarray:
    """Probable error per size class: sharp in the machine's size range, degrading below it."""
    return ep_ref * (floor + (d_ref_um / np.maximum(GEO_MEAN_UM, 1e-6)) ** exponent)


# ---------------------------------------------------------------------------------------------
def rotary_scrubber(feed: Stream, *, diameter_m: float, length_m: float, speed_pct_critical: float,
                    water_m3_h: float, feed_solids_pct_target: float, lifter_count: int = 8,
                    installed_kw: float = 400.0, detachable_clay_frac: float = 0.55,
                    friability: float = 0.25) -> tuple[Stream, dict]:
    """Rotary scrubber: attrition-scrub clay/ochre off the ore and disperse it into the water.

    Lateritic and ochreous iron ores carry a clay coating that blinds screens, dilutes every
    downstream product and is the single largest cause of high alumina in sinter feed. The
    scrubber is an attrition mill for that coating: retention time and impeller action detach it,
    and the liberated clay reports to the fines where the desliming cyclones can take it out.

    Modelled as a first-order attrition process: the fraction of clay detached follows
    ``1 - exp(-k * t)`` with ``k`` rising with drum speed and falling with pulp density, and the
    detached clay is placed in the finest size classes as free gangue.
    """
    vol = np.pi * (diameter_m / 2.0) ** 2 * length_m
    charge_vol = 0.35 * vol
    solids_target = float(np.clip(feed_solids_pct_target, 40.0, 80.0))
    water_needed = feed.solids_tph * (100.0 - solids_target) / max(solids_target, 1e-6)
    water_in = feed.water_tph + max(water_m3_h, 0.0)
    slurry_m3_h = feed.solids_tph / max(feed.sg, 1e-6) + water_in
    residence_min = 60.0 * charge_vol / max(slurry_m3_h, 1e-6)
    solids_pct = 100.0 * feed.solids_tph / max(feed.solids_tph + water_in, 1e-6)

    speed = float(np.clip(speed_pct_critical, 15.0, 45.0))
    k = 0.30 * (speed / 30.0) ** 1.4 * (lifter_count / 8.0) ** 0.35 * (65.0 / max(solids_pct, 25.0)) ** 0.5
    detached = float(np.clip(1.0 - np.exp(-k * residence_min), 0.0, 0.985))

    #: Clay in this ore sits in two places: as discrete shale and ochre particles, and as a
    #: coating adhering to the surface of otherwise good ore lumps. The second kind is what
    #: decides the alumina in the lump product, because a coated lump carries its clay straight
    #: to the stockpile. Scrubbing strips the coating: the lump loses mass, keeps its iron units
    #: and therefore comes out both lighter and richer, while the detached clay reports to the
    #: fines where the desliming cyclones can reject it.
    clay_mass = (1.0 - feed.iron_mineral_frac) * feed.alumina_share
    detachable = float(np.clip(detachable_clay_frac, 0.0, 0.85))
    surface_frac = 0.85 * detachable * detached      # fraction of the clay held as a surface coating
    coating = float(np.clip(clay_mass * surface_frac, 0.0, 0.25))

    m = feed.m.copy()
    coarse = GEO_MEAN_UM > 1500.0
    coarse_mass = float(m[coarse].sum())
    removed = 0.0
    if coarse_mass > 1e-9 and coating > 1e-9:
        # the coating is a fraction of the coarse material's own mass
        c = float(np.clip(coating / max(coarse_mass, 1e-9), 0.0, 0.16))
        factor = 1.0 / (1.0 - c)
        before = float(m[coarse].sum())
        idx = np.where(coarse)[0]
        for i in idx:
            m[i] = uplift_grade(m[i], factor)
        removed = before - float(m[coarse].sum())

    # the detached coating, plus any free clay shaken out of the fines, reports to the fine classes
    fines_sel = (GEO_MEAN_UM < 40.0) & (GEO_MEAN_UM > 2.0)
    wfine = np.where(fines_sel, 1.0 / np.maximum(GEO_MEAN_UM, 1.0), 0.0)
    wfine = wfine / max(wfine.sum(), 1e-12)
    m[:, 0] += wfine * removed
    m = np.clip(m, 0.0, None)
    m = m / max(m.sum(), 1e-12)
    moved = removed

    # attrition of friable ore: lateritic and ochreous lumps degrade in the drum, and the fines
    # they shed are what feeds the desliming-cyclone and WHIMS circuit downstream
    attr = (0.05 + 0.60 * float(np.clip(friability, 0.0, 0.8))) * detached
    m2 = m.copy()
    for i in range(N_CLASSES - 2):
        if GEO_MEAN_UM[i] < 2000.0:
            continue
        moved_row = m2[i] * attr
        m2[i] -= moved_row
        m2[i + 1] += moved_row * 0.62
        m2[i + 2] += moved_row * 0.38
    m2 = m2 / max(m2.sum(), 1e-12)

    power = installed_kw * (0.35 + 0.55 * (feed.solids_tph / max(0.9 * diameter_m ** 2 * length_m * 22.0, 1e-6)))
    power = float(np.clip(power, 0.05 * installed_kw, installed_kw))
    out = feed.copy(m=m2, water_tph=water_in, name="scrubbed")
    info = {"diameter_m": diameter_m, "length_m": length_m, "volume_m3": round(vol, 1),
            "speed_pct_critical": round(speed, 2), "residence_time_min": round(residence_min, 2),
            "slurry_m3_h": round(slurry_m3_h, 1), "solids_pct": round(solids_pct, 2),
            "water_added_m3_h": round(max(water_m3_h, 0.0), 1),
            "water_required_m3_h": round(max(water_needed - feed.water_tph, 0.0), 1),
            "clay_detachment_pct": round(100 * detached, 2),
            "detachable_clay_pct": round(100 * detachable, 1),
            "surface_coating_pct_of_feed": round(100 * coating, 3),
            "clay_removed_pct_of_feed": round(100 * moved, 3),
            "scrubbing_index": round(k * residence_min, 3),
            "attrition_fraction": round(float(attr), 4),
            "friability": round(float(np.clip(friability, 0.0, 0.8)), 3),
            "minus_45um_in_pct": round(feed.minus_45um_pct, 2),
            "minus_45um_out_pct": round(out.minus_45um_pct, 2),
            "power_kw": round(power, 1), "installed_kw": installed_kw,
            "power_utilisation_pct": round(100 * power / max(installed_kw, 1e-6), 1),
            "specific_energy_kwh_t": round(power / max(feed.solids_tph, 1e-6), 3)}
    return out, info


# ---------------------------------------------------------------------------------------------
def jig(feed: Stream, *, cut_sg_target: float, stroke_mm: float, frequency_rpm: float,
        bed_depth_mm: float, hutch_water_m3_h: float, area_m2: float, n_cells: int = 2,
        installed_kw: float = 75.0, machine: str = "lump") -> tuple[Stream, Stream, dict]:
    """Jig: pulsed-bed density separation. Returns (sinks/concentrate, floats/tailing, info).

    A jig stratifies a bed by repeated dilation and consolidation. The cut density is set mainly
    by how loose the bed is kept — hutch water and stroke energy open it, bed depth and feed rate
    close it — and the sharpness by the stroke-frequency product relative to the particle size.

    The jig is excellent on lumps and poor on fines: its probable error rises steeply below about
    3 mm because a fine particle has no time to settle through the dilated bed before consolidation.
    That single fact is why this flowsheet jigs the lumps and sends the fines to spirals instead.
    """
    sgp = feed.particle_sg
    stroke = float(np.clip(stroke_mm, 5.0, 60.0))
    freq = float(np.clip(frequency_rpm, 40.0, 300.0))
    bed = float(np.clip(bed_depth_mm, 60.0, 600.0))
    pulsion = stroke * freq / 1000.0                          # m/min of bed dilation
    loading = feed.solids_tph / max(area_m2 * n_cells, 1e-6)  # t/h per m2

    # bed condition -> achieved cut density around the target
    hutch_flux = hutch_water_m3_h / max(area_m2 * n_cells, 1e-6)          # m3/h per m2 of bed
    looseness = (pulsion / 2.64) ** 0.45 * (hutch_flux / 12.0) ** 0.30 \
        * (220.0 / max(bed, 60.0)) ** 0.25 * (12.0 / max(loading, 2.0)) ** 0.18
    looseness = float(np.clip(looseness, 0.35, 2.4))
    #: a looser bed floats more material, i.e. raises the density at which the cut is made
    sg50 = float(np.clip(cut_sg_target * (0.80 + 0.20 * looseness), 2.7, 5.0))

    # sharpness: good for lumps, degrading fast below a few mm
    ep_base = 0.16 * (1.0 + 0.35 * abs(np.log(max(looseness, 0.2))))
    ep = _ep_by_size(ep_base, d_ref_um=3200.0, exponent=0.80, floor=0.55)
    ep = np.clip(ep, 0.06, 3.5)

    part = density_partition(sgp, sg50, ep)
    window = size_window(700.0, 90_000.0, lo_sharp=1.25, hi_sharp=3.0)
    # material outside the window: coarse lumps ride over to the sinks, fines wash to the floats
    coarse_bypass = np.clip(1.0 - 1.0 / (1.0 + (GEO_MEAN_UM / 90_000.0) ** 3.0), 0.0, 1.0)
    fines_loss = np.clip(1.0 - window, 0.0, 1.0) * (GEO_MEAN_UM < 700.0)
    rec = part * window[:, None] + coarse_bypass[:, None] * (1 - window[:, None])
    # a little hydraulic carry-over of fines to the sinks with the hutch water
    rec += fines_loss[:, None] * 0.12
    rec = np.clip(rec, 0.0, 1.0)

    water_split = float(np.clip(0.22 + 0.28 * hutch_water_m3_h / max(hutch_water_m3_h + feed.water_tph, 1e-6), 0.1, 0.7))
    total_water = feed.water_tph + max(hutch_water_m3_h, 0.0)
    feed_w = feed.copy(water_tph=total_water)
    sink, float_ = split(feed_w, rec, water_split, ("jig_sinks", "jig_floats"),
                         goethite_bias=0.94, alumina_bias=1.22)
    a_in, a_s, a_f = feed.assay(), sink.assay(), float_.assay()
    power = installed_kw * float(np.clip(0.25 + 0.55 * pulsion / 3.2 + 0.2 * loading / 14.0, 0.15, 1.0))
    info = {"machine": machine, "n_cells": n_cells, "area_m2": round(area_m2 * n_cells, 2),
            "cut_sg_target": round(cut_sg_target, 3), "cut_sg_achieved": round(sg50, 3),
            "ep_at_10mm": round(float(np.interp(10_000.0, GEO_MEAN_UM[::-1], ep[::-1])), 3),
            "ep_at_1mm": round(float(np.interp(1_000.0, GEO_MEAN_UM[::-1], ep[::-1])), 3),
            "stroke_mm": round(stroke, 1), "frequency_rpm": round(freq, 1),
            "pulsion_m_min": round(pulsion, 3), "bed_depth_mm": round(bed, 1),
            "hutch_water_m3_h": round(hutch_water_m3_h, 1), "hutch_flux_m3_h_m2": round(hutch_flux, 2),
            "bed_looseness": round(float(looseness), 3),
            "loading_tph_m2": round(loading, 2), "feed_tph": round(feed.solids_tph, 2),
            "yield_pct": round(100 * sink.solids_tph / max(feed.solids_tph, 1e-6), 2),
            "feed_fe_pct": round(a_in["fe_pct"], 2), "conc_fe_pct": round(a_s["fe_pct"], 2),
            "tail_fe_pct": round(a_f["fe_pct"], 2), "conc_sio2_pct": round(a_s["sio2_pct"], 2),
            "conc_al2o3_pct": round(a_s["al2o3_pct"], 2),
            "fe_recovery_pct": round(100 * sink.fe_tph / max(feed.fe_tph, 1e-9), 2),
            "upgrade_ratio": round(a_s["fe_pct"] / max(a_in["fe_pct"], 1e-6), 3),
            "power_kw": round(power, 1), "installed_kw": installed_kw,
            "power_utilisation_pct": round(100 * power / max(installed_kw, 1e-6), 1)}
    return sink, float_, info


# ---------------------------------------------------------------------------------------------
def spiral_classifier(feed: Stream, *, tank_width_m: float, tank_length_m: float, slope_deg: float,
                      screw_rpm: float, weir_height_m: float, dilution_water_m3_h: float,
                      n_units: int = 2, installed_kw: float = 45.0) -> tuple[Stream, Stream, dict]:
    """Screw (spiral) classifier. Returns (sand underflow, slime overflow, info).

    A mechanical classifier separates by **settling velocity**, not by size alone. Because a dense
    hematite grain settles like a quartz grain roughly 1.6x its diameter (the equal-settling
    ratio), the overflow is systematically leaner than the feed and the sand product is
    systematically richer. The model applies a per-density cut size:

        d50(SG) = d50_ref * sqrt((SG_qz - 1) / (SG - 1))

    which is exactly the hindered-settling relationship behind that behaviour.
    """
    area = 0.62 * tank_width_m * tank_length_m * n_units      # settling-pool area, not the whole tank
    water = feed.water_tph + max(dilution_water_m3_h, 0.0)
    overflow_rate = (feed.solids_tph / max(feed.sg, 1e-6) + water) / max(area, 1e-6)   # m3/h/m2
    slope = float(np.clip(slope_deg, 12.0, 22.0))
    rpm = float(np.clip(screw_rpm, 1.5, 12.0))

    # reference (quartz) cut size from the overflow rate and the pool geometry
    d50_ref = 150.0 * (overflow_rate / 4.0) ** 0.55 * (weir_height_m / 0.30) ** 0.30 \
        * (18.0 / slope) ** 0.22 * (4.5 / rpm) ** 0.12
    d50_ref = float(np.clip(d50_ref, 35.0, 900.0))

    sgp = feed.particle_sg
    d50_by_class = d50_ref * np.sqrt((SG_QZ - SG_WATER) / np.maximum(sgp - SG_WATER, 1e-6))
    # Whiten-type efficiency curve about each density's own cut size
    sharp = 3.1
    x = GEO_MEAN_UM[:, None] / d50_by_class[None, :]
    to_sand = x ** sharp / (1.0 + x ** sharp)
    # water bypass: a fraction of the feed reports to each product regardless of size
    bypass = float(np.clip(0.10 + 0.30 * (1.0 - overflow_rate / 8.0), 0.05, 0.28))
    to_sand = bypass + (1.0 - bypass) * to_sand
    to_sand = np.clip(to_sand, 0.0, 1.0)

    water_to_sand = float(np.clip(0.10 + 0.20 * (1.0 - overflow_rate / 8.0), 0.06, 0.35))
    feed_w = feed.copy(water_tph=water)
    sand, slime = split(feed_w, to_sand, water_to_sand, ("classifier_sand", "classifier_overflow"),
                        goethite_bias=1.0, alumina_bias=0.82)
    a_in, a_s, a_o = feed.assay(), sand.assay(), slime.assay()
    power = installed_kw * float(np.clip(0.3 + 0.5 * feed.solids_tph / max(area * 12.0, 1e-6), 0.15, 1.0))
    info = {"n_units": n_units, "pool_area_m2": round(area, 2), "slope_deg": round(slope, 1),
            "sand_loading_tph_m2": round(feed.solids_tph / max(area, 1e-6), 3),
            "screw_rpm": round(rpm, 2), "weir_height_m": round(weir_height_m, 3),
            "overflow_rate_m3_h_m2": round(overflow_rate, 3),
            "d50_quartz_um": round(d50_ref, 1),
            "d50_hematite_um": round(float(d50_by_class[-1]), 1),
            "equal_settling_ratio": round(float(d50_ref / max(d50_by_class[-1], 1e-6)), 3),
            "bypass_pct": round(100 * bypass, 1),
            "sand_tph": round(sand.solids_tph, 2), "overflow_tph": round(slime.solids_tph, 2),
            "sand_solids_pct": round(sand.solids_pct, 2), "overflow_solids_pct": round(slime.solids_pct, 2),
            "sand_p80_um": round(sand.p80_um, 1), "overflow_p80_um": round(slime.p80_um, 1),
            "feed_fe_pct": round(a_in["fe_pct"], 2), "sand_fe_pct": round(a_s["fe_pct"], 2),
            "overflow_fe_pct": round(a_o["fe_pct"], 2),
            "overflow_al2o3_pct": round(a_o["al2o3_pct"], 2),
            "fe_to_sand_pct": round(100 * sand.fe_tph / max(feed.fe_tph, 1e-9), 2),
            "power_kw": round(power, 1), "installed_kw": installed_kw}
    return sand, slime, info


# ---------------------------------------------------------------------------------------------
def spiral_concentrator(feed: Stream, *, n_starts: int, turns: float, diameter_m: float,
                        feed_solids_pct_target: float, wash_water_m3_h: float,
                        conc_splitter: float, middling_splitter: float,
                        feed_tph_per_start: float = 2.0) -> tuple[Stream, Stream, Stream, dict]:
    """Spiral concentrator with three products. Returns (concentrate, middling, tailing, info).

    Flowing-film separation down a helical trough: heavy particles migrate to the inner radius,
    light ones are swept out. The two splitter positions (as a fraction of trough width from the
    inside) cut the band into concentrate, middling and tailing. Performance falls away above
    about 2 mm — the particle no longer follows the film — and below about 75 um, where the film
    is thicker than the particle and drag dominates.

    The middling is not waste: in this flowsheet it is retreated on the shaking tables, which is
    the classical way to recover the composites a spiral cannot cut cleanly.
    """
    sgp = feed.particle_sg
    capacity = n_starts * feed_tph_per_start
    load = feed.solids_tph / max(capacity, 1e-6)
    solids_pct = float(np.clip(feed_solids_pct_target, 15.0, 45.0))
    wash = max(wash_water_m3_h, 0.0) / max(n_starts, 1)

    # sharpness improves with turns and wash water, degrades when overloaded
    ep_base = 0.34 * (5.0 / max(turns, 3.0)) ** 0.45 * (1.0 + 0.55 * max(load - 1.0, 0.0)) \
        * (1.0 - 0.18 * np.tanh(wash / 1.2)) * (1.0 + 0.012 * abs(solids_pct - 28.0))
    ep = _ep_by_size(float(ep_base), d_ref_um=260.0, exponent=0.95, floor=0.60)
    ep = np.clip(ep, 0.12, 4.0)

    # cut densities from the splitter positions (inner = heavy)
    cs = float(np.clip(conc_splitter, 0.05, 0.60))
    ms = float(np.clip(max(middling_splitter, cs + 0.05), 0.15, 0.90))
    sg_conc = float(np.clip(5.05 - 3.3 * cs, 3.05, 4.95))
    sg_mid = float(np.clip(5.05 - 3.3 * ms, 2.75, sg_conc - 0.12))

    window = size_window(62.0, 2400.0, lo_sharp=1.9, hi_sharp=2.6)
    to_conc = density_partition(sgp, sg_conc, ep) * window[:, None]
    to_conc_or_mid = density_partition(sgp, sg_mid, ep) * window[:, None]
    to_conc_or_mid = np.maximum(to_conc_or_mid, to_conc)
    # fines and oversize outside the window are swept to the tailing with the film
    fines_entrain = np.clip(1.0 - window, 0.0, 1.0)[:, None] * 0.06
    to_conc = np.clip(to_conc + fines_entrain, 0.0, 1.0)
    to_conc_or_mid = np.clip(to_conc_or_mid + fines_entrain * 1.8, 0.0, 1.0)

    total_water = feed.water_tph + max(wash_water_m3_h, 0.0)
    feed_w = feed.copy(water_tph=total_water)
    conc, rest = split(feed_w, to_conc, 0.18, ("spiral_conc", "_rest"), goethite_bias=0.97, alumina_bias=0.80)
    rel_mid = np.where(to_conc_or_mid < 1.0 - 1e-9,
                       np.clip((to_conc_or_mid - to_conc) / np.maximum(1.0 - to_conc, 1e-9), 0.0, 1.0), 0.0)
    mid, tail = split(rest, rel_mid, 0.30, ("spiral_middling", "spiral_tailing"),
                      goethite_bias=1.0, alumina_bias=0.92)
    a_in, a_c, a_m, a_t = feed.assay(), conc.assay(), mid.assay(), tail.assay()
    info = {"n_starts": n_starts, "turns": turns, "diameter_m": diameter_m,
            "capacity_tph": round(capacity, 2), "load_fraction": round(load, 3),
            "feed_solids_pct": round(solids_pct, 2), "wash_water_m3_h": round(max(wash_water_m3_h, 0.0), 2),
            "conc_splitter": round(cs, 3), "middling_splitter": round(ms, 3),
            "cut_sg_conc": round(sg_conc, 3), "cut_sg_middling": round(sg_mid, 3),
            "ep_at_500um": round(float(np.interp(500.0, GEO_MEAN_UM[::-1], ep[::-1])), 3),
            "ep_at_100um": round(float(np.interp(100.0, GEO_MEAN_UM[::-1], ep[::-1])), 3),
            "feed_tph": round(feed.solids_tph, 2), "conc_tph": round(conc.solids_tph, 2),
            "middling_tph": round(mid.solids_tph, 2), "tailing_tph": round(tail.solids_tph, 2),
            "conc_yield_pct": round(100 * conc.solids_tph / max(feed.solids_tph, 1e-6), 2),
            "feed_fe_pct": round(a_in["fe_pct"], 2), "conc_fe_pct": round(a_c["fe_pct"], 2),
            "middling_fe_pct": round(a_m["fe_pct"], 2), "tail_fe_pct": round(a_t["fe_pct"], 2),
            "conc_sio2_pct": round(a_c["sio2_pct"], 2), "conc_al2o3_pct": round(a_c["al2o3_pct"], 2),
            "fe_recovery_pct": round(100 * conc.fe_tph / max(feed.fe_tph, 1e-9), 2),
            "fe_to_middling_pct": round(100 * mid.fe_tph / max(feed.fe_tph, 1e-9), 2),
            "upgrade_ratio": round(a_c["fe_pct"] / max(a_in["fe_pct"], 1e-6), 3)}
    return conc, mid, tail, info


# ---------------------------------------------------------------------------------------------
def shaking_table(feed: Stream, *, n_decks: int, deck_area_m2: float, slope_deg: float,
                  stroke_mm: float, frequency_rpm: float, wash_water_m3_h: float,
                  conc_cut: float, feed_tph_per_deck: float = 1.1,
                  installed_kw: float = 2.2) -> tuple[Stream, Stream, Stream, dict]:
    """Wilfley-type shaking table. Returns (concentrate, middling, tailing, info).

    The sharpest gravity device in the plant, and the most size-sensitive: the asymmetric deck
    motion fans the feed into a band by density *and* size, so a table only performs on a narrow,
    closely sized, deslimed feed — which is exactly what it gets here, the spiral middling.

    Capacity is low (about 1 t/h per deck), so tables are installed in banks and used as a
    cleaner rather than a rougher.
    """
    sgp = feed.particle_sg
    capacity = n_decks * feed_tph_per_deck
    load = feed.solids_tph / max(capacity, 1e-6)
    stroke = float(np.clip(stroke_mm, 8.0, 30.0))
    freq = float(np.clip(frequency_rpm, 180.0, 340.0))
    slope = float(np.clip(slope_deg, 1.0, 8.0))
    wash = max(wash_water_m3_h, 0.0) / max(n_decks, 1)

    ep_base = 0.135 * (1.0 + 0.70 * max(load - 1.0, 0.0)) * (1.0 + 0.09 * abs(slope - 3.2)) \
        * (1.0 + 0.045 * abs(stroke * freq / 1000.0 - 4.4)) * (1.0 - 0.15 * np.tanh(wash / 0.35))
    ep = _ep_by_size(float(ep_base), d_ref_um=95.0, exponent=0.85, floor=0.70)
    ep = np.clip(ep, 0.05, 4.0)

    cc = float(np.clip(conc_cut, 0.10, 0.70))
    sg_conc = float(np.clip(5.05 - 2.9 * cc, 3.2, 4.95))
    sg_mid = float(np.clip(sg_conc - 0.55, 2.8, sg_conc - 0.1))
    window = size_window(38.0, 1800.0, lo_sharp=2.2, hi_sharp=2.8)

    to_conc = density_partition(sgp, sg_conc, ep) * window[:, None]
    to_conc_or_mid = np.maximum(density_partition(sgp, sg_mid, ep) * window[:, None], to_conc)
    slime_loss = np.clip(1.0 - window, 0.0, 1.0)[:, None] * 0.04
    to_conc = np.clip(to_conc + slime_loss, 0.0, 1.0)
    to_conc_or_mid = np.clip(to_conc_or_mid + slime_loss * 1.6, 0.0, 1.0)

    total_water = feed.water_tph + max(wash_water_m3_h, 0.0)
    feed_w = feed.copy(water_tph=total_water)
    conc, rest = split(feed_w, to_conc, 0.16, ("table_conc", "_rest"), goethite_bias=0.98, alumina_bias=0.72)
    rel_mid = np.where(to_conc_or_mid < 1.0 - 1e-9,
                       np.clip((to_conc_or_mid - to_conc) / np.maximum(1.0 - to_conc, 1e-9), 0.0, 1.0), 0.0)
    mid, tail = split(rest, rel_mid, 0.32, ("table_middling", "table_tailing"))
    a_in, a_c, a_t = feed.assay(), conc.assay(), tail.assay()
    power = installed_kw * n_decks * float(np.clip(0.5 + 0.4 * load, 0.3, 1.0))
    info = {"n_decks": n_decks, "deck_area_m2": round(deck_area_m2, 2),
            "capacity_tph": round(capacity, 2), "load_fraction": round(load, 3),
            "slope_deg": round(slope, 2), "stroke_mm": round(stroke, 1), "frequency_rpm": round(freq, 1),
            "wash_water_m3_h": round(max(wash_water_m3_h, 0.0), 2),
            "cut_sg_conc": round(sg_conc, 3), "cut_sg_middling": round(sg_mid, 3),
            "ep_at_200um": round(float(np.interp(200.0, GEO_MEAN_UM[::-1], ep[::-1])), 3),
            "ep_at_75um": round(float(np.interp(75.0, GEO_MEAN_UM[::-1], ep[::-1])), 3),
            "feed_tph": round(feed.solids_tph, 2), "conc_tph": round(conc.solids_tph, 2),
            "middling_tph": round(mid.solids_tph, 2), "tailing_tph": round(tail.solids_tph, 2),
            "feed_fe_pct": round(a_in["fe_pct"], 2), "conc_fe_pct": round(a_c["fe_pct"], 2),
            "tail_fe_pct": round(a_t["fe_pct"], 2), "conc_sio2_pct": round(a_c["sio2_pct"], 2),
            "conc_al2o3_pct": round(a_c["al2o3_pct"], 2),
            "conc_yield_pct": round(100 * conc.solids_tph / max(feed.solids_tph, 1e-6), 2),
            "fe_recovery_pct": round(100 * conc.fe_tph / max(feed.fe_tph, 1e-9), 2),
            "upgrade_ratio": round(a_c["fe_pct"] / max(a_in["fe_pct"], 1e-6), 3),
            "power_kw": round(power, 2)}
    return conc, mid, tail, info


def partition_curve(sg50: float, ep_value: float, sg_lo: float = 2.6, sg_hi: float = 5.2,
                    points: int = 28) -> list[dict]:
    """Tromp curve for plotting: partition to sinks against particle density."""
    sgs = np.linspace(sg_lo, sg_hi, points)
    part = 1.0 / (1.0 + np.exp(-LN3 * (sgs - sg50) / max(ep_value, 1e-3)))
    return [{"sg": round(float(s), 3), "to_sinks_pct": round(float(100 * p), 2)}
            for s, p in zip(sgs, part)]
