"""Model identification for the supervisory controller.

The controller does not get a model from a step-test campaign; it gets one from the twin. Each
manipulated variable is perturbed about the current operating point, the flowsheet is re-solved,
and the resulting steady-state gains are assembled into a matrix. Residence times through the
affected units then set a first-order-plus-dead-time dynamic for every pair.

That has a practical consequence worth stating: the model is re-identified whenever the ore
changes, so the controller does not inherit gains fitted to an ore type the plant stopped
treating months ago — which is the usual reason APC on a beneficiation plant degrades.

For a gravity plant the dynamics are fast by the standards of a flotation or grinding circuit.
Jig beds restratify in a minute or two, spiral bands respond in seconds, and the long poles are
the scrubber (a few minutes of residence) and the tailings thickener (tens of minutes). The
dead times are dominated by conveyor and pump transport, not by process lags.
"""
from __future__ import annotations

import time

import numpy as np

from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.twin.circuit import solve

#: manipulated variables exposed to the controller, with engineering and move limits
MVS: list[dict] = [
    {"key": "rom_feed_tph", "label": "ROM feed rate", "unit": "t/h", "lo": 350.0, "hi": 900.0,
     "max_move": 15.0, "cost": 2.2, "area": "100 Crushing", "tag": "101_WIC_001"},
    {"key": "secondary_css_mm", "label": "Secondary crusher CSS", "unit": "mm", "lo": 22.0, "hi": 55.0,
     "max_move": 2.0, "cost": 1.4, "area": "100 Crushing", "tag": "102_HIC_004"},
    {"key": "scrubber_speed_pct_critical", "label": "Scrubber drum speed", "unit": "% Cs", "lo": 20.0,
     "hi": 40.0, "max_move": 1.5, "cost": 0.4, "area": "200 Scrubbing", "tag": "201_SIC_010"},
    {"key": "scrubber_water_m3_h", "label": "Scrubber water", "unit": "m3/h", "lo": 180.0, "hi": 820.0,
     "max_move": 35.0, "cost": 0.3, "area": "200 Scrubbing", "tag": "201_FIC_011"},
    {"key": "trommel_aperture_mm", "label": "Trommel lump cut size", "unit": "mm", "lo": 6.0, "hi": 18.0,
     "max_move": 1.0, "cost": 3.0, "area": "200 Scrubbing", "tag": "202_HS_014"},
    {"key": "lump_jig_cut_sg", "label": "Lump jig cut density", "unit": "SG", "lo": 3.2, "hi": 4.8,
     "max_move": 0.10, "cost": 0.5, "area": "300 Lump jigging", "tag": "301_DIC_020"},
    {"key": "lump_jig_hutch_water_m3_h", "label": "Lump jig hutch water", "unit": "m3/h", "lo": 90.0,
     "hi": 520.0, "max_move": 25.0, "cost": 0.3, "area": "300 Lump jigging", "tag": "301_FIC_021"},
    {"key": "lump_jig_bed_depth_mm", "label": "Lump jig bed depth", "unit": "mm", "lo": 130.0, "hi": 380.0,
     "max_move": 15.0, "cost": 0.6, "area": "300 Lump jigging", "tag": "301_LIC_022"},
    {"key": "lump_jig_stroke_mm", "label": "Lump jig stroke", "unit": "mm", "lo": 12.0, "hi": 40.0,
     "max_move": 1.5, "cost": 0.8, "area": "300 Lump jigging", "tag": "301_HIC_023"},
    {"key": "classifier_dilution_water_m3_h", "label": "Classifier dilution water", "unit": "m3/h",
     "lo": 100.0, "hi": 700.0, "max_move": 30.0, "cost": 0.3, "area": "400 Classification",
     "tag": "401_FIC_030"},
    {"key": "classifier_weir_height_m", "label": "Classifier weir height", "unit": "m", "lo": 0.18,
     "hi": 0.50, "max_move": 0.03, "cost": 0.7, "area": "400 Classification", "tag": "401_LIC_031"},
    {"key": "fines_jig_cut_sg", "label": "Fines jig cut density", "unit": "SG", "lo": 3.2, "hi": 4.7,
     "max_move": 0.10, "cost": 0.5, "area": "500 Fines jigging", "tag": "501_DIC_040"},
    {"key": "spiral_cyclone_pressure_kpa", "label": "Spiral cyclone pressure", "unit": "kPa", "lo": 75.0,
     "hi": 190.0, "max_move": 6.0, "cost": 0.4, "area": "600 Spirals", "tag": "601_PIC_050"},
    {"key": "spiral_feed_solids_pct", "label": "Spiral feed density", "unit": "% solids", "lo": 20.0,
     "hi": 38.0, "max_move": 1.2, "cost": 0.4, "area": "600 Spirals", "tag": "601_DIC_051"},
    {"key": "spiral_conc_splitter", "label": "Spiral concentrate splitter", "unit": "fraction", "lo": 0.12,
     "hi": 0.50, "max_move": 0.03, "cost": 0.6, "area": "600 Spirals", "tag": "601_HIC_052"},
    {"key": "spiral_middling_splitter", "label": "Spiral middling splitter", "unit": "fraction", "lo": 0.25,
     "hi": 0.80, "max_move": 0.03, "cost": 0.6, "area": "600 Spirals", "tag": "601_HIC_053"},
    {"key": "spiral_wash_water_m3_h", "label": "Spiral wash water", "unit": "m3/h", "lo": 40.0, "hi": 280.0,
     "max_move": 15.0, "cost": 0.3, "area": "600 Spirals", "tag": "601_FIC_054"},
    {"key": "table_conc_cut", "label": "Table concentrate cut", "unit": "fraction", "lo": 0.15, "hi": 0.60,
     "max_move": 0.03, "cost": 0.5, "area": "700 Tables", "tag": "701_HIC_060"},
    {"key": "table_slope_deg", "label": "Table deck slope", "unit": "deg", "lo": 1.8, "hi": 6.0,
     "max_move": 0.25, "cost": 0.7, "area": "700 Tables", "tag": "701_HIC_061"},
    {"key": "deslime_cyclone_pressure_kpa", "label": "Desliming cyclone pressure", "unit": "kPa",
     "lo": 95.0, "hi": 240.0, "max_move": 8.0, "cost": 0.4, "area": "800 WHIMS", "tag": "801_PIC_070"},
    {"key": "whims_field_tesla", "label": "WHIMS field intensity", "unit": "T", "lo": 0.55, "hi": 1.55,
     "max_move": 0.06, "cost": 0.9, "area": "800 WHIMS", "tag": "801_JIC_071"},
    {"key": "whims_wash_water_m3_h", "label": "WHIMS wash water", "unit": "m3/h", "lo": 35.0, "hi": 240.0,
     "max_move": 12.0, "cost": 0.3, "area": "800 WHIMS", "tag": "801_FIC_072"},
    {"key": "tails_flocculant_g_t", "label": "Tailings flocculant", "unit": "g/t", "lo": 12.0, "hi": 80.0,
     "max_move": 4.0, "cost": 1.1, "area": "900 Tailings", "tag": "901_FIC_080"},
    {"key": "reclaim_water_fraction", "label": "Pond reclaim fraction", "unit": "fraction", "lo": 0.50,
     "hi": 0.94, "max_move": 0.03, "cost": 0.2, "area": "900 Tailings", "tag": "901_FIC_081"},
]
MV_BY_KEY = {m["key"]: m for m in MVS}

