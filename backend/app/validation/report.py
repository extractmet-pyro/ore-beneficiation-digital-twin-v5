"""The acceptance test report.

The deliverable of a validation run is a document someone signs, not a JSON blob. This module
renders the run as Markdown — which converts cleanly to Word or PDF and, more importantly, can
be read and checked line by line by a plant engineer who was not in the room.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.validation.criteria import TOLERANCE_CLASSES, catalogue as criteria_catalogue
from app.validation.protocol import protocol
from app.validation.scenarios import catalogue as scenario_catalogue

_MARK = {"pass": "PASS", "fail": "FAIL", "marginal": "MARGINAL", "partial": "PARTIAL",
         "incomplete": "INCOMPLETE", "insufficient_data": "NO VERDICT",
         "not_evaluated": "EVIDENCE REQUIRED", "not_discriminating": "NOT DISCRIMINATING",
         "not_applicable": "NOT APPLICABLE", "no_response": "NO RESPONSE"}


def _m(v: str) -> str:
    return _MARK.get(v, str(v).upper())


def _table(head: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    out.append("")
    return out


def render_markdown(run: dict[str, Any], *, plant_name: str | None = None,
                    model_version: str = "", gate: str = "G1") -> str:
    acc, beh, fs, sysr = run["accuracy"], run["behaviour"], run["fail_safe"], run["system"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L: list[str] = []
    A = L.append

    A(f"# Digital Twin Acceptance Test Report — {gate}")
    A("")
    A(f"**Plant** {plant_name or run['plant_id']}  ")
    A(f"**Model version** {model_version or 'as delivered'}  ")
    A(f"**Generated** {now}  ")
    A(f"**Overall verdict** **{_m(run['overall_verdict'])}**")
    A("")
    A("This report is produced by the twin itself from the criteria table agreed and frozen at "
      "Gate 0. Every number below can be reproduced by re-running the validation endpoint "
      "against the same model version and the same data window.")
    A("")

    # ---------------------------------------------------------------- summary
    A("## 1  Summary of verdicts")
    A("")
    L.extend(_table(
        ["Section", "Verdict", "Detail"],
        [["Accuracy against plant data", _m(acc["verdict"]),
          f"{acc['summary']['pass']} pass, {acc['summary']['marginal']} marginal, "
          f"{acc['summary']['fail']} fail of {acc['summary']['evaluated']} criteria"],
         ["Behaviour (step tests)", _m(beh["verdict"]),
          f"{sum(1 for r in beh['rows'] if r['verdict'] == 'pass')} of {len(beh['rows'])} scenarios pass"],
         ["Fail-safe outside envelope", _m(fs["verdict"]),
          f"{sum(1 for c in fs['checks'] if c['verdict'] == 'pass')} of {len(fs['checks'])} checks pass"],
         ["System criteria", _m(sysr["verdict"]),
          f"{sysr['summary']['pass']} pass, {sysr['summary']['fail']} fail, "
          f"{sysr['summary']['evidence_required']} awaiting site evidence"]]))
    gr = run.get("gate_readiness", {})
    A(f"**Gate readiness** {gr.get('G1_FAT', 'unknown')}")
    A("")
    if gr.get("blocking"):
        A("**Blocking items:** " + ", ".join(gr["blocking"]))
        A("")
    if gr.get("evidence_outstanding"):
        A("**Evidence outstanding (supplied at site acceptance):** "
          + ", ".join(gr["evidence_outstanding"]))
        A("")

    # ---------------------------------------------------------------- accuracy
    A("## 2  Accuracy against plant data")
    A("")
    A(f"Data window: {acc['hours_evaluated']} hours evaluated, {acc['hours_excluded']} excluded "
      f"({acc['exclusion_pct']} % of elapsed time). Source: {acc['data_source']}")
    A("")
    A("Tolerances are stated as a multiple of the reference measurement's own repeatability. "
      "The `RMSE / sigma` column is the one to read: a value below about 1.5 means the model "
      "disagrees with the measurement by less than the measurement disagrees with itself.")
    A("")
    rows = []
    for r in acc["results"]:
        if r["verdict"] == "insufficient_data":
            rows.append([r["kpi"], r.get("class", ""), r.get("n"), "", "", "", "", _m(r["verdict"])])
            continue
        st = r["statistics"]
        rows.append([r["kpi"], r["class"], r["n"], st["bias"], st["mae"], st["rmse"],
                     r["rmse_in_sigmas"], _m(r["verdict"])])
    L.extend(_table(["KPI", "Class", "n", "Bias", "MAE", "RMSE", "RMSE / sigma", "Verdict"], rows))

    supp = [r for r in acc["results"] if r.get("suppressed_checks")]
    if supp:
        A("### 2.1  Measures suppressed, and why")
        A("")
        A("A correlation measure applied to a variable that barely moves over the test period "
          "grades the measurement noise rather than the model. Where that is the case the "
          "measure is reported but not used to decide the verdict, and the reason is recorded "
          "here rather than left for someone to discover.")
        A("")
        srows = []
        for r in supp:
            for k in r["suppressed_checks"]:
                srows.append([r["kpi"], k, _m(r["checks"][k]["verdict"]),
                              r["checks"][k].get("reason", "")[:150]])
        L.extend(_table(["KPI", "Measure", "Status", "Reason"], srows))

    fails = [r for r in acc["results"] if r["verdict"] in ("fail", "marginal")]
    if fails:
        A("### 2.2  Criteria not fully met")
        A("")
        for r in fails:
            A(f"**{r['kpi']} ({r['label']}) — {_m(r['verdict'])}**")
            A("")
            for k in r["failed_checks"]:
                c = r["checks"][k]
                A(f"- `{k}` = {c['value']} against a limit of {c['limit']} "
                  f"(margin {c['margin']}).")
            A(f"- Measurement basis: {r['measurement_basis']}")
            A("")

    # ---------------------------------------------------------------- behaviour
    A("## 3  Behaviour — step tests")
    A("")
    A(beh["method"])
    A("")
    for r in beh["rows"]:
        A(f"### {r['scenario_id']} — {r['name']} — **{_m(r['verdict'])}**")
        A("")
        s = r["step"]
        A(f"Step: `{s['variable']}` {s['from']} to {s['to']} ({s['group']}).  ")
        A(f"Rationale: {r['rationale']}")
        A("")
        L.extend(_table(["Variable", "Expected", "From", "To", "Change", "Verdict"],
                        [[c["kpi"], c.get("expected", ""), c.get("from"), c.get("to"),
                          c.get("change_pct", c.get("change")), _m(c["verdict"])]
                         for c in r["checks"]]))

    # ---------------------------------------------------------------- fail safe
    A("## 4  Behaviour outside the validated envelope")
    A("")
    A(fs["statement"])
    A("")
    L.extend(_table(["Check", "Verdict", "Detail"],
                    [[c["check"], _m(c["verdict"]), c["detail"]] for c in fs["checks"]]))

    # ---------------------------------------------------------------- system
    A("## 5  System criteria")
    A("")
    A(sysr["note"])
    A("")
    L.extend(_table(["Criterion", "Class", "Limit", "Measured", "Verdict"],
                    [[r["name"], r["class"], r["limit"], r.get("value"), _m(r["verdict"])]
                     for r in sysr["results"]]))

    # ---------------------------------------------------------------- criteria table
    A("## 6  The criteria this report was graded against")
    A("")
    cc = criteria_catalogue()
    A(cc["amendment"])
    A("")
    L.extend(_table(["KPI", "Class", "Unit", "Reference sigma", "Max bias", "Max RMSE",
                     "Min R2", "Basis"],
                    [[c["kpi"], c["class"], c["unit"], c["reference_sigma"],
                      c["limits"]["max_abs_bias"], c["limits"]["max_rmse"],
                      c["limits"]["min_r2"], c["measurement_basis"]]
                     for c in cc["kpi_criteria"]]))
    A("Tolerance classes:")
    A("")
    L.extend(_table(["Class", "Name", "Gates acceptance", "Definition"],
                    [[k, v["name"], "yes" if v["gates_acceptance"] else "no", v["definition"]]
                     for k, v in TOLERANCE_CLASSES.items()]))

    # ---------------------------------------------------------------- scenarios
    A("## 7  Scenario catalogue")
    A("")
    sc = scenario_catalogue()
    L.extend(_table(["ID", "Scenario", "Kind", "KPIs judged", "Expected behaviour"],
                    [[s["scenario_id"], s["name"], s["kind"],
                      ", ".join(s["kpis_judged"]) or "n/a",
                      s["expected_behaviour"][:180]] for s in sc["scenarios"]]))

    # ---------------------------------------------------------------- protocol
    A("## 8  Acceptance procedure")
    A("")
    pr = protocol()
    L.extend(_table(["Gate", "Name", "Phase", "Exit criterion", "Signatories"],
                    [[g["gate"], g["name"], g["phase"], g["exit"],
                      ", ".join(g["signatories"])] for g in pr["gates"]]))
    A("**Concessions.** " + pr["concession_rule"])
    A("")
    A("**Periods excluded from the statistics:**")
    A("")
    for e in pr["exclusion_rules"]:
        A(f"- {e}")
    A("")

    # ---------------------------------------------------------------- signature
    A("## 9  Signatures")
    A("")
    L.extend(_table(["Role", "Name", "Organisation", "Date", "Signature"],
                    [[v.split(".")[0], "", "", "", ""] for v in pr["roles"].values()]))
    A("---")
    A("")
    A("Prepared by Extractmet Private Limited. Commercial in confidence.")
    return "\n".join(x for x in L if x is not None)
