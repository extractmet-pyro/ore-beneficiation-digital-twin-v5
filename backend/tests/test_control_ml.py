"""Supervisory control (identification + MPC) and the machine-learning layer."""
from __future__ import annotations

import numpy as np
import pytest

from app.control.advisory import operator_guidance, pairing_analysis, readiness
from app.control.identification import CVS, MVS, identify, step_response
from app.control.mpc import MPCController, handover_payload
from app.ml.anomaly import AnomalyDetector, drift_report, psi
from app.ml.dataset import FEATURES, TARGETS, build_dataset
from app.ml.models import learning_curve, partial_dependence, train_model
from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.twin.circuit import solve


@pytest.fixture(scope="module")
def ident():
    return identify(FlowsheetConfig(), OreConfig(), OperatingConfig(), EconomicsConfig(),
                    mv_keys=["lump_jig_cut_sg", "scrubber_speed_pct_critical", "spiral_conc_splitter",
                             "whims_field_tesla"],
                    cv_keys=["lump_al2o3_pct", "lump_fe_pct", "fines_fe_pct", "fe_recovery_pct"])


@pytest.fixture(scope="module")
def dataset():
    return build_dataset(n=90, seed=5, noise_pct=0.5)


def test_identification_shapes_and_signs(ident):
    g = np.array(ident["gain_matrix"])
    assert g.shape == (4, 4)
    i_al = ident["cv_keys"].index("lump_al2o3_pct")
    j_cut = ident["mv_keys"].index("lump_jig_cut_sg")
    assert g[i_al, j_cut] < 0              # a tighter jig cut rejects more clay-bearing middling
    i_fe = ident["cv_keys"].index("lump_fe_pct")
    assert g[i_fe, j_cut] > 0              # ... and lifts the lump Fe grade
    assert ident["condition_number"] > 0


def test_step_response_reaches_the_gain():
    y = step_response(2.0, 10.0, 5.0, horizon_min=120, dt_min=2.0)
    assert y[0] == 0.0
    assert y[-1] == pytest.approx(2.0, rel=0.02)


def test_mpc_moves_towards_the_target(ident):
    ctrl = MPCController(ident, horizon=16, control_horizon=3, dt_min=5.0)
    base = solve(FlowsheetConfig(), OreConfig(), OperatingConfig(), EconomicsConfig())
    y = {c: base["kpis"][c] for c in ctrl.cv_keys}
    u = {m: float(getattr(OperatingConfig(), m)) for m in ctrl.mv_keys}
    y["lump_al2o3_pct"] = 2.9
    sol = ctrl.solve(y, u, targets={"lump_al2o3_pct": 2.1})
    assert sol["status"] in ("optimal", "suboptimal")
    assert sol["predicted"]["lump_al2o3_pct"][-1] < y["lump_al2o3_pct"]
    assert sol["moves"]["lump_jig_cut_sg"] > 0


def test_mpc_respects_move_and_range_limits(ident):
    ctrl = MPCController(ident, horizon=12, control_horizon=2, dt_min=5.0)
    u = {m: float(getattr(OperatingConfig(), m)) for m in ctrl.mv_keys}
    y = {c: 0.0 for c in ctrl.cv_keys}
    y.update({"lump_al2o3_pct": 4.5, "lump_fe_pct": 57.0, "fines_fe_pct": 58.0, "fe_recovery_pct": 78.0})
    sol = ctrl.solve(y, u, targets={"lump_al2o3_pct": 1.6})
    from app.control.identification import MV_BY_KEY
    for m, d in sol["moves"].items():
        assert abs(d) <= MV_BY_KEY[m]["max_move"] + 1e-6
        assert MV_BY_KEY[m]["lo"] - 1e-6 <= sol["u_next"][m] <= MV_BY_KEY[m]["hi"] + 1e-6


def test_closed_loop_beats_open_loop(ident):
    ctrl = MPCController(ident, horizon=14, control_horizon=3, dt_min=5.0)
    base = solve(FlowsheetConfig(), OreConfig(), OperatingConfig(), EconomicsConfig())
    y = {c: base["kpis"][c] for c in ctrl.cv_keys}
    u = {m: float(getattr(OperatingConfig(), m)) for m in ctrl.mv_keys}
    dist = {"lump_al2o3_pct": [0.0] * 4 + [0.75] * 20}
    targets = dict(y)                      # hold the current operating point, then disturb the silica
    closed = ctrl.simulate(y, u, steps=24, disturbance=dist, seed=3, targets=targets)
    open_loop = ctrl.simulate(y, u, steps=24, disturbance=dist, seed=3, controller_on=False, targets=targets)
    assert closed["metrics"]["zone_rmse"]["lump_al2o3_pct"] <= open_loop["metrics"]["zone_rmse"]["lump_al2o3_pct"]
    assert closed["metrics"]["violations"] < open_loop["metrics"]["violations"]