#: controlled variables, with operating zones rather than single set-points
CVS: list[dict] = [
    {"key": "lump_al2o3_pct", "label": "Lump ore alumina", "unit": "% Al2O3", "target": 2.2,
     "lo": 1.0, "hi": 2.5, "weight": 9.0, "priority": 1, "tag": "302_AIC_025"},
    {"key": "lump_fe_pct", "label": "Lump ore Fe grade", "unit": "% Fe", "target": 62.5,
     "lo": 61.5, "hi": 66.0, "weight": 7.0, "priority": 1, "tag": "302_AIC_024"},
    {"key": "fines_fe_pct", "label": "Sinter fines Fe grade", "unit": "% Fe", "target": 64.5,
     "lo": 63.0, "hi": 67.0, "weight": 6.0, "priority": 2, "tag": "702_AIC_064"},
    {"key": "fe_recovery_pct", "label": "Plant Fe recovery", "unit": "%", "target": 92.0,
     "lo": 88.0, "hi": 97.0, "weight": 5.0, "priority": 2, "tag": "901_KIC_090"},
    {"key": "lump_yield_pct", "label": "Lump yield", "unit": "%", "target": 37.0,
     "lo": 28.0, "hi": 46.0, "weight": 4.0, "priority": 3, "tag": "302_KIC_026"},
    {"key": "throughput_tph", "label": "Plant throughput", "unit": "t/h", "target": 600.0,
     "lo": 420.0, "hi": 760.0, "weight": 6.5, "priority": 3, "tag": "101_WIC_001"},
    {"key": "energy_kwh_t", "label": "Specific energy", "unit": "kWh/t", "target": 2.4,
     "lo": 1.4, "hi": 3.2, "weight": 3.0, "priority": 4, "tag": "902_JI_091"},
    {"key": "tailings_fe_pct", "label": "Tailings Fe grade", "unit": "% Fe", "target": 19.0,
     "lo": 10.0, "hi": 24.0, "weight": 3.5, "priority": 4, "tag": "901_AI_082"},
]
CV_BY_KEY = {c["key"]: c for c in CVS}

