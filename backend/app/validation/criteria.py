"""Measurable acceptance criteria for the digital twin.

This is the contractual heart of the validation layer: a table of numbers that decides, without
argument, whether the twin has been accepted. Three principles shape it.

**A model cannot be held to a tolerance tighter than the measurement it is judged against.**
Every criterion therefore carries the reference measurement's own uncertainty, and the tolerance
is set as a stated multiple of it. Asking for product alumina predicted to 0.02 % when the shift
composite assay itself repeats to 0.06 % is not rigour, it is a guarantee of a dispute.

**Not every variable carries the same commercial weight.** Criteria are graded. Class A
variables are the ones the product is sold on and the ones a failure would be argued over;
Class B are operational; Class C are indicative and are reported but do not gate acceptance.

**A criterion that cannot be evaluated is not a criterion.** Each entry names the measurement
basis, the averaging window, and the minimum sample count below which no verdict is given.
"""
from __future__ import annotations

from typing import Any

TOLERANCE_CLASSES: dict[str, dict[str, Any]] = {
    "A": {"name": "Contractual", "gates_acceptance": True,
          "definition": "Variables the product is sold on, or that a commercial dispute would "
                        "turn on. All Class A criteria must pass for acceptance.",
          "sigma_multiple": 1.5},
    "B": {"name": "Operational", "gates_acceptance": True,
          "definition": "Variables the plant is run on. All Class B criteria must pass, or be "
                        "accepted as marginal with a written concession.",
          "sigma_multiple": 2.0},
    "C": {"name": "Indicative", "gates_acceptance": False,
          "definition": "Reported for information and trend value. Do not gate acceptance.",
          "sigma_multiple": 3.0},
}


#: Which measures decide the verdict for each kind of variable.
#:
#: An assay is contracted in absolute percentage points - "maximum 2.5 % Al2O3, penalty per 0.1 %
#: above" - so its tolerance is absolute and a relative measure such as MAPE is reported but does
#: not gate: the same 0.09 % absolute error is 4 % on one plant's product and 6 % on another's,
#: and failing the second one for it would be an artefact of the arithmetic, not a finding about
#: the model.
#:
#: A tonnage is the opposite. An absolute tolerance in t/h cannot be carried from a 600 t/h plant
#: to an 820 t/h plant, so flows gate on the relative measure and their absolute errors are
#: reported for information.
GATING = {
    "assay": ["bias", "mae", "rmse", "r2", "coverage_95_pct"],
    "percentage": ["bias", "mae", "rmse", "r2", "coverage_95_pct"],
    "flow": ["mape_pct", "r2", "coverage_95_pct"],
    "rate": ["mape_pct", "r2"],
}


def _c(kpi, label, unit, cls, basis, sigma, *, max_bias, max_mae, max_rmse, max_mape=None,
       min_r2=None, min_coverage=90.0, max_theil=1.0, n_min=30, window="1 h average",
       scenarios=("all",), note="", kind="assay"):
    return {
        "kpi": kpi, "label": label, "unit": unit, "class": cls,
        "measurement_basis": basis, "reference_sigma": sigma,
        "limits": {"max_abs_bias": max_bias, "max_mae": max_mae, "max_rmse": max_rmse,
                   "max_mape_pct": max_mape, "min_r2": min_r2,
                   "min_coverage_95_pct": min_coverage, "max_theil_u2": max_theil},
        "tolerance_basis": (f"RMSE limit is {round(max_rmse / sigma, 2)} x the reference "
                            f"measurement's own 1-sigma repeatability of {sigma} {unit}."),
        "n_min": n_min, "window": window, "applies_in_scenarios": list(scenarios),
        "quantity_kind": kind, "gating_measures": list(GATING[kind]),
        "gating_note": ("Absolute measures decide; relative error is reported only."
                        if kind in ("assay", "percentage") else
                        "Relative error decides; absolute error is reported only, because an "
                        "absolute tonnage tolerance cannot be carried between plants of "
                        "different size."),
        "note": note,
    }