def test_handover_payload_is_complete(ident):
    ctrl = MPCController(ident, horizon=12, control_horizon=2, dt_min=5.0)
    base = solve(FlowsheetConfig(), OreConfig(), OperatingConfig(), EconomicsConfig())
    y = {c: base["kpis"][c] for c in ctrl.cv_keys}
    u = {m: float(getattr(OperatingConfig(), m)) for m in ctrl.mv_keys}
    p = handover_payload(ctrl.solve(y, u))
    assert p["mode"] == "advisory" and len(p["checksum"]) == 16
    assert all({"tag", "value", "ramp_rate_per_min"} <= set(sp) for sp in p["setpoints"])


def test_pairing_and_readiness(ident):
    pa = pairing_analysis(ident)
    assert len(pa["pairings"]) == len(ident["cv_keys"])
    r = readiness({"302_AIC_025": "bad"}, ident)
    assert r["ready_for_closed_loop"] is False
    assert r["readiness_score_pct"] < 100


def test_operator_guidance_is_actionable():
    base = solve(FlowsheetConfig(), OreConfig(), OperatingConfig(), EconomicsConfig())
    from app.twin.constraints import evaluate_all
    rows = operator_guidance(evaluate_all(base), base["kpis"])
    assert all("action" in r and r["action"] for r in rows)


def test_mv_cv_registers_are_consistent():
    assert len(MVS) >= 20 and len(CVS) >= 6
    for m in MVS:
        assert m["lo"] < m["hi"] and m["max_move"] > 0
        assert hasattr(OperatingConfig(), m["key"])


def test_dataset_covers_features_and_targets(dataset):
    assert dataset["n"] > 60
    assert dataset["X"].shape[1] == len(FEATURES)
    assert dataset["Y"].shape[1] == len(TARGETS)
    assert np.isfinite(dataset["X"]).all() and np.isfinite(dataset["Y"]).all()


def test_soft_sensor_model_learns(dataset):
    m = train_model(dataset, "lump_fe_pct")
    assert m.metrics["r2_test"] > 0.5
    assert m.metrics["cv_folds"] >= 2
    assert m.importance and m.residual_sigma > 0
    p = m.predict({f: float(v) for f, v in zip(dataset["feature_names"], dataset["X"][0])})
    assert p["interval_95"][0] < p["value"] < p["interval_95"][1]


def test_hybrid_model_corrects_a_biased_twin(dataset):
    y = dataset["Y"][:, dataset["target_names"].index("lump_al2o3_pct")]
    twin = 0.9 * y + 0.4                       # systematically biased physics prediction
    hybrid = train_model(dataset, "lump_al2o3_pct", hybrid_baseline=twin)
    idx = 3
    feats = {f: float(v) for f, v in zip(dataset["feature_names"], dataset["X"][idx])}
    pred = hybrid.predict(feats, twin_value=float(twin[idx]))
    assert abs(pred["value"] - y[idx]) < abs(twin[idx] - y[idx])


def test_learning_curve_and_partial_dependence(dataset):
    lc = learning_curve(dataset, "lump_fe_pct", fractions=(0.4, 1.0))
    assert lc[-1]["n_train"] >= lc[0]["n_train"]
    m = train_model(dataset, "lump_fe_pct")
    pd = partial_dependence(m, dataset, "lump_jig_cut_sg", points=8)
    assert len(pd["x"]) == len(pd["y"]) == 8


def test_anomaly_detector_flags_out_of_envelope(dataset):
    det = AnomalyDetector().fit(dataset["X"], dataset["feature_names"])
    normal = {f: float(v) for f, v in zip(dataset["feature_names"], np.median(dataset["X"], axis=0))}
    weird = dict(normal)
    weird["lump_jig_cut_sg"] = 6.5
    weird["scrubber_water_m3_h"] = 2400.0
    assert det.score(weird)["anomaly_score"] > det.score(normal)["anomaly_score"]
    assert det.score(weird)["drivers"]


def test_psi_and_drift_report(dataset):
    ref = dataset
    shifted = {**dataset, "X": dataset["X"] * 1.35}
    rep = drift_report(ref, shifted)
    assert rep["n_drifted"] > 0
    assert psi(dataset["X"][:, 0], dataset["X"][:, 0]) < 0.02