#: first-order dynamics per MV: (dominant time constant, transport dead time) in minutes
MV_DYNAMICS: dict[str, tuple[float, float]] = {
    "rom_feed_tph": (7.0, 3.5),
    "secondary_css_mm": (9.0, 4.5),
    "scrubber_speed_pct_critical": (4.5, 1.5),
    "scrubber_water_m3_h": (3.5, 1.2),
    "trommel_aperture_mm": (6.0, 2.5),
    "lump_jig_cut_sg": (2.5, 0.8),
    "lump_jig_hutch_water_m3_h": (2.0, 0.6),
    "lump_jig_bed_depth_mm": (3.5, 1.0),
    "lump_jig_stroke_mm": (2.2, 0.6),
    "classifier_dilution_water_m3_h": (5.0, 1.8),
    "classifier_weir_height_m": (6.5, 2.0),
    "fines_jig_cut_sg": (2.5, 1.0),
    "spiral_cyclone_pressure_kpa": (2.0, 0.8),
    "spiral_feed_solids_pct": (3.0, 1.2),
    "spiral_conc_splitter": (1.2, 0.5),
    "spiral_middling_splitter": (1.2, 0.5),
    "spiral_wash_water_m3_h": (1.5, 0.5),
    "table_conc_cut": (1.8, 0.7),
    "table_slope_deg": (2.5, 0.9),
    "deslime_cyclone_pressure_kpa": (2.2, 0.9),
    "whims_field_tesla": (1.5, 0.6),
    "whims_wash_water_m3_h": (1.5, 0.5),
    "tails_flocculant_g_t": (14.0, 5.0),
    "reclaim_water_fraction": (25.0, 8.0),
}


def _kpis(fs: FlowsheetConfig, ore: OreConfig, op: OperatingConfig, ec: EconomicsConfig,
          cv_keys: list[str]) -> dict[str, float]:
    r = solve(fs, ore, op, ec, iterations=16)
    return {c: float(r["kpis"][c]) for c in cv_keys}


def identify(flowsheet: FlowsheetConfig, ore: OreConfig, operating: OperatingConfig,
             economics: EconomicsConfig, *, mv_keys: list[str] | None = None,
             cv_keys: list[str] | None = None, step_frac: float = 0.03) -> dict:
    """Central-difference identification of the gain matrix, plus FOPDT dynamics and an RGA."""
    t0 = time.perf_counter()
    mv_keys = mv_keys or [m["key"] for m in MVS]
    cv_keys = cv_keys or [c["key"] for c in CVS]
    base = _kpis(flowsheet, ore, operating, economics, cv_keys)
    gains = np.zeros((len(cv_keys), len(mv_keys)))
    models: dict[str, dict] = {}
    for j, mv in enumerate(mv_keys):
        spec = MV_BY_KEY[mv]
        u0 = float(getattr(operating, mv))
        step = max(step_frac * max(abs(u0), 1e-6), 0.35 * spec["max_move"])
        hi = float(np.clip(u0 + step, spec["lo"], spec["hi"]))
        lo = float(np.clip(u0 - step, spec["lo"], spec["hi"]))
        tau0, dead0 = MV_DYNAMICS.get(mv, (5.0, 2.0))
        if hi - lo < 1e-9:
            # the operating point sits on this variable's limit, so it has no usable gain here;
            # record it explicitly rather than leaving a hole in the model matrix
            for i, cv in enumerate(cv_keys):
                models[f"{cv}|{mv}"] = {"cv": cv, "mv": mv, "gain": 0.0, "tau_min": tau0,
                                        "dead_time_min": dead0, "at_limit": True,
                                        "units": f"{CV_BY_KEY[cv]['unit']} per {MV_BY_KEY[mv]['unit']}"}
            continue
        k_hi = _kpis(flowsheet, ore, operating.model_copy(update={mv: hi}), economics, cv_keys)
        k_lo = _kpis(flowsheet, ore, operating.model_copy(update={mv: lo}), economics, cv_keys)
        tau, dead = MV_DYNAMICS.get(mv, (5.0, 2.0))
        for i, cv in enumerate(cv_keys):
            g = (k_hi[cv] - k_lo[cv]) / (hi - lo)
            gains[i, j] = g
            models[f"{cv}|{mv}"] = {"cv": cv, "mv": mv, "gain": round(float(g), 6),
                                    "tau_min": tau, "dead_time_min": dead,
                                    "units": f"{CV_BY_KEY[cv]['unit']} per {MV_BY_KEY[mv]['unit']}"}
    try:
        rga = gains * np.linalg.pinv(gains).T
        cond = float(np.linalg.cond(gains))
    except np.linalg.LinAlgError:                                    # pragma: no cover
        rga = np.zeros_like(gains)
        cond = float("inf")
    return {"mv_keys": mv_keys, "cv_keys": cv_keys, "gain_matrix": gains.tolist(),
            "rga_matrix": np.nan_to_num(rga).tolist(), "condition_number": round(cond, 2),
            "models": models, "base_kpis": {k: round(v, 5) for k, v in base.items()},
            "operating_point": {m: float(getattr(operating, m)) for m in mv_keys},
            "identified_s": round(time.perf_counter() - t0, 2),
            "note": "Gains are central differences on the first-principles twin at the current "
                    "operating point; dynamics come from unit residence and transport times."}


def step_response(gain: float, tau_min: float, dead_min: float, horizon_min: float = 60.0,
                  dt_min: float = 1.0) -> list[float]:
    """Unit-step response of the identified FOPDT model."""
    t = np.arange(0.0, horizon_min + dt_min, dt_min)
    y = np.where(t <= dead_min, 0.0, gain * (1.0 - np.exp(-(t - dead_min) / max(tau_min, 1e-6))))
    return [float(v) for v in y]