#: Per-KPI acceptance criteria.
KPI_CRITERIA: list[dict[str, Any]] = [
    _c("lump_fe_pct", "Lump ore Fe", "% Fe", "A",
       "Shift composite sample, laboratory XRF, against the shift's twin average", 0.25,
       max_bias=0.30, max_mae=0.45, max_rmse=0.60, max_mape=1.0, min_r2=0.80, n_min=45,
       window="8 h shift composite",
       note="The headline product specification. A persistent bias here is the one finding that "
            "would stop acceptance on its own."),
    _c("lump_al2o3_pct", "Lump ore alumina", "% Al2O3", "A",
       "Shift composite sample, laboratory XRF", 0.06,
       max_bias=0.08, max_mae=0.12, max_rmse=0.16, max_mape=6.0, min_r2=0.75, n_min=45,
       window="8 h shift composite",
       note="Penalty element. Judged separately at high-clay feed, where the plant actually "
            "needs the prediction."),
    _c("fines_fe_pct", "Sinter fines Fe", "% Fe", "A",
       "Shift composite sample, laboratory XRF", 0.25,
       max_bias=0.30, max_mae=0.45, max_rmse=0.60, max_mape=1.0, min_r2=0.78, n_min=45,
       window="8 h shift composite"),
    _c("fe_recovery_pct", "Overall Fe recovery", "%", "A",
       "Reconciled daily metallurgical balance", 0.80,
       max_bias=1.00, max_mae=1.40, max_rmse=1.80, max_mape=2.5, min_r2=0.70, n_min=30,
       window="24 h reconciled",
       note="Judged on reconciled data only. An unreconciled recovery figure is not a "
            "measurement and no model should be graded against one.", kind="percentage"),
    _c("mass_yield_pct", "Mass yield to product", "%", "A",
       "Reconciled daily balance from weightometers", 0.60,
       max_bias=0.80, max_mae=1.10, max_rmse=1.50, max_mape=2.0, min_r2=0.75, n_min=30,
       window="24 h reconciled", kind="percentage"),
    _c("pellet_fines_fe_pct", "Pellet-plant feed Fe", "% Fe", "B",
       "Shift composite sample, laboratory XRF", 0.30,
       max_bias=0.40, max_mae=0.55, max_rmse=0.75, max_mape=1.4, min_r2=0.70, n_min=40,
       window="8 h shift composite"),
    _c("throughput_tph", "ROM throughput", "t/h", "B",
       "Calibrated weightometer, hourly average", 6.0,
       max_bias=8.0, max_mae=11.0, max_rmse=14.0, max_mape=2.5, min_r2=0.92, n_min=60,
       window="1 h average", kind="flow"),
    _c("lump_tph", "Lump ore production", "t/h", "B",
       "Calibrated weightometer, hourly average", 3.0,
       max_bias=4.0, max_mae=5.5, max_rmse=7.0, max_mape=3.0, min_r2=0.85, n_min=60, kind="flow"),
    _c("fines_tph", "Sinter fines production", "t/h", "B",
       "Calibrated weightometer, hourly average", 2.5,
       max_bias=3.5, max_mae=4.5, max_rmse=6.0, max_mape=3.0, min_r2=0.85, n_min=60, kind="flow"),
    _c("tailings_fe_pct", "Tailings Fe", "% Fe", "B",
       "Daily composite, laboratory XRF", 0.40,
       max_bias=0.55, max_mae=0.75, max_rmse=1.00, max_mape=4.0, min_r2=0.65, n_min=30,
       window="24 h composite",
       note="The loss term. Accuracy here is what makes a recovery prediction believable."),
    _c("lump_al2o3_pct@high_clay", "Lump alumina, high-clay feed", "% Al2O3", "A",
       "Shift composite during feed with clay share above 0.6", 0.06,
       max_bias=0.10, max_mae=0.15, max_rmse=0.20, max_mape=7.5, min_r2=0.70, n_min=20,
       window="8 h shift composite", scenarios=("S03_high_clay",),
       note="Deliberately a wider tolerance on a harder case, judged on fewer samples. The "
            "alternative - one tolerance across all feeds - either fails a good model on hard "
            "ore or passes a poor one on easy ore."),
    _c("energy_kwh_t", "Specific energy", "kWh/t", "C",
       "Switchboard energy meters against ROM tonnes", 0.18,
       max_bias=0.30, max_mae=0.45, max_rmse=0.60, max_mape=6.0, min_r2=0.60, n_min=30,
       window="24 h", kind="rate"),
    _c("fresh_water_m3_h", "Fresh water make-up", "m3/h", "C",
       "Magnetic flow meter on the make-up line", 12.0,
       max_bias=18.0, max_mae=26.0, max_rmse=34.0, max_mape=10.0, min_r2=0.50, n_min=30, kind="flow"),
    _c("classifier_d50_um", "Classifier cut size", "um", "C",
       "Periodic size-by-size survey of overflow and sand", 22.0,
       max_bias=30.0, max_mae=45.0, max_rmse=60.0, max_mape=18.0, min_r2=0.45, n_min=12,
       window="per survey", kind="rate",
       note="Surveyed rather than measured on line, so the sample count is small by nature "
            "and the verdict is indicative."),
]

