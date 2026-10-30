"""Executing a validation run and producing verdicts.

Three kinds of test are run, because three different questions have to be answered:

* **Accuracy** — paired model and plant observations graded against the numerical criteria.
* **Behaviour** — step tests graded on the direction and order of magnitude of the response.
  This is the check that catches a model which is numerically close and physically wrong.
* **System** — properties of the software and the deployment: closure, solve time,
  reproducibility, hybrid gating, feasibility of the shipped operating point.

Every verdict carries the number, the limit and the margin, so the report can be read without
re-running anything.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.validation import metrics as M
from app.validation.criteria import KPI_CRITERIA, SYSTEM_CRITERIA, TOLERANCE_CLASSES, criteria_index
from app.validation.scenarios import ENVELOPE, SCENARIOS, envelope_check, scenario_index

#: Machine-checkable behaviour expectations. Each is a step between two operating points with
#: the sign of the expected response on each KPI: +1 rises, -1 falls, 0 must not move materially.
BEHAVIOUR_CHECKS: dict[str, dict[str, Any]] = {
    "S05_rate_up": {
        "group": "operating", "variable": "rom_feed_tph", "from": 600.0, "to": 715.0,
        "expect": {"throughput_tph": +1},
        "unit_expect": {"spirals.load_fraction": +1, "shaking_tables.load_fraction": +1,
                        "lump_jig.loading_tph_m2": +1, "whims.loading_fraction": +1},
        "bounded": {"fe_recovery_pct": 0.6},
        "rationale": "Every separator is loaded harder, so each one's loading fraction must rise. "
                     "On this circuit recovery is expected to hold rather than collapse, because "
                     "the gravity units still have headroom at 110 % of nameplate; the bounded "
                     "check catches a model that invents a recovery gain from extra tonnage.",
    },
    "S06_turndown": {
        "group": "operating", "variable": "rom_feed_tph", "from": 600.0, "to": 420.0,
        "expect": {"energy_kwh_t": +1, "throughput_tph": -1},
        "rationale": "Fixed-speed drives on a smaller tonnage raise specific energy.",
    },
    "S07_scrubber_step": {
        "group": "operating", "variable": "scrubber_speed_pct_critical", "from": 24.0, "to": 38.0,
        "expect": {"lump_al2o3_pct": -1},
        "unit_expect": {"scrubber.clay_detachment_pct": +1},
        "rationale": "The plant's primary lever on lump alumina. If this sign is wrong, nothing "
                     "else about the model matters.",
    },
    "S07b_scrubber_dilution": {
        "group": "operating", "variable": "scrubber_water_m3_h", "from": 294.0, "to": 546.0,
        "expect": {"lump_al2o3_pct": +1},
        "unit_expect": {"scrubber.solids_pct": -1, "scrubber.scrubbing_index": -1},
        "rationale": "A scrubber cleans by attrition in a dense pulp. Adding dilution water "
                     "lowers the pulp density and the residence time, so LESS clay is detached "
                     "and the product gets worse. The counter-intuitive sign is the test.",
    },
    "S08_jig_cut": {
        "group": "operating", "variable": "lump_jig_cut_sg", "from": 3.9, "to": 4.4,
        "expect": {"lump_fe_pct": +1, "lump_yield_pct": -1},
        "rationale": "The grade-recovery trade-off at the jig, which must be traced correctly "
                     "or the optimiser will walk the wrong way.",
    },
    "S09_whims_field": {
        "group": "operating", "variable": "whims_field_tesla", "from": 0.60, "to": 1.30,
        "expect": {"fe_recovery_pct": +1},
        "unit_expect": {"whims.mass_recovery_pct": +1, "whims.fe_recovery_pct": +1,
                        "whims.tail_fe_pct": -1},
        # one-sided on purpose: the grade must not COLLAPSE. A rise is the correct answer on a
        # deslimed, well liberated feed and must not be scored as a failure.
        "floor": {"pellet_fines_fe_pct": -2.5},
        "rationale": "A stronger field recovers substantially more iron from a deslimed, well "
                     "liberated feed. Concentrate grade is expected to hold or improve rather "
                     "than collapse, because the extra material recovered is liberated haematite "
                     "and not middlings.",
    },
    "S12_recycle_upset": {
        "group": "operating", "variable": "tertiary_css_mm", "from": 8.0, "to": 14.0,
        "expect": {"energy_kwh_t": -1},
        "unit_expect": {"tertiary_crusher.circulating_load_pct": +1,
                        "tertiary_crusher.feed_tph": +1},
        "rationale": "Opening the recrush setting above the screen aperture floods the recycle: "
                     "circulating load and crusher feed rise. Specific energy falls, because "
                     "each tonne is crushed less hard - the cost of the upset appears as lost "
                     "capacity, not as kWh per tonne, which is the distinction a plant needs.",
    },
    "S13_water_limited": {
        "group": "operating", "variable": "reclaim_water_fraction", "from": 0.85, "to": 0.55,
        "expect": {"fresh_water_m3_h": +1},
        "rationale": "Less reclaim must be made up with fresh water; the balance has to show it.",
    },
}

#: Scenarios whose feed is changed rather than a set-point, used for the accuracy cases.
ORE_SCENARIOS: dict[str, dict[str, float]] = {
    "S02_low_grade": {"fe_head_pct": 49.0, "sio2_head_pct": 13.0},
    "S03_high_clay": {"clay_share": 0.72, "al2o3_head_pct": 7.2},
    "S04_hard_banded": {"axb": 42.0, "liberation_d50_um": 28000.0, "lump_friability": 0.12},
    "S15_outside_envelope": {"fe_head_pct": 46.0, "clay_share": 0.85},
}

_REL_TOL = 1e-4   # a response smaller than this fraction counts as "did not move"


# --------------------------------------------------------------------------- grading
def _grade_limit(value, limit, kind: str, ceiling: float | None = None) -> dict[str, Any]:
    """Grade one number against one limit.

    ``ceiling`` matters for the bounded measures. R-squared cannot exceed 1 and coverage cannot
    exceed 100, so "how much headroom is left" has to be measured against the distance from the
    limit to that ceiling, not against the limit itself. Without it an R-squared of 1.000 against
    a limit of 0.92 is reported as marginal, which is nonsense.
    """
    if value is None or limit is None or (isinstance(value, float) and not np.isfinite(value)):
        return {"value": None, "limit": limit, "verdict": "not_evaluated", "margin": None}
    v, l = float(value), float(limit)
    ok = v <= l if kind == "max" else v >= l
    margin = (l - v) if kind == "max" else (v - l)
    span = abs(float(ceiling) - l) if ceiling is not None else abs(l)
    # a limit of exactly zero has no meaningful "nearly" band; satisfying it is a pass
    marginal = ok and span > 1e-9 and abs(margin) < 0.10 * span
    return {"value": round(v, 5), "limit": round(l, 5),
            "verdict": "marginal" if marginal else ("pass" if ok else "fail"),
            "margin": round(margin, 5),
            "margin_pct_of_limit": round(100 * margin / max(span, 1e-9), 1)}


#: Measures that only discriminate when the observed variable actually moves. Applying them to a
#: variable whose whole range over the test period is inside its own measurement noise produces
#: a failure that says nothing about the model.
_NEEDS_VARIANCE = ("r2", "theil_u2")
_VARIANCE_FACTOR = 2.0


def _window_hours(window: str) -> float:
    w = (window or "").lower()
    if "shift" in w or "8 h" in w:
        return 8.0
    if "24 h" in w or "daily" in w:
        return 24.0
    if "survey" in w:
        return float("inf")
    return 1.0



def grade_kpi(criterion: dict[str, Any], observed, predicted, lo=None, hi=None) -> dict[str, Any]:
    """Evaluate one KPI criterion against a paired series."""
    obs = np.asarray(observed, dtype=float).ravel()
    pred = np.asarray(predicted, dtype=float).ravel()
    n = int(min(len(obs), len(pred)))
    if n < criterion["n_min"]:
        return {"kpi": criterion["kpi"], "label": criterion["label"], "class": criterion["class"],
                "n": n, "n_min": criterion["n_min"], "verdict": "insufficient_data",
                "note": f"{n} paired samples against a minimum of {criterion['n_min']}. "
                        "No verdict is given rather than a weak one."}
    rep = M.full_report(obs[:n], pred[:n], lo, hi)
    L = criterion["limits"]
    sigma = float(criterion["reference_sigma"])
    obs_sd = float(rep["observed"]["sd"])
    discriminating = obs_sd > _VARIANCE_FACTOR * sigma
    hourly = _window_hours(criterion.get("window", "")) <= 1.0

    checks = {
        "bias": _grade_limit(abs(rep["bias"]), L["max_abs_bias"], "max"),
        "mae": _grade_limit(rep["mae"], L["max_mae"], "max"),
        "rmse": _grade_limit(rep["rmse"], L["max_rmse"], "max"),
        "mape_pct": _grade_limit(rep["mape_pct"], L["max_mape_pct"], "max"),
        "r2": _grade_limit(rep["r2"], L["min_r2"], "min", ceiling=1.0),
        "theil_u2": _grade_limit(rep["theil_u2"], L["max_theil_u2"], "max"),
    }
    if "coverage_95_pct" in rep:
        checks["coverage_95_pct"] = _grade_limit(rep["coverage_95_pct"], L["min_coverage_95_pct"],
                                                 "min", ceiling=100.0)

    # Suppress the measures that cannot discriminate on this series, and say why.
    if not discriminating:
        for k in _NEEDS_VARIANCE:
            if checks[k]["verdict"] != "not_evaluated":
                checks[k] = {**checks[k], "verdict": "not_discriminating",
                             "reason": (f"Observed spread over the test period (sd {obs_sd:g}) is "
                                        f"below {_VARIANCE_FACTOR:g} x the reference measurement's "
                                        f"own repeatability ({sigma:g}). A correlation measure on "
                                        f"a series that barely moves grades the noise, not the "
                                        f"model; bias, MAE and RMSE decide instead.")}
    if not hourly and checks["theil_u2"]["verdict"] not in ("not_evaluated", "not_discriminating"):
        checks["theil_u2"] = {**checks["theil_u2"], "verdict": "not_applicable",
                              "reason": (f"The criterion is judged on a {criterion['window']}, so a "
                                         f"persistence benchmark at one-hour resolution is the "
                                         f"wrong comparison. Evaluated at the criterion window "
                                         f"during the performance trial instead.")}

    # Measures outside this criterion's gating set are computed and reported, but they do not
    # decide the verdict. Which measures gate depends on how the quantity is contracted - see
    # GATING in criteria.py.
    gating = set(criterion.get("gating_measures") or checks.keys())
    for k, c in list(checks.items()):
        if k not in gating and c["verdict"] in ("pass", "marginal", "fail"):
            checks[k] = {**c, "verdict": "reported",
                         "reason": criterion.get("gating_note", "Reported, not gating.")}

    graded = ("pass", "marginal", "fail")
    verdicts = [c["verdict"] for c in checks.values() if c["verdict"] in graded]
    overall = ("fail" if "fail" in verdicts else
               "marginal" if "marginal" in verdicts else
               "pass" if verdicts else "not_evaluated")
    return {
        "kpi": criterion["kpi"], "label": criterion["label"], "unit": criterion["unit"],
        "class": criterion["class"], "gates_acceptance": TOLERANCE_CLASSES[criterion["class"]]["gates_acceptance"],
        "n": n, "verdict": overall, "checks": checks, "statistics": rep,
        "reference_sigma": sigma, "observed_sd": round(obs_sd, 5),
        "discriminating": discriminating,
        "rmse_in_sigmas": round(rep["rmse"] / max(sigma, 1e-9), 2),
        "measurement_basis": criterion["measurement_basis"],
        "failed_checks": [k for k, c in checks.items() if c["verdict"] == "fail"],
        "gating_measures": sorted(gating),
        "suppressed_checks": [k for k, c in checks.items()
                              if c["verdict"] in ("not_discriminating", "not_applicable")],
        "reported_only": [k for k, c in checks.items() if c["verdict"] == "reported"],
    }


# --------------------------------------------------------------------------- accuracy run
def run_accuracy(plant_id: str, *, hours: int = 168, kpis: list[str] | None = None) -> dict[str, Any]:
    """Pair the twin against the plant over the replay history and grade every criterion.

    In a deployment the 'plant' side is the reconciled historian and the laboratory assays. Here
    it is the replay historian's measured series, which carries instrument noise, drift and the
    seeded fault events — so the residuals are of the right character for a demonstration.
    """
    from app.services.historian_service import REPLAY_HOURS, get_historian
    hist = get_historian()
    want = set(kpis or [c["kpi"] for c in KPI_CRITERIA])
    base_of = {c["kpi"]: c["kpi"].split("@")[0] for c in KPI_CRITERIA}
    obs: dict[str, list[float]] = {}
    pred: dict[str, list[float]] = {}
    clay: list[float] = []
    n_hours = int(min(hours, REPLAY_HOURS))
    excluded = 0
    for h in range(n_hours):
        t, m = hist.truth(plant_id, float(h)), hist.model(plant_id, float(h))
        tk, mk = t.get("kpis", {}), m.get("kpis", {})
        if not tk or not mk:
            excluded += 1
            continue
        thr = tk.get("throughput_tph")
        nameplate = t.get("mvs", {}).get("rom_feed_tph") or 600.0
        if thr is not None and nameplate and thr < 0.50 * float(nameplate):
            excluded += 1          # transient, excluded by rule
            continue
        clay.append(float(t.get("ore", {}).get("clay_share", 0.0)))
        for c in KPI_CRITERIA:
            k = c["kpi"]
            if k not in want:
                continue
            b = base_of[k]
            if b in tk and b in mk:
                obs.setdefault(k, []).append(float(tk[b]))
                pred.setdefault(k, []).append(float(mk[b]))

    results = []
    for c in KPI_CRITERIA:
        k = c["kpi"]
        if k not in obs:
            continue
        o, p = obs[k], pred[k]
        if "@high_clay" in k:                      # conditional criterion
            mask = [i for i, cl in enumerate(clay) if cl > 0.60]
            o = [obs[k][i] for i in mask]
            p = [pred[k][i] for i in mask]
        results.append(grade_kpi(c, o, p))

    gating = [r for r in results if r.get("gates_acceptance")]
    fails = [r for r in gating if r["verdict"] == "fail"]
    return {
        "plant_id": plant_id, "hours_evaluated": n_hours - excluded, "hours_excluded": excluded,
        "exclusion_pct": round(100 * excluded / max(n_hours, 1), 2),
        "results": results,
        "summary": {
            "evaluated": len(results),
            "pass": sum(1 for r in results if r["verdict"] == "pass"),
            "marginal": sum(1 for r in results if r["verdict"] == "marginal"),
            "fail": sum(1 for r in results if r["verdict"] == "fail"),
            "insufficient_data": sum(1 for r in results if r["verdict"] == "insufficient_data"),
            "class_a_fail": [r["kpi"] for r in results if r["class"] == "A" and r["verdict"] == "fail"],
        },
        "verdict": "fail" if fails else ("marginal" if any(r["verdict"] == "marginal" for r in gating)
                                         else "pass"),
        "data_source": "Replay historian measured series against the twin's modelled series.",
    }


# --------------------------------------------------------------------------- behaviour run
def run_behaviour(plant_id: str, scenario_id: str | None = None) -> dict[str, Any]:
    """Step tests graded on the sign and magnitude of the response."""
    from app.services.simulation_service import get_simulation_service
    sim = get_simulation_service()
    idx = scenario_index()
    ids = [scenario_id] if scenario_id else list(BEHAVIOUR_CHECKS)
    rows = []
    for sid in ids:
        chk = BEHAVIOUR_CHECKS.get(sid)
        if chk is None:
            continue
        a = sim.run_plant(plant_id, {chk["group"]: {chk["variable"]: chk["from"]}}, include_streams=False)
        b = sim.run_plant(plant_id, {chk["group"]: {chk["variable"]: chk["to"]}}, include_streams=False)
        checks = []
        for kpi, sign in chk["expect"].items():
            va, vb = a["kpis"].get(kpi), b["kpis"].get(kpi)
            if va is None or vb is None:
                checks.append({"kpi": kpi, "verdict": "not_evaluated"})
                continue
            d = float(vb) - float(va)
            rel = d / max(abs(float(va)), 1e-9)
            moved = abs(rel) > _REL_TOL
            ok = (d > 0 if sign > 0 else d < 0) if sign != 0 else not moved
            checks.append({"kpi": kpi, "expected": "rise" if sign > 0 else ("fall" if sign < 0 else "no change"),
                           "from": round(float(va), 4), "to": round(float(vb), 4),
                           "change": round(d, 4), "change_pct": round(100 * rel, 3),
                           "verdict": "pass" if (ok and (moved or sign == 0)) else
                                      ("fail" if not ok else "no_response")})
        for kpi, floor in (chk.get("floor") or {}).items():
            va, vb = a["kpis"].get(kpi), b["kpis"].get(kpi)
            if va is None or vb is None:
                checks.append({"kpi": kpi, "verdict": "not_evaluated"})
                continue
            rel = 100 * (float(vb) - float(va)) / max(abs(float(va)), 1e-9)
            checks.append({"kpi": kpi, "expected": f"not worse than {floor} %",
                           "from": round(float(va), 4), "to": round(float(vb), 4),
                           "change_pct": round(rel, 3),
                           "verdict": "pass" if rel >= floor else "fail"})
        for kpi, tol in (chk.get("bounded") or {}).items():
            va, vb = a["kpis"].get(kpi), b["kpis"].get(kpi)
            if va is None or vb is None:
                checks.append({"kpi": kpi, "verdict": "not_evaluated"})
                continue
            rel = 100 * (float(vb) - float(va)) / max(abs(float(va)), 1e-9)
            checks.append({"kpi": kpi, "expected": f"hold within +/- {tol} %",
                           "from": round(float(va), 4), "to": round(float(vb), 4),
                           "change_pct": round(rel, 3),
                           "verdict": "pass" if abs(rel) <= tol else "fail"})
        for key, sign in (chk.get("unit_expect") or {}).items():
            u, f = key.split(".", 1)
            va, vb = a["units"].get(u, {}).get(f), b["units"].get(u, {}).get(f)
            if va is None or vb is None:
                checks.append({"kpi": key, "verdict": "not_evaluated"})
                continue
            d = float(vb) - float(va)
            ok = d > 0 if sign > 0 else d < 0
            checks.append({"kpi": key, "expected": "rise" if sign > 0 else "fall",
                           "from": round(float(va), 4), "to": round(float(vb), 4),
                           "change": round(d, 4),
                           "verdict": "pass" if ok else "fail"})
        v = [c["verdict"] for c in checks]
        rows.append({
            "scenario_id": sid, "name": idx.get(sid, {}).get("name", sid),
            "step": {"variable": chk["variable"], "from": chk["from"], "to": chk["to"],
                     "group": chk["group"]},
            "rationale": chk["rationale"], "checks": checks,
            "verdict": "fail" if "fail" in v else ("pass" if all(x == "pass" for x in v) else "partial"),
        })
    return {"plant_id": plant_id, "rows": rows,
            "verdict": "fail" if any(r["verdict"] == "fail" for r in rows) else
                       ("partial" if any(r["verdict"] == "partial" for r in rows) else "pass"),
            "method": "Each step is solved twice by the twin and graded on the sign, and where "
                      "stated the magnitude, of the response. A model that hits every numerical "
                      "tolerance but moves a lever the wrong way fails here, which is the point."}


# --------------------------------------------------------------------------- fail-safe run
def run_fail_safe(plant_id: str) -> dict[str, Any]:
    """The twin asked something outside its validated envelope must say so."""
    from app.hybrid.builder import get_builder
    from app.services.plant_service import get_plant_service
    from app.services.simulation_service import get_simulation_service
    ore = ORE_SCENARIOS["S15_outside_envelope"]
    _, ore_cfg, op_cfg, _ = get_plant_service().configs(plant_id)
    point = {**op_cfg.model_dump(), **ore_cfg.model_dump(), **ore}
    env = envelope_check(point)
    res = get_simulation_service().run_plant(plant_id, {"ore": ore}, include_streams=False)
    builder = get_builder()
    ds = builder.dataset()
    built = builder.build("lump_al2o3_pct")
    mu = np.asarray(ds["X"], dtype=float).mean(axis=0)
    feats = {n: float(mu[i]) for i, n in enumerate(ds["feature_names"])}
    feats.update({k: v for k, v in ore.items() if k in feats})
    far = {k: v * 3.0 for k, v in feats.items()}
    gated_far = built["model"].predict(far, 2.0, mode="gated_residual")
    checks = [
        {"check": "Envelope flag raised", "verdict": "pass" if not env["inside_envelope"] else "fail",
         "detail": env["statement"]},
        {"check": "Offending variables named",
         "verdict": "pass" if env["variables_outside"] else "fail",
         "detail": ", ".join(env["variables_outside"]) or "none"},
        {"check": "Twin still solves and returns a result",
         "verdict": "pass" if res.get("kpis") else "fail",
         "detail": f"lump Fe {res['kpis'].get('lump_fe_pct')} %, "
                   f"alumina {res['kpis'].get('lump_al2o3_pct')} %"},
        {"check": "Hybrid correction gated off far outside the learned domain",
         "verdict": "pass" if gated_far["gate"] == 0.0 else "fail",
         "detail": f"gate {gated_far['gate']}, correction {gated_far['correction']}"},
        {"check": "Gated prediction equals the mechanistic prediction",
         "verdict": "pass" if abs(gated_far["value"] - gated_far["mechanistic"]) < 1e-9 else "fail",
         "detail": f"{gated_far['value']} vs {gated_far['mechanistic']}"},
    ]
    return {"plant_id": plant_id, "scenario_id": "S15_outside_envelope",
            "envelope": env, "checks": checks,
            "verdict": "fail" if any(c["verdict"] == "fail" for c in checks) else "pass",
            "statement": "Outside the validated envelope the twin returns a mechanistic result, "
                         "labels it, and switches the learned correction off. It does not "
                         "silently extrapolate."}


# --------------------------------------------------------------------------- system run
def run_system(plant_id: str, *, tests_pass: bool | None = None,
               availability_pct: float | None = None,
               data_completeness_pct: float | None = None) -> dict[str, Any]:
    """System criteria: what can be measured here is measured; the rest is marked as evidence
    to be supplied at the relevant gate rather than silently assumed."""
    from app.services.diagnostics_service import get_diagnostics_service
    from app.services.simulation_service import get_simulation_service
    sim = get_simulation_service()

    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = sim.run_plant(plant_id, {"operating": {"rom_feed_tph": 600.0 + 7 * len(times)}},
                            include_streams=False)
        times.append(1000 * (time.perf_counter() - t0))
    base = sim.run_plant(plant_id)
    bal = get_diagnostics_service().balance(plant_id)
    rows = {r["component"]: r for r in bal["rows"]}

    a = sim.run_plant(plant_id, include_streams=False)
    b = sim.run_plant(plant_id, include_streams=False)
    reproducible = all(abs(float(a["kpis"][k]) - float(b["kpis"][k])) < 1e-12
                       for k in a["kpis"] if isinstance(a["kpis"][k], (int, float)))

    from app.hybrid.builder import get_builder
    ex = get_builder().extrapolation_test("lump_al2o3_pct")
    gate_ok = bool(ex["conclusion"]["gated_converges_to_mechanistic"])

    try:
        from app.services.mpc_service import get_mpc_service
        sol = get_mpc_service().solve(plant_id)
        mpc_s = round(float(sol.get("solve_ms", 0.0)) / 1000.0, 3)
    except Exception:  # noqa: BLE001 — MPC is optional scope; absence is not a failure here
        mpc_s = None

    measured = {
        "closure_solids_pct": rows.get("Solids", {}).get("closure_pct"),
        "closure_fe_pct": rows.get("Iron units", {}).get("closure_pct"),
        # worst absolute departure from 100 %, expressed back as a closure figure, so that an
        # over-closure of 102.6 % counts against the model exactly as 97.4 % would
        "closure_elements_pct": (
            round(100.0 - max(abs(v - 100.0) for v in
                              (rows.get("Silica", {}).get("closure_pct"),
                               rows.get("Alumina", {}).get("closure_pct")) if v is not None), 3)
            if any(rows.get(k, {}).get("closure_pct") is not None for k in ("Silica", "Alumina"))
            else None),
        "solve_p95_ms": round(float(np.percentile(times, 95)), 1),
        "mpc_solve_s": mpc_s,
        "availability_pct": availability_pct,
        "data_completeness_pct": data_completeness_pct,
        "soft_sensor_latency_s": None,
        "reproducible": reproducible,
        "hybrid_gate_ok": gate_ok,
        "tests_pass": tests_pass,
        "constraint_penalty": base.get("constraint_penalty"),
    }
    out = []
    for c in SYSTEM_CRITERIA:
        v = measured.get(c["value_key"])
        if c["kind"] == "bool":
            verdict = "not_evaluated" if v is None else ("pass" if bool(v) else "fail")
            out.append({**c, "value": v, "verdict": verdict,
                        "evidence_required": verdict == "not_evaluated"})
        else:
            g = _grade_limit(v, c.get("threshold"), c["kind"], ceiling=c.get("ceiling"))
            out.append({**c, "value": g["value"], "verdict": g["verdict"],
                        "margin": g["margin"], "evidence_required": g["verdict"] == "not_evaluated"})
    gating = [r for r in out if TOLERANCE_CLASSES[r["class"]]["gates_acceptance"]]
    return {
        "plant_id": plant_id, "results": out,
        "measured": measured,
        "solve_times_ms": [round(t, 1) for t in times],
        "summary": {"pass": sum(1 for r in out if r["verdict"] == "pass"),
                    "fail": sum(1 for r in out if r["verdict"] == "fail"),
                    "marginal": sum(1 for r in out if r["verdict"] == "marginal"),
                    "evidence_required": sum(1 for r in out if r.get("evidence_required"))},
        "verdict": "fail" if any(r["verdict"] == "fail" for r in gating) else
                   ("incomplete" if any(r.get("evidence_required") for r in gating) else "pass"),
        "note": "Criteria that can only be measured on the live installation - availability, "
                "data completeness, latency - are marked as evidence required and are supplied "
                "at the site acceptance test rather than assumed here.",
    }


# --------------------------------------------------------------------------- full run
def run_all(plant_id: str, *, hours: int = 168, tests_pass: bool | None = None) -> dict[str, Any]:
    acc = run_accuracy(plant_id, hours=hours)
    beh = run_behaviour(plant_id)
    fs = run_fail_safe(plant_id)
    sysr = run_system(plant_id, tests_pass=tests_pass)
    order = {"fail": 3, "incomplete": 2, "partial": 2, "marginal": 1, "pass": 0}
    worst = max((acc["verdict"], beh["verdict"], fs["verdict"], sysr["verdict"]),
                key=lambda v: order.get(v, 0))
    blocking = (acc["summary"]["class_a_fail"]
                + [r["scenario_id"] for r in beh["rows"] if r["verdict"] == "fail"]
                + [r["id"] for r in sysr["results"] if r["verdict"] == "fail" and r["class"] == "A"]
                + ([fs["scenario_id"]] if fs["verdict"] == "fail" else []))
    outstanding = [r["name"] for r in sysr["results"] if r.get("evidence_required")]
    return {
        "plant_id": plant_id,
        "accuracy": acc, "behaviour": beh, "fail_safe": fs, "system": sysr,
        "overall_verdict": worst,
        "gate_readiness": {
            # availability, data completeness and latency are site-acceptance evidence, not
            # factory-acceptance criteria, so they do not hold up G1
            "G1_FAT": "ready" if not blocking else "not ready",
            "G2_SAT": "ready" if not blocking and not outstanding else "evidence outstanding",
            "blocking": blocking,
            "evidence_outstanding": outstanding,
        },
    }
