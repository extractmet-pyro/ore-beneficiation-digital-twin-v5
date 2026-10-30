"""The demonstration and acceptance procedure.

Acceptance criteria without a procedure are a wish. This module defines the gates, who signs
each one, what evidence is produced, and what happens when a gate fails — which is the part
most specifications leave out and most disputes turn on.

The sequence is the one used for any process control or analyser package, adapted for a model:
data readiness, factory acceptance on historical data, site acceptance on the live link, a
performance trial on the running plant, and — where supervisory control is in scope — a
structured on/off trial before closed loop.
"""
from __future__ import annotations

from typing import Any

ROLES: dict[str, str] = {
    "supplier": "Extractmet project engineer. Runs the tests, produces the evidence pack.",
    "plant_process": "Plant process engineer or chief metallurgist. Owns the acceptance "
                     "criteria and signs the metallurgical verdict.",
    "plant_control": "Plant control and instrumentation engineer. Owns the tag list, the "
                     "historian link and, in Phase 3, the DCS interface.",
    "plant_it": "Plant IT and OT. Owns the deployment, the network path and the security review.",
    "plant_lab": "Laboratory manager. Owns the reference measurements and their uncertainty.",
    "assessor": "Optional independent assessor nominated by the plant. May witness any gate.",
}

GATES: list[dict[str, Any]] = [
    {
        "gate": "G0", "name": "Data readiness review", "phase": "Phase 0",
        "objective": "Establish that the plant's data can support the criteria that are about "
                     "to be agreed, before anyone commits to them.",
        "entry": ["Flowsheet and equipment list frozen", "Tag list supplied",
                  "Twelve months of historian data made available",
                  "Laboratory precision records supplied"],
        "activities": [
            "Tag audit: coverage, engineering units, calibration status, completeness.",
            "Reference-measurement uncertainty established from the laboratory's own duplicates.",
            "Acceptance criteria table populated with those uncertainties and agreed.",
            "Operating envelope agreed from the ore-body model and the plant's own range.",
            "Scenario catalogue agreed, including which historical events will be used.",
            "Survey campaign specified where the data will not otherwise support a criterion.",
        ],
        "evidence": ["Data-gap report", "Signed acceptance criteria table",
                     "Signed operating envelope", "Agreed scenario catalogue"],
        "signatories": ["supplier", "plant_process", "plant_control", "plant_lab"],
        "exit": "Criteria table and envelope signed and frozen.",
        "on_failure": "Either a survey campaign is added to the scope, or the affected criterion "
                      "is downgraded to Class C with that stated in writing. A criterion is never "
                      "agreed on data that cannot test it.",
    },
    {
        "gate": "G1", "name": "Factory acceptance test (FAT)", "phase": "End of Phase 1",
        "objective": "Demonstrate the calibrated model against plant data that was withheld from "
                     "calibration, offline, before anything is installed on site.",
        "entry": ["Model calibrated", "Validation data set withheld and sealed at G0",
                  "Regression suite passing"],
        "activities": [
            "Blind run against the withheld validation set; no further fitting is permitted "
            "after the seal is broken.",
            "All accuracy scenarios executed and graded against the criteria table.",
            "All behaviour scenarios executed and graded on direction and magnitude.",
            "System criteria measured: closure, solve time, reproducibility, regression suite.",
            "Hybrid gating demonstrated by the extrapolation walk.",
            "Fail-safe scenario demonstrated outside the envelope.",
        ],
        "evidence": ["FAT report with every criterion and its verdict",
                     "Parity and Bland-Altman plots per Class A KPI",
                     "Calibration report listing every fitted parameter",
                     "Regression suite output", "Reproducibility check"],
        "signatories": ["supplier", "plant_process", "assessor"],
        "exit": "All Class A criteria pass. Class B pass or carry a written concession.",
        "on_failure": "Re-calibration against the training set only, then a re-run against a "
                      "fresh withheld set. The failed set is not reused, because a model "
                      "re-fitted to its own validation data has not been validated.",
    },
    {
        "gate": "G2", "name": "Site acceptance test (SAT)", "phase": "End of Phase 2",
        "objective": "Demonstrate the installed system on the plant's own infrastructure, "
                     "reading live data.",
        "entry": ["Deployed on plant server or VM", "Historian link established, read-only",
                  "Security review complete", "Operators trained"],
        "activities": [
            "Connectivity and tag-mapping verification across the full tag list.",
            "Data completeness and latency measured over fourteen consecutive days.",
            "Live prediction compared against laboratory assays as they are produced.",
            "Soft sensors compared against the laboratory over the same period.",
            "Reconciliation and anomaly monitors exercised on live data.",
            "Failover, restart and historian-outage behaviour demonstrated.",
        ],
        "evidence": ["SAT report", "Tag-mapping verification record",
                     "Fourteen-day availability and completeness log",
                     "Live-versus-laboratory comparison"],
        "signatories": ["supplier", "plant_process", "plant_control", "plant_it"],
        "exit": "Availability, completeness and latency criteria met; Class A accuracy "
                "maintained on live data over the fourteen days.",
        "on_failure": "Where the cause is instrumentation or data quality, the finding is "
                      "recorded against the plant and the clock stops until it is resolved. "
                      "Where the cause is the model, G1 is re-entered.",
    },
    {
        "gate": "G3", "name": "Performance trial", "phase": "Phase 2 to Phase 3",
        "objective": "Demonstrate that the accuracy holds over a commercially meaningful period "
                     "and across real ore variability, not just over a good fortnight.",
        "entry": ["SAT passed", "Trial period, exclusions and reconciliation basis agreed"],
        "activities": [
            "Continuous operation for the agreed trial period, thirty days minimum and ninety "
            "days preferred.",
            "All Class A and B criteria evaluated on the full period, excluding declared "
            "exclusions only.",
            "Drift monitors reviewed; any re-calibration during the trial is recorded and the "
            "trial restarts if the model is changed.",
            "At least one unplanned ore excursion captured and reported.",
        ],
        "evidence": ["Trial report", "Exclusion log with a reason for every excluded period",
                     "Drift and re-calibration log", "Availability record"],
        "signatories": ["supplier", "plant_process", "plant_control", "assessor"],
        "exit": "Criteria met over the full trial period with declared exclusions below ten "
                "per cent of elapsed time.",
        "on_failure": "Trial extended once by the agreed period. A second failure returns the "
                      "project to G1 at the supplier's cost.",
    },
    {
        "gate": "G4", "name": "Control acceptance", "phase": "Phase 3, where MPC is in scope",
        "objective": "Demonstrate that the supervisory controller improves the plant, measured "
                     "by the plant's own metallurgical accounting.",
        "entry": ["G3 passed", "Advisory mode run for at least thirty days",
                  "Operator acceptance rate recorded", "DCS interface specification signed"],
        "activities": [
            "Structured on/off trial: alternating periods with the controller in and out of "
            "service, on comparable feed, with the sequence fixed in advance.",
            "Evaluation by the plant's own metallurgical accounting, not by the supplier.",
            "Move limits, rate limits, watchdog and operator override all demonstrated.",
            "Hand-over payload verified, including checksum and rejection of a corrupted payload.",
        ],
        "evidence": ["On/off trial report", "Operator acceptance log",
                     "Interface and interlock test record", "Benefit calculation by the plant"],
        "signatories": ["supplier", "plant_process", "plant_control", "assessor"],
        "exit": "Agreed benefit measure improved by the contracted margin, with all interlocks "
                "demonstrated.",
        "on_failure": "The controller remains in advisory service, which is independently "
                      "useful, and the closed-loop milestone is not invoiced.",
    },
    {
        "gate": "G5", "name": "Handover", "phase": "Project close",
        "objective": "Leave the plant able to run, maintain and extend the system without the "
                     "supplier.",
        "entry": ["All prior gates passed or concessions recorded"],
        "activities": [
            "Source code, model configuration and test suite delivered.",
            "Deployment guide and calibration report delivered and walked through.",
            "Three training sessions delivered: metallurgists, control engineers, IT and OT.",
            "Model custody arrangement and re-calibration schedule agreed.",
            "Outstanding concessions and known limitations listed and signed.",
        ],
        "evidence": ["Handover certificate", "Delivered artefact list",
                     "Training attendance record", "Open-items register"],
        "signatories": ["supplier", "plant_process", "plant_control", "plant_it"],
        "exit": "Handover certificate signed.",
        "on_failure": "Not applicable; outstanding items are carried on the open-items register "
                      "with owners and dates.",
    },
]