#: System-level criteria. These are properties of the software and the deployment rather than
#: of the process model, and several of them are pass/fail rather than tolerance-based.
SYSTEM_CRITERIA: list[dict[str, Any]] = [
    {"id": "balance_solids", "name": "Solids mass-balance closure", "class": "A",
     "limit": ">= 99.5 %", "kind": "min", "value_key": "closure_solids_pct", "threshold": 99.5, "ceiling": 100.0,
     "method": "Sum of product and tailings solids against ROM feed on the delivered model.",
     "why": "A twin that does not close cannot be reasoned with; every other number is suspect."},
    {"id": "balance_iron", "name": "Iron-unit closure", "class": "A",
     "limit": ">= 99.5 %", "kind": "min", "value_key": "closure_fe_pct", "threshold": 99.5, "ceiling": 100.0,
     "method": "Iron units out against iron units in."},
    {"id": "balance_elements", "name": "Silica and alumina closure", "class": "B",
     "limit": "within +/- 7 % of unity", "kind": "min", "value_key": "closure_elements_pct",
     "threshold": 93.0, "ceiling": 100.0,
     "method": "Worst absolute departure from unity across silica and alumina, so an "
               "over-closure counts against the model exactly as an under-closure does.",
     "why": "Silica and alumina are re-partitioned at each separator by a first-order bias model "
            "rather than carried as their own state axes, which is a deliberate simplification. "
            "The tolerance is stated at the level the simplification actually delivers, around "
            "five to six per cent, rather than at a number that sounds better and would have to "
            "be conceded later. A site that needs tighter secondary-mineral closure is quoted a "
            "multi-component state, which is a larger model and a larger calibration programme."},
    {"id": "solve_time", "name": "Full-circuit solve time, 95th percentile", "class": "B",
     "limit": "<= 2000 ms", "kind": "max", "value_key": "solve_p95_ms", "threshold": 2000.0,
     "method": "Timed over the scenario suite on the delivered hardware."},
    {"id": "mpc_solve", "name": "MPC solve time per interval", "class": "B",
     "limit": "<= 30 s", "kind": "max", "value_key": "mpc_solve_s", "threshold": 30.0,
     "method": "Worst case over the closed-loop study, against a five-minute supervisory cycle."},
    {"id": "availability", "name": "Service availability over the trial", "class": "A",
     "limit": ">= 99.0 %", "kind": "min", "value_key": "availability_pct", "threshold": 99.0, "ceiling": 100.0,
     "method": "Health endpoint polled at one-minute intervals for the trial duration."},
    {"id": "data_completeness", "name": "Historian data completeness", "class": "B",
     "limit": ">= 95.0 %", "kind": "min", "value_key": "data_completeness_pct", "threshold": 95.0, "ceiling": 100.0,
     "method": "Good-quality samples against expected samples across the tag list.",
     "why": "A twin cannot be graded on a period when the plant was not measuring. Below this "
            "the period is excluded from the trial rather than counted as a failure."},
    {"id": "soft_sensor_latency", "name": "Soft-sensor update latency", "class": "B",
     "limit": "<= 60 s", "kind": "max", "value_key": "soft_sensor_latency_s", "threshold": 60.0,
     "method": "Historian timestamp to desk display."},
    {"id": "reproducibility", "name": "Bitwise reproducibility", "class": "A",
     "limit": "identical", "kind": "bool", "value_key": "reproducible",
     "method": "The same inputs and the same model version produce the same outputs.",
     "why": "Without this there is no auditable acceptance, because no result can be re-checked."},
    {"id": "hybrid_gate", "name": "Hybrid correction gating", "class": "A",
     "limit": "correction -> 0 outside domain", "kind": "bool", "value_key": "hybrid_gate_ok",
     "method": "Extrapolation walk out of the learned domain; the gated prediction must converge "
               "on the mechanistic prediction exactly.",
     "why": "This is what makes a data-driven component safe to put in front of an operator."},
    {"id": "regression_suite", "name": "Automated regression suite", "class": "A",
     "limit": "100 % pass", "kind": "bool", "value_key": "tests_pass",
     "method": "The delivered test suite, run on the plant's own installation."},
    {"id": "constraint_feasibility", "name": "Delivered operating point feasible", "class": "B",
     "limit": "penalty = 0", "kind": "max", "value_key": "constraint_penalty", "threshold": 0.0,
     "method": "No constraint violated at the shipped baseline operating point."},
]


