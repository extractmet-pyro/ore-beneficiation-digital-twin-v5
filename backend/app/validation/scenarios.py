"""Operating envelope and the scenario catalogue.

Two questions an acceptance test has to answer before any number means anything:

* **Over what operating conditions is the twin claimed to be accurate?** That is the envelope.
  Outside it the twin still runs and still answers, but the accuracy criteria do not apply and
  the twin says so rather than quietly pretending otherwise.
* **Which situations will it be demonstrated on?** That is the scenario catalogue. A model that
  is only ever tested at the design point has not been tested.

Each scenario carries an *expected behaviour* as well as a numerical criterion, because a
model can hit every tolerance and still be wrong in a way a metallurgist would spot in a
second — a cut density that moves the wrong way, a recovery that rises when it should fall.
Those directional checks are part of acceptance, and they are machine-checkable.
"""
from __future__ import annotations

from typing import Any

#: The claimed envelope. Outside any of these the twin reports "outside validated envelope".
ENVELOPE: list[dict[str, Any]] = [
    {"variable": "rom_feed_tph", "label": "ROM throughput", "unit": "t/h", "lo": 380.0, "hi": 880.0,
     "basis": "70 % to 110 % of nameplate across the three reference plants"},
    {"variable": "fe_head_pct", "label": "Head Fe", "unit": "% Fe", "lo": 48.0, "hi": 60.0,
     "basis": "Ore-body block model P5 to P95"},
    {"variable": "al2o3_head_pct", "label": "Head alumina", "unit": "% Al2O3", "lo": 2.5, "hi": 8.0,
     "basis": "Ore-body block model P5 to P95"},
    {"variable": "sio2_head_pct", "label": "Head silica", "unit": "% SiO2", "lo": 5.0, "hi": 14.0,
     "basis": "Ore-body block model P5 to P95"},
    {"variable": "clay_share", "label": "Detachable clay share", "unit": "fraction", "lo": 0.25,
     "hi": 0.80, "basis": "Attrition testwork across the mining areas"},
    {"variable": "liberation_d50_um", "label": "Liberation d50", "unit": "um", "lo": 9000.0,
     "hi": 32000.0, "basis": "Mineralogical characterisation"},
    {"variable": "lump_jig_cut_sg", "label": "Lump jig cut density", "unit": "SG", "lo": 3.2, "hi": 4.6,
     "basis": "Operable range of the installed jig"},
    {"variable": "whims_field_tesla", "label": "WHIMS field", "unit": "T", "lo": 0.40, "hi": 1.60,
     "basis": "Machine rating"},
    {"variable": "scrubber_water_m3_h", "label": "Scrubber water", "unit": "m3/h", "lo": 220.0,
     "hi": 680.0, "basis": "Pump and launder capacity"},
]


def envelope_check(values: dict[str, float]) -> dict[str, Any]:
    """Classify an operating point against the claimed envelope."""
    rows, outside = [], []
    for e in ENVELOPE:
        v = values.get(e["variable"])
        if v is None:
            rows.append({**e, "value": None, "state": "not_supplied"})
            continue
        v = float(v)
        span = max(e["hi"] - e["lo"], 1e-9)
        if v < e["lo"]:
            st, by = "below", round(100 * (e["lo"] - v) / span, 2)
        elif v > e["hi"]:
            st, by = "above", round(100 * (v - e["hi"]) / span, 2)
        else:
            st, by = "inside", 0.0
        pos = round(100 * (v - e["lo"]) / span, 1)
        rows.append({**e, "value": round(v, 4), "state": st, "outside_by_pct_of_span": by,
                     "position_pct": pos,
                     "near_edge": bool(st == "inside" and (pos < 8 or pos > 92))})
        if st != "inside":
            outside.append(e["variable"])
    return {
        "inside_envelope": not outside, "variables_outside": outside,
        "near_edge": [r["variable"] for r in rows if r.get("near_edge")],
        "rows": rows,
        "statement": ("Operating point is inside the validated envelope; the acceptance "
                      "tolerances apply." if not outside else
                      "Operating point is outside the validated envelope on "
                      f"{', '.join(outside)}. The twin still solves, but the accuracy criteria "
                      "do not apply and results are reported as indicative."),
    }


def _s(sid, name, kind, purpose, setup, kpis, expected, *, duration="8 h", data="Shift composite "
       "assays plus hourly historian", criteria=None, note=""):
    return {"scenario_id": sid, "name": name, "kind": kind, "purpose": purpose,
            "setup": setup, "kpis_judged": kpis, "expected_behaviour": expected,
            "duration": duration, "data_required": data,
            "numerical_criteria": criteria or "Class A and B KPI criteria for the KPIs judged.",
            "note": note}


