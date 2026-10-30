"""Services and HTTP API smoke tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.registry import get_registry
from app.services.data_quality_service import get_data_quality_service
from app.services.diagnostics_service import get_diagnostics_service
from app.services.historian_service import REPLAY_HOURS, get_historian
from app.services.live_service import get_live_service
from app.services.optimization_service import get_optimization_service
from app.services.overview_service import get_overview_service
from app.services.plant_service import get_plant_service
from app.services.simulation_service import get_simulation_service
from app.services.unit_service import get_unit_service

PLANT = "IX-OB-01"


@pytest.fixture(scope="module")
def client():
    get_registry().n_samples = 80          # keep ML training fast in CI
    return TestClient(app)


def test_plant_register():
    ps = get_plant_service()
    assert PLANT in ps.ids()
    assert len(ps.tags(PLANT)) > 20
    fs, ore, op, ec = ps.configs(PLANT)
    assert ore.fe_head_pct > 0 and op.rom_feed_tph > 0


def test_historian_replay_is_deterministic():
    h = get_historian()
    a = h.truth(PLANT, 12.0)["kpis"]["lump_fe_pct"]
    b = h.truth(PLANT, 12.0 + REPLAY_HOURS)["kpis"]["lump_fe_pct"]
    assert a == b


def test_historian_events_show_up_in_the_data():
    h = get_historian()
    during = h.truth(PLANT, 84.0)            # jig hutch-water pump fault window
    before = h.truth(PLANT, 70.0)
    assert during["mvs"]["lump_jig_hutch_water_m3_h"] < before["mvs"]["lump_jig_hutch_water_m3_h"]
    assert during["kpis"]["lump_al2o3_pct"] > before["kpis"]["lump_al2o3_pct"]


def test_sensor_fault_is_only_in_the_measurement():
    h = get_historian()
    meas = h.tag_value(PLANT, "302_AIC_025", 148.0, "measurement")
    truth = h.tag_value(PLANT, "302_AIC_025", 148.0, "truth")
    assert meas < truth                      # analyser drift reads low


def test_simulation_and_streams():
    r = get_simulation_service().run_plant(PLANT)
    assert r["kpis"]["lump_fe_pct"] > 58
    assert "S08_lump_ore" in r["streams"]
    assert len(r["streams"]["S08_lump_ore"]["psd"]["size_um"]) == 36
    assert r["sankey"]["links"]


def test_sensitivity_monotonic_in_amine():
    r = get_simulation_service().sensitivity(PLANT, "lump_jig_cut_sg", [3.6, 4.2, 4.7],
                                             ["lump_fe_pct", "lump_al2o3_pct"])
    fe = [row["lump_fe_pct"] for row in r["rows"]]
    al = [row["lump_al2o3_pct"] for row in r["rows"]]
    assert fe[0] < fe[-1] and al[0] > al[-1]


def test_optimizer_finds_a_feasible_improvement():
    r = get_optimization_service().optimise(PLANT, objective="margin", max_evals=80)
    assert r["constraint_penalty"] < 5.0
    assert r["optimised_kpis"]["margin_usd_h"] >= r["baseline_kpis"]["margin_usd_h"] - 1e-6


def test_monte_carlo_reports_feasibility():
    r = get_optimization_service().monte_carlo(PLANT, samples=6)
    assert 0 <= r["feasible_pct"] <= 100
    assert "lump_fe_pct" in r["summary"]


def test_live_snapshot_has_tags_and_constraints():
    s = get_live_service().snapshot(PLANT, hour=10.0)
    assert len(s["tags"]) > 20 and s["constraints"]
    assert all("status" in c for c in s["constraints"])
    assert s["soft_sensors"]


def test_overview_and_flowsheet():
    o = get_overview_service().overview(PLANT, hour=10.0)
    assert len(o["areas"]) == 9
    f = get_overview_service().flowsheet(PLANT, hour=10.0)
    assert len(f["nodes"]) >= 20 and len(f["edges"]) >= 28
    assert any(e.get("kind") == "recycle" for e in f["edges"])


def test_unit_detail_and_curves():
    d = get_unit_service().detail(PLANT, "lump_jig")
    assert d["state"] and d["curves"]["partition_curve"] and d["curves"]["grade_recovery"]
    d2 = get_unit_service().detail(PLANT, "whims")
    assert d2["curves"]["capture_curve"] and d2["curves"]["size_recovery"]
    d3 = get_unit_service().detail(PLANT, "spirals")
    assert d3["curves"]["size_window"]


def test_diagnostics_balance_closes():
    b = get_diagnostics_service().balance(PLANT)
    solids = next(r for r in b["rows"] if r["component"] == "Solids")
    assert 99.0 < solids["closure_pct"] < 101.0


def test_reconciliation_adjusts_measurements():
    r = get_diagnostics_service().reconcile(PLANT, hour=20.0)
    assert len(r["variables"]) == 6
    assert 60 < r["reconciled_recovery_pct"] < 99


def test_data_quality_flags_the_drifting_analyser():
    rep = get_data_quality_service().report(PLANT, hours=12.0, step_h=1.0)
    assert 0 <= rep["quality_score_pct"] <= 100
    assert len(rep["tags"]) > 20


# ---- HTTP -----------------------------------------------------------------------------------
def test_health_and_root(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("url", [
    "/api/v1/plants", "/api/v1/plants/IX-OB-01", "/api/v1/plants/IX-OB-01/tags",
    "/api/v1/metadata", "/api/v1/metadata/constraints", "/api/v1/metadata/objectives",
    "/api/v1/metadata/config-schema", "/api/v1/units", "/api/v1/units/lump_jig", "/api/v1/units/whims",
    "/api/v1/overview", "/api/v1/overview/flowsheet", "/api/v1/overview/shifts?shifts=2",
    "/api/v1/live/snapshot", "/api/v1/live/soft-sensors", "/api/v1/live/trend?hours=6",
    "/api/v1/diagnostics/balance", "/api/v1/diagnostics/events", "/api/v1/diagnostics/reconcile",
    "/api/v1/timeseries/replay-info", "/api/v1/timeseries/kpis?end_h=8",
    "/api/v1/optimization/objectives", "/api/v1/mpc/config", "/api/v1/simulation/grade-recovery?points=4", "/api/v1/simulation/washability",
])
def test_get_endpoints(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text
    assert r.json()


def test_simulation_run_endpoint(client):
    r = client.post("/api/v1/simulation/run", json={"plant_id": PLANT,
                                                    "operating": {"lump_jig_cut_sg": 4.6},
                                                    "include_streams": False})
    assert r.status_code == 200
    assert r.json()["kpis"]["lump_fe_pct"] > 60.0


def test_optimization_endpoint(client):
    r = client.post("/api/v1/optimization/run", json={"plant_id": PLANT, "objective": "fe_recovery",
                                                      "max_evals": 40})
    assert r.status_code == 200 and "setpoints" in r.json()


def test_mpc_endpoints(client):
    ident = client.get("/api/v1/mpc/identification").json()
    assert ident["gain_matrix"]
    sol = client.post("/api/v1/mpc/solve", json={"plant_id": PLANT, "hour": 12.0}).json()
    assert sol["status"] in ("optimal", "suboptimal")
    assert sol["handover"]["setpoints"]
    sim = client.post("/api/v1/mpc/simulate", json={"plant_id": PLANT, "steps": 12}).json()
    assert sim["closed_loop"]["metrics"]["rmse"]
    adv = client.get("/api/v1/mpc/advisory").json()
    assert adv["pairing"]["pairings"]


def test_ml_endpoints(client):
    st = client.get("/api/v1/ml/status").json()
    assert st["features"] and st["targets"]
    pred = client.post("/api/v1/ml/predict", json={"plant_id": PLANT, "hour": 12.0,
                                                   "targets": ["lump_fe_pct"]}).json()
    assert pred["predictions"][0]["value"] > 0
    imp = client.get("/api/v1/ml/importance?target=lump_fe_pct").json()
    assert imp["importance"]
    an = client.get("/api/v1/ml/anomaly?hours=6&step_h=2").json()
    assert an["rows"]


def test_unknown_plant_returns_404(client):
    assert client.get("/api/v1/plants/NOPE").status_code == 404