def criteria_index() -> dict[str, dict[str, Any]]:
    return {c["kpi"]: c for c in KPI_CRITERIA}


def gating_kpis() -> list[str]:
    return [c["kpi"] for c in KPI_CRITERIA if TOLERANCE_CLASSES[c["class"]]["gates_acceptance"]]


def catalogue() -> dict[str, Any]:
    return {
        "tolerance_classes": TOLERANCE_CLASSES,
        "kpi_criteria": KPI_CRITERIA,
        "system_criteria": SYSTEM_CRITERIA,
        "counts": {"kpi": len(KPI_CRITERIA), "system": len(SYSTEM_CRITERIA),
                   "class_a": sum(1 for c in KPI_CRITERIA if c["class"] == "A"),
                   "class_b": sum(1 for c in KPI_CRITERIA if c["class"] == "B"),
                   "class_c": sum(1 for c in KPI_CRITERIA if c["class"] == "C")},
        "principles": [
            "No tolerance is tighter than the reference measurement's own repeatability.",
            "Criteria are graded; Class C is reported but does not gate acceptance.",
            "Every criterion names its measurement basis, averaging window and minimum sample "
            "count. Below the sample count no verdict is given rather than a weak one.",
            "Hard cases carry their own, wider criteria rather than being averaged into the "
            "easy ones.",
            "Assays gate on absolute error and tonnages on relative error, because that is how "
            "each one is contracted. Applying both to both silently makes the tighter of the two "
            "the real criterion, and which one that is changes from plant to plant.",
            "Periods when the plant was not measuring properly are excluded from the trial, "
            "not counted as model failures.",
        ],
        "amendment": "The table is agreed and frozen at the end of Phase 0, before the model is "
                     "built, and any change after that is a signed variation. Criteria written "
                     "after the results are known are not acceptance criteria.",
    }