CONCESSION_RULE = (
    "A Class B criterion that fails by less than 25 % of its limit may be accepted by written "
    "concession recording the shortfall, the cause, the operational consequence and whether a "
    "remedy is planned. Class A criteria cannot be conceded. Concessions are listed on the "
    "handover certificate so that they remain visible after the project team has gone."
)

EXCLUSION_RULES: list[str] = [
    "Plant down, tripped, starting up or shutting down.",
    "Throughput below 50 % of nameplate, which is a transient rather than an operating state.",
    "Historian data completeness below 95 % for the period.",
    "A reference measurement known to be out of calibration, from the date of the last good "
    "check to the date of recalibration.",
    "Periods during which the model was being re-calibrated.",
    "Declared out-of-envelope operation, which is reported separately rather than graded.",
]


def protocol() -> dict[str, Any]:
    return {
        "gates": GATES, "roles": ROLES, "concession_rule": CONCESSION_RULE,
        "exclusion_rules": EXCLUSION_RULES,
        "sequence": [g["gate"] for g in GATES],
        "principles": [
            "The validation data set is sealed at G0 and not opened until the FAT. A model "
            "tuned against its own acceptance data has not been validated.",
            "Behaviour is graded as well as accuracy. A model can hit every tolerance and still "
            "move the wrong lever.",
            "The plant's own metallurgical accounting decides the control benefit, not ours.",
            "Exclusions are defined in advance and logged with reasons, so that the trial cannot "
            "be rescued after the fact by discarding bad days.",
            "Every gate has named signatories and a stated consequence of failure.",
        ],
    }
