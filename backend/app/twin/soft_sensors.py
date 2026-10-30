"""Soft sensors: estimates of quantities the plant cannot measure continuously.

A gravity plant is instrument-poor by nature. Jig beds, spiral bands and table decks carry no
analysers, and product assays arrive from the laboratory hours after the shift that made them.
Each soft sensor here infers one of those quantities from measurements that *are* available,
carries its own uncertainty, and states how long the estimate stays valid — which is what allows
the control layer to use it and the data-quality gate to refuse it when its inputs are unhealthy.
"""
from __future__ import annotations

SOFT_SENSORS: list[dict] = [
    {"key": "lump_al2o3_pct", "label": "Lump ore alumina", "unit": "% Al2O3",
     "basis": "Scrubber residence time and power draw, trommel wash-water rate, jig bed condition "
              "and ROM clay index, calibrated against shift composites",
     "sigma": 0.18, "valid_window_min": 45, "drives": "Scrubber speed and water, trommel spray rate"},
    {"key": "lump_fe_pct", "label": "Lump ore Fe grade", "unit": "% Fe",
     "basis": "Jig cut density inferred from bed pressure and hutch-water balance, with the ROM "
              "head grade from the on-belt analyser",
     "sigma": 0.42, "valid_window_min": 30, "drives": "Lump jig cut density and bed depth"},
    {"key": "fines_fe_pct", "label": "Sinter fines Fe grade", "unit": "% Fe",
     "basis": "Weighted blend of the fines-jig, spiral and table concentrate streams from their "
              "densimeter and flow readings",
     "sigma": 0.38, "valid_window_min": 30, "drives": "Spiral splitter positions, table cut"},
    {"key": "jig_cut_sg", "label": "Lump jig cut density", "unit": "SG",
     "basis": "Bed pressure profile, pulsion energy and hutch-water flux",
     "sigma": 0.09, "valid_window_min": 12, "drives": "Hutch water, stroke, bed depth"},
    {"key": "classifier_d50_um", "label": "Classifier cut size", "unit": "um",
     "basis": "Overflow volumetric rate, weir height and pulp density, with the equal-settling "
              "correction for hematite",
     "sigma": 22.0, "valid_window_min": 20, "drives": "Dilution water, weir height, screw speed"},
    {"key": "spiral_feed_p80_um", "label": "Spiral feed top size (P80)", "unit": "um",
     "basis": "Cyclone pressure and feed density with the classifier cut estimate",
     "sigma": 38.0, "valid_window_min": 20, "drives": "Cyclone pressure, number of cyclones open"},
    {"key": "whims_feed_fe_pct", "label": "WHIMS feed Fe grade", "unit": "% Fe",
     "basis": "Desliming-cyclone underflow density and the slimes mass split",
     "sigma": 1.35, "valid_window_min": 40, "drives": "Desliming cyclone pressure, WHIMS field"},
    {"key": "slimes_fraction_pct", "label": "Slimes fraction of feed", "unit": "%",
     "basis": "Classifier overflow flow and density against the ROM weightometer",
     "sigma": 0.55, "valid_window_min": 25, "drives": "Scrubber duty, classifier dilution"},
]
SOFT_SENSOR_BY_KEY = {s["key"]: s for s in SOFT_SENSORS}


def estimate(result: dict) -> list[dict]:
    """Produce soft-sensor estimates from a solved circuit, each with its uncertainty."""
    k, u = result["kpis"], result["units"]
    raw = {
        "lump_al2o3_pct": k["lump_al2o3_pct"],
        "lump_fe_pct": k["lump_fe_pct"],
        "fines_fe_pct": k["fines_fe_pct"],
        "jig_cut_sg": u["lump_jig"].get("cut_sg_achieved"),
        "classifier_d50_um": u["spiral_classifier"].get("d50_quartz_um"),
        "spiral_feed_p80_um": u["spiral_cyclone"].get("overflow_p80_um"),
        "whims_feed_fe_pct": u["whims"].get("feed_fe_pct"),
        "slimes_fraction_pct": round(100.0 * u["spiral_classifier"].get("overflow_tph", 0.0)
                                     / max(k["throughput_tph"], 1e-6), 3),
    }
    out = []
    for spec in SOFT_SENSORS:
        v = raw.get(spec["key"])
        out.append({**spec, "value": None if v is None else round(float(v), 4),
                    "interval_95": None if v is None else
                    [round(float(v) - 1.96 * spec["sigma"], 4), round(float(v) + 1.96 * spec["sigma"], 4)]})
    return out