#: The scenarios the twin is demonstrated on. ``kind`` separates the three things a test can
#: establish: that the model is *accurate*, that it *behaves* correctly, and that it *fails
#: safely*.
SCENARIOS: list[dict[str, Any]] = [
    _s("S01_base", "Base case, design ore at design rate", "accuracy",
       "Establish accuracy at the operating point the plant spends most of its time at.",
       {"rom_feed_tph": 600.0, "fe_head_pct": 54.25, "clay_share": 0.55},
       ["lump_fe_pct", "lump_al2o3_pct", "fines_fe_pct", "fe_recovery_pct", "mass_yield_pct",
        "throughput_tph"],
       "All Class A KPIs within tolerance; no significant bias on the paired t-test.",
       duration="30 days of plant data"),
    _s("S02_low_grade", "Low head grade", "accuracy",
       "Accuracy when the feed is poorer than design, which is where yield decisions are made.",
       {"fe_head_pct": 49.0, "sio2_head_pct": 13.0},
       ["lump_fe_pct", "fe_recovery_pct", "tailings_fe_pct", "mass_yield_pct"],
       "Recovery and yield both fall; tailings grade rises; product grade is held by yield loss "
       "rather than by upgrade."),
    _s("S03_high_clay", "High-clay, high-alumina feed", "accuracy",
       "The commercially important hard case: alumina control on clay-bearing ore.",
       {"clay_share": 0.72, "al2o3_head_pct": 7.2},
       ["lump_al2o3_pct@high_clay", "lump_fe_pct", "fines_fe_pct"],
       "Lump alumina rises; scrubber duty becomes the dominant lever on it, ahead of jig cut "
       "density; desliming load rises.",
       note="Judged against the wider high-clay criterion, not the base-case one."),
    _s("S04_hard_banded", "Hard, coarsely banded ore", "accuracy",
       "Accuracy when comminution rather than separation is the constraint.",
       {"axb": 42.0, "liberation_d50_um": 28000.0, "lump_friability": 0.12},
       ["throughput_tph", "lump_tph", "energy_kwh_t", "mass_yield_pct"],
       "Recrush circulating load rises; specific energy rises; lump yield rises as the ore "
       "resists degradation."),
    _s("S05_rate_up", "Throughput step up to 110 % of nameplate", "behaviour",
       "Does the model find the real bottleneck, and does it find the right one?",
       {"rom_feed_tph": 715.0},
       ["throughput_tph", "fe_recovery_pct", "mass_yield_pct"],
       "At least one constraint becomes binding; separation sharpness falls as loading rises; "
       "recovery falls. The binding constraint predicted by the twin matches the plant's own "
       "experience of what limits it.",
       duration="4 h step test"),
    _s("S06_turndown", "Turn-down to 70 % of nameplate", "behaviour",
       "Behaviour at low rate, where many models silently extrapolate.",
       {"rom_feed_tph": 420.0},
       ["fe_recovery_pct", "energy_kwh_t", "classifier_d50_um"],
       "Specific energy rises; classifier cut becomes finer; separation sharpness improves.",
       duration="4 h step test"),
    _s("S07_scrubber_step", "Scrubber drum speed step", "behaviour",
       "Direct test of the plant's primary quality handle.",
       {"scrubber_speed_pct_critical": [24.0, 38.0]},
       ["lump_al2o3_pct", "lump_fe_pct"],
       "Lump alumina falls monotonically as drum speed, and therefore attrition, rises; the sign "
       "and the order of magnitude match the plant's own step test.",
       duration="2 x 4 h", criteria="Directional agreement plus gain within a factor of two of "
                                    "the measured plant gain."),
    _s("S07b_scrubber_dilution", "Scrubber dilution water step", "behaviour",
       "A counter-intuitive response that a plant frequently gets backwards, and therefore one "
       "of the more valuable things to confirm the twin has right.",
       {"scrubber_water_m3_h": [294.0, 546.0]},
       ["lump_al2o3_pct"],
       "Lump alumina RISES as dilution water is added. A scrubber cleans by particle-on-particle "
       "attrition, which needs a dense pulp; extra water lowers the pulp density and shortens the "
       "residence time, so less clay is detached. Operators reaching for more water to 'wash "
       "harder' make the product worse.",
       duration="2 x 4 h", criteria="Directional agreement with the plant's own water step test.",
       note="If a twin shows alumina falling here it has modelled a washing plant, not a scrubber."),
    _s("S08_jig_cut", "Jig cut density step", "behaviour",
       "The classic grade-recovery trade-off, measured rather than asserted.",
       {"lump_jig_cut_sg": [3.9, 4.4]},
       ["lump_fe_pct", "lump_yield_pct", "fe_recovery_pct"],
       "Raising the cut density raises lump grade and lowers lump yield; the grade-recovery "
       "curve traced by the twin passes through the plant's measured operating points.",
       duration="2 x 4 h"),
    _s("S09_whims_field", "WHIMS field strength step", "behaviour",
       "Separation response on the fines side of the plant.",
       {"whims_field_tesla": [0.60, 1.30]},
       ["pellet_fines_fe_pct", "fe_recovery_pct", "tailings_fe_pct"],
       "Mass and iron recovery to the magnetic product rise steeply with field and the magnetic "
       "tailing grade falls. On this circuit the concentrate grade does NOT fall materially, "
       "because the WHIMS feed has already been deslimed and its magnetics are well liberated: "
       "the extra material recovered at higher field is liberated haematite rather than "
       "middlings. The usual grade-recovery trade-off is weak here, and a twin that shows a "
       "strong one has mis-modelled the desliming stage upstream.",
       duration="2 x 4 h"),
    _s("S10_screen_blind", "Screen progressively blinding", "fault",
       "Does the twin detect a developing mechanical fault before the monthly balance does?",
       {"fault": "sizing_screen_efficiency_decay"},
       ["throughput_tph", "lump_tph"],
       "Model-plant residual on screen undersize grows steadily; the anomaly monitor raises the "
       "screen before the production figures move outside their normal range.",
       duration="7 days of historical data covering a known blinding event",
       criteria="Detection at least 24 h before the event was found by the plant, with no more "
                "than one false positive in the period."),
    _s("S11_analyser_drift", "On-stream analyser drift", "fault",
       "Does the twin identify the instrument rather than blame the process?",
       {"fault": "analyser_bias_ramp"},
       ["lump_fe_pct", "fines_fe_pct"],
       "Reconciliation flags the drifting tag as the suspect measurement; the twin's own "
       "prediction does not follow the drift; the fault is attributed to the instrument.",
       duration="14 days of historical data",
       criteria="Correct instrument identified; no corresponding change in the modelled process "
                "state."),
    _s("S12_recycle_upset", "Recrush circulating-load upset", "behaviour",
       "The recycle loop is the hardest part of the circuit to reason about without a model.",
       {"tertiary_css_mm": 14.0},
       ["throughput_tph", "lump_tph"],
       "Opening the recrush setting above the screen aperture floods the recycle: circulating "
       "load and tertiary crusher feed both rise sharply and non-linearly, and the twin still "
       "converges. Specific energy FALLS, because each tonne is crushed less hard even though "
       "more tonnes are handled - the recycle cost shows up as capacity, not as kWh per tonne.",
       duration="4 h"),
    _s("S13_water_limited", "Water-recycle constraint binding", "behaviour",
       "Plant behaviour when the water balance, not the ore, is the limit.",
       {"reclaim_water_fraction": 0.55},
       ["fresh_water_m3_h", "throughput_tph"],
       "Fresh-water make-up rises; the twin identifies the water constraint as binding before "
       "throughput is affected."),
    _s("S14_blend_change", "Blend change between two mining areas", "accuracy",
       "The common real disturbance: the feed changes, nothing on the plant does.",
       {"blend": "area_A_to_area_B over 6 h"},
       ["lump_al2o3_pct", "lump_fe_pct", "fe_recovery_pct"],
       "The twin tracks the transition with no set-point change, and the residual does not grow "
       "systematically through it.",
       duration="24 h spanning a known blend change"),
    _s("S15_outside_envelope", "Operating point outside the validated envelope", "fail_safe",
       "What the twin does when it is asked something it cannot answer.",
       {"fe_head_pct": 44.0, "clay_share": 0.85},
       ["lump_fe_pct", "lump_al2o3_pct"],
       "The twin solves and returns a result, labels it as outside the validated envelope, "
       "reports which variables are outside and by how much, and switches the hybrid correction "
       "off so the answer is purely mechanistic.",
       duration="single evaluation",
       criteria="Envelope flag raised, offending variables named, hybrid gate at zero. No "
                "accuracy criterion applies."),
    _s("S16_startup", "Start-up and shut-down transient", "excluded",
       "Stated explicitly as out of scope so that it cannot become a dispute later.",
       {"transient": "cold start to steady state"}, [],
       "Not modelled. The twin is a steady-state circuit model with a dynamic supervisory layer; "
       "it is not valid during start-up, shut-down or a plant trip, and reports no result for "
       "those periods rather than an unreliable one.",
       duration="n/a", data="n/a",
       criteria="Periods flagged and excluded from all accuracy statistics.",
       note="Declared a limitation, not a failure. Acceptance explicitly covers this exclusion."),
]


def scenario_index() -> dict[str, dict[str, Any]]:
    return {s["scenario_id"]: s for s in SCENARIOS}


def catalogue() -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for s in SCENARIOS:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    return {"envelope": ENVELOPE, "scenarios": SCENARIOS, "counts": {"total": len(SCENARIOS), **kinds},
            "kinds": {
                "accuracy": "Graded against the numerical KPI criteria.",
                "behaviour": "Graded on the direction and order of magnitude of the response, "
                             "against the plant's own step tests.",
                "fault": "Graded on detection and correct attribution.",
                "fail_safe": "Graded on the twin declining to answer rather than answering badly.",
                "excluded": "Declared out of scope, with the exclusion itself accepted."}}
