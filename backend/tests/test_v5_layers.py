"""Tests for the three v5 layers: plant 3-D model, hybrid model, validation and acceptance."""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.hybrid.builder import HYBRID_TARGETS, get_builder
from app.hybrid.composition import MODES
from app.hybrid.domain import DomainOfValidity
from app.main import app
from app.plant3d.bindings import asset_detail, state_frame
from app.plant3d.geometry import aabb, clash_check, footprint, gltf_manifest, routes, scene_graph
from app.plant3d.importers import import_spec, match_nodes, solve_registration
from app.plant3d.model import ASSETS, LEVELS, OVERLAYS
from app.services.simulation_service import get_simulation_service
from app.validation import metrics as M
from app.validation.criteria import KPI_CRITERIA, SYSTEM_CRITERIA, catalogue as crit_cat
from app.validation.runner import grade_kpi, run_behaviour, run_fail_safe, run_system
from app.validation.scenarios import SCENARIOS, envelope_check

client = TestClient(app)
PLANT = "IX-OB-01"


@pytest.fixture(scope="module")
def sim():
    return get_simulation_service().run_plant(PLANT)


# =================================================================== plant 3-D model
class TestPlant3DModel:
    def test_scene_graph_is_complete_and_tagged(self):
        sg = scene_graph()
        eq = [n for n in sg["nodes"] if n["kind"] == "equipment"]
        assert len(eq) == len(ASSETS)
        assert all(n["tag"] for n in eq), "every piece of equipment carries a plant tag"
        assert len({n["tag"] for n in eq}) == len(eq), "tags are unique"
        assert sg["counts"]["bound_to_twin"] >= 15

    def test_every_binding_resolves_against_a_real_result(self, sim):
        """A binding that points at a key the twin does not produce is a silent dead channel."""
        frame = {a["asset_id"]: a for a in state_frame(sim)["assets"]}
        dead = []
        for a in ASSETS:
            f = frame[a["asset_id"]]
            for b in a["bindings"]:
                if b["channel"] == "status":
                    continue
                if b["channel"] in ("fill", "duty", "rotation") and b["channel"] not in f["channels"]:
                    dead.append(f"{a['asset_id']}.{b['channel']} -> {b['key']}")
        assert not dead, f"bindings that resolve to nothing: {dead}"

    def test_status_bindings_name_real_constraints(self, sim):
        keys = {c["key"] for c in sim["constraints"]}
        bad = [b["key"] for a in ASSETS for b in a["bindings"]
               if b["channel"] == "status" and b["key"] not in keys]
        assert not bad, f"status bindings pointing at unknown constraints: {bad}"

    def test_layout_is_clash_free(self):
        c = clash_check(clearance_m=0.5)
        assert c["clean"], f"layout clashes: {c['clashes']}"

    def test_routes_connect_real_assets_both_ends(self):
        ids = {a["asset_id"] for a in ASSETS}
        rs = routes()
        assert len(rs) >= 25
        for r in rs:
            assert r["from_asset"] in ids and r["to_asset"] in ids
            assert len(r["path"]) >= 2 and r["length_m"] > 0

    def test_footprints_and_boxes_are_positive(self):
        for a in ASSETS:
            dx, dy, dz = footprint(a)
            assert min(dx, dy, dz) > 0, a["asset_id"]
            box = aabb(a)
            assert all(box["max"][i] > box["min"][i] for i in range(3)), a["asset_id"]

    def test_levels_cover_every_asset(self):
        ids = {lv["level_id"] for lv in LEVELS}
        assert all(a["level"] in ids for a in ASSETS)

    def test_state_frame_tracks_the_process(self):
        sim = get_simulation_service()
        lo = state_frame(sim.run_plant(PLANT, {"operating": {"rom_feed_tph": 450.0}}))
        hi = state_frame(sim.run_plant(PLANT, {"operating": {"rom_feed_tph": 760.0}}))
        a = {x["asset_id"]: x for x in lo["assets"]}
        b = {x["asset_id"]: x for x in hi["assets"]}
        assert b["scrubber"]["throughput_tph"] > a["scrubber"]["throughput_tph"]
        assert hi["summary"]["total_power_kw"] > lo["summary"]["total_power_kw"]
        assert b["lump_jig"]["duty_pct"] > a["lump_jig"]["duty_pct"]

    @pytest.mark.parametrize("overlay", [o["id"] for o in OVERLAYS])
    def test_every_overlay_produces_values(self, sim, overlay):
        f = state_frame(sim, overlay=overlay)
        assert f["overlay"] == overlay
        if overlay != "none":
            vals = [a["overlay_value"] for a in f["assets"]
                    if isinstance(a["overlay_value"], (int, float))]
            assert vals, f"overlay '{overlay}' coloured nothing"

    def test_asset_detail_carries_streams_and_datasheet(self, sim):
        d = asset_detail("whims", sim)
        assert d["asset"]["tag"] == "602-MS-001"
        assert d["asset"]["datasheet"]["units"] == 3
        assert d["unit_result"]["field_tesla"] > 0
        assert any(s["direction"] == "out" for s in d["streams"])
        assert asset_detail("no_such_asset", sim) is None

    def test_gltf_manifest_is_well_formed(self):
        g = gltf_manifest()
        assert g["asset"]["version"] == "2.0"
        assert len(g["nodes"]) == len(ASSETS)
        assert g["scenes"][0]["nodes"] == list(range(len(ASSETS)))
        for n in g["nodes"]:
            assert len(n["translation"]) == 3 and len(n["scale"]) == 3
            assert n["extras"]["tag"]


class TestPlant3DImport:
    def test_tag_matching_is_exact_and_refuses_to_guess(self):
        m = match_nodes(["301-JG-001", "EQUIP 201-SC-001 DRUM", "Mesh_0042", "602-MS-001"])
        got = {x["node"]: x["asset_id"] for x in m["matched"]}
        assert got["301-JG-001"] == "lump_jig"
        assert got["EQUIP 201-SC-001 DRUM"] == "scrubber"
        assert got["602-MS-001"] == "whims"
        assert any(u["node"] == "Mesh_0042" for u in m["unmatched"]), \
            "a meaningless node name must not be bound on a guess"

    def test_duplicate_bindings_are_reported(self):
        m = match_nodes(["301-JG-001", "301-JG-001 copy"])
        assert m["duplicate_bindings"] or m["ambiguous"]
        assert not m["ready"]

    def test_registration_recovers_a_known_transform(self):
        rng = np.random.default_rng(3)
        src = rng.normal(size=(6, 3)) * 20
        th = np.radians(37.0)
        R = np.array([[np.cos(th), 0, np.sin(th)], [0, 1, 0], [-np.sin(th), 0, np.cos(th)]])
        tgt = 1.0 * (R @ src.T).T + np.array([12.0, -3.0, 7.5])
        out = solve_registration([{"source": s.tolist(), "target": t.tolist()}
                                  for s, t in zip(src, tgt)])
        assert out["ok"] and out["quality"] == "good"
        assert out["residual_m"]["rms"] < 1e-6
        assert abs(out["scale"] - 1.0) < 1e-6
        assert np.allclose(out["translation_m"], [12.0, -3.0, 7.5], atol=1e-3)

    def test_registration_needs_three_points(self):
        out = solve_registration([{"source": [0, 0, 0], "target": [1, 1, 1]}])
        assert not out["ok"]

    def test_import_spec_states_limits_as_well_as_formats(self):
        s = import_spec()
        assert len(s["formats"]) >= 6
        assert any("gltf" in f["extensions"][0] or ".glb" in f["extensions"] for f in s["formats"])
        assert len(s["limits"]) >= 3 and len(s["workflow"]) >= 5


# =================================================================== hybrid model
class TestHybrid:
    def test_domain_separates_inside_from_outside(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(300, 4))
        d = DomainOfValidity().fit(X, ["a", "b", "c", "d"])
        inside = d.score({"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0})
        outside = d.score({"a": 40.0, "b": 40.0, "c": 40.0, "d": 40.0})
        assert inside["verdict"] == "inside" and inside["confidence"] == 1.0
        assert outside["verdict"] == "outside" and outside["confidence"] == 0.0
        assert outside["features_outside"]

    def test_domain_confidence_decreases_monotonically(self):
        rng = np.random.default_rng(1)
        d = DomainOfValidity().fit(rng.normal(size=(300, 3)), ["a", "b", "c"])
        conf = [d.score({"a": s, "b": s, "c": s})["confidence"] for s in (0, 1, 2, 4, 8, 16)]
        assert conf == sorted(conf, reverse=True)
        assert conf[0] == 1.0 and conf[-1] == 0.0

    @pytest.mark.parametrize("target", HYBRID_TARGETS)
    def test_hybrid_builds_for_every_declared_target(self, target):
        b = get_builder().build(target)
        assert b["residual"].hybrid is True
        assert b["direct"].hybrid is False
        assert b["model"].domain.names

    def test_correction_is_bounded(self):
        built = get_builder().build("lump_al2o3_pct")
        m = built["model"]
        feats = {n: float(v) for n, v in zip(m.domain.names, m.domain.mu)}
        out = m.predict(feats, 2.0, mode="gated_residual")
        cap = min(m.max_correction_sigma * m.residual_model.residual_sigma,
                  m.max_correction_frac * 2.0)
        assert abs(out["correction"]) <= cap + 1e-9

    def test_gated_mode_falls_back_to_physics_outside_the_domain(self):
        ex = get_builder().extrapolation_test("lump_al2o3_pct")
        assert ex["conclusion"]["gated_converges_to_mechanistic"] is True
        assert ex["rows"][-1]["gate"] == 0.0
        assert ex["rows"][0]["gate"] == 1.0
        # the data-only model has no such discipline, which is the point of the test
        assert ex["conclusion"]["data_only_departure"] > ex["conclusion"]["ungated_departure"]

    def test_attribution_sums_to_a_hundred(self):
        built = get_builder().build("lump_fe_pct")
        m = built["model"]
        feats = {n: float(v) for n, v in zip(m.domain.names, m.domain.mu)}
        a = m.predict(feats, 63.0)["attribution"]
        assert abs(a["mechanistic_pct"] + a["learned_pct"] - 100.0) < 0.05

    def test_hybrid_beats_mechanistic_in_domain(self):
        c = get_builder().compare("lump_al2o3_pct", n_test=80)
        assert c["results"]["gated_residual"]["rmse"] < c["results"]["mechanistic_only"]["rmse"]
        assert c["improvement_vs_mechanistic_pct"] > 0

    def test_every_mode_is_reachable(self):
        built = get_builder().build("lump_al2o3_pct")
        m = built["model"]
        feats = {n: float(v) for n, v in zip(m.domain.names, m.domain.mu)}
        for spec in MODES:
            if spec["id"] == "serial_parameter":
                continue          # needs a configured parameter solver
            out = m.predict(feats, 2.0, mode=spec["id"])
            assert out["mode"] == spec["id"] and np.isfinite(out["value"])


# =================================================================== validation
class TestMetrics:
    def test_perfect_prediction(self):
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert M.bias(y, y) == 0.0 and M.rmse(y, y) == 0.0
        assert M.r2(y, y) == 1.0

    def test_bias_sign_is_model_minus_plant(self):
        assert M.bias([1.0, 1.0], [2.0, 2.0]) == 1.0

    def test_theil_u2_detects_a_model_worse_than_persistence(self):
        rng = np.random.default_rng(5)
        obs = np.cumsum(rng.normal(size=200))
        good = obs + rng.normal(scale=0.05, size=200)
        bad = obs.mean() + rng.normal(scale=3.0, size=200)
        assert M.theil_u2(obs, good) < 1.0 < M.theil_u2(obs, bad)

    def test_coverage_counts_the_interval(self):
        y = np.zeros(100)
        assert M.coverage(y, np.full(100, -1.0), np.full(100, 1.0)) == 100.0
        assert M.coverage(y, np.full(100, 0.5), np.full(100, 1.0)) == 0.0

    def test_bland_altman_limits_bracket_the_mean(self):
        rng = np.random.default_rng(7)
        a = rng.normal(size=500)
        b = a + rng.normal(scale=0.2, size=500) + 0.5
        ba = M.bland_altman(a, b)
        assert ba["loa_lower"] < ba["mean_difference"] < ba["loa_upper"]
        assert abs(ba["mean_difference"] - 0.5) < 0.05

    def test_paired_t_finds_a_real_bias_and_ignores_noise(self):
        rng = np.random.default_rng(11)
        a = rng.normal(size=400)
        assert M.paired_t_on_bias(a, a + rng.normal(scale=0.1, size=400) + 0.3)["significant_bias"]
        assert not M.paired_t_on_bias(a, a + rng.normal(scale=0.1, size=400))["significant_bias"]

    def test_full_report_has_every_measure(self):
        rng = np.random.default_rng(13)
        a = rng.normal(size=120)
        r = M.full_report(a, a + rng.normal(scale=0.1, size=120))
        for k in ("bias", "mae", "rmse", "r2", "theil_u2", "bland_altman", "paired_t", "ks",
                  "residual_profile", "durbin_watson"):
            assert k in r


class TestCriteria:
    def test_no_tolerance_is_tighter_than_its_measurement(self):
        """The rule the whole criteria table is built on, enforced as a test."""
        offenders = [c["kpi"] for c in KPI_CRITERIA
                     if c["limits"]["max_rmse"] < c["reference_sigma"]]
        assert not offenders, f"RMSE limit below the measurement's own sigma: {offenders}"

    def test_limits_are_ordered_bias_then_mae_then_rmse(self):
        for c in KPI_CRITERIA:
            L = c["limits"]
            assert L["max_abs_bias"] <= L["max_mae"] <= L["max_rmse"], c["kpi"]

    def test_every_criterion_declares_its_basis_and_sample_floor(self):
        for c in KPI_CRITERIA:
            assert c["measurement_basis"] and c["n_min"] >= 10 and c["window"]

    def test_assays_gate_on_absolute_error_and_flows_on_relative(self):
        """An absolute tonnage tolerance cannot be carried between plants of different size, and
        a relative assay tolerance punishes the plant with the cleaner product. Each quantity
        gates on the measure it is actually contracted in."""
        by = {c["kpi"]: c for c in KPI_CRITERIA}
        assert "mape_pct" not in by["lump_al2o3_pct"]["gating_measures"]
        assert "rmse" in by["lump_al2o3_pct"]["gating_measures"]
        assert "mape_pct" in by["lump_tph"]["gating_measures"]
        assert "rmse" not in by["lump_tph"]["gating_measures"]
        for c in KPI_CRITERIA:
            assert c["gating_measures"], c["kpi"]
            assert c["quantity_kind"] in ("assay", "percentage", "flow", "rate"), c["kpi"]

    def test_non_gating_measures_are_reported_not_hidden(self):
        c = next(x for x in KPI_CRITERIA if x["kpi"] == "lump_tph")
        rng = np.random.default_rng(23)
        obs = 300.0 + rng.normal(scale=25.0, size=200)
        out = grade_kpi(c, obs, obs + rng.normal(scale=3.0, size=200))
        assert "rmse" in out["reported_only"], "the absolute error is still computed and shown"
        assert out["checks"]["rmse"]["value"] is not None
        assert "reason" in out["checks"]["rmse"]

    def test_class_a_and_b_gate_acceptance_and_c_does_not(self):
        cat = crit_cat()
        assert cat["tolerance_classes"]["A"]["gates_acceptance"] is True
        assert cat["tolerance_classes"]["C"]["gates_acceptance"] is False

    def test_system_criteria_are_complete(self):
        for c in SYSTEM_CRITERIA:
            assert c["kind"] in ("min", "max", "bool") and c["method"]
            if c["kind"] != "bool":
                assert c.get("threshold") is not None

    def test_grade_refuses_a_verdict_below_the_sample_floor(self):
        c = next(x for x in KPI_CRITERIA if x["kpi"] == "lump_fe_pct")
        out = grade_kpi(c, [62.0, 62.1, 62.2], [62.0, 62.1, 62.2])
        assert out["verdict"] == "insufficient_data"

    def test_grade_fails_a_biased_model(self):
        c = next(x for x in KPI_CRITERIA if x["kpi"] == "lump_fe_pct")
        rng = np.random.default_rng(17)
        obs = 62.0 + rng.normal(scale=1.0, size=200)
        out = grade_kpi(c, obs, obs + 2.0)
        assert out["verdict"] == "fail" and "bias" in out["failed_checks"]

    def test_grade_suppresses_correlation_on_a_flat_series(self):
        c = next(x for x in KPI_CRITERIA if x["kpi"] == "lump_fe_pct")
        rng = np.random.default_rng(19)
        obs = 62.0 + rng.normal(scale=0.02, size=200)     # moves far less than the assay sigma
        out = grade_kpi(c, obs, obs + rng.normal(scale=0.02, size=200))
        assert out["discriminating"] is False
        assert out["checks"]["r2"]["verdict"] == "not_discriminating"
        assert "reason" in out["checks"]["r2"]
        assert out["verdict"] == "pass"


class TestEnvelopeAndScenarios:
    def test_envelope_classifies_inside_and_outside(self):
        assert envelope_check({"rom_feed_tph": 600.0})["inside_envelope"]
        out = envelope_check({"rom_feed_tph": 1200.0, "clay_share": 0.9})
        assert not out["inside_envelope"]
        assert set(out["variables_outside"]) == {"rom_feed_tph", "clay_share"}

    def test_envelope_flags_the_edge(self):
        out = envelope_check({"rom_feed_tph": 390.0})
        assert "rom_feed_tph" in out["near_edge"]

    def test_scenarios_cover_every_kind(self):
        kinds = {s["kind"] for s in SCENARIOS}
        assert {"accuracy", "behaviour", "fault", "fail_safe", "excluded"} <= kinds
        assert len(SCENARIOS) >= 15

    def test_scenarios_declare_expected_behaviour(self):
        for s in SCENARIOS:
            assert s["expected_behaviour"] and s["purpose"] and s["numerical_criteria"]


class TestValidationRuns:
    @pytest.mark.parametrize("plant", ["IX-OB-01", "IX-OB-02", "IX-OB-03"])
    def test_accuracy_passes_on_every_reference_plant(self, plant):
        from app.validation.runner import run_accuracy
        a = run_accuracy(plant)
        assert a["summary"]["fail"] == 0, f"{plant}: {a['summary']['class_a_fail']}"
        assert a["verdict"] in ("pass", "marginal")

    def test_a_criterion_with_no_matching_data_gives_no_verdict(self):
        """IX-OB-03 runs a low-clay ore, so the high-clay criterion has nothing to grade. The
        right answer is silence, not a pass."""
        from app.validation.runner import run_accuracy
        a = run_accuracy("IX-OB-03")
        hc = next(r for r in a["results"] if r["kpi"] == "lump_al2o3_pct@high_clay")
        assert hc["verdict"] == "insufficient_data"

    @pytest.mark.parametrize("plant", ["IX-OB-01", "IX-OB-02", "IX-OB-03"])
    def test_behaviour_suite_passes_on_every_reference_plant(self, plant):
        b = run_behaviour(plant)
        bad = [(r["scenario_id"], [c["kpi"] for c in r["checks"] if c["verdict"] != "pass"])
               for r in b["rows"] if r["verdict"] != "pass"]
        assert not bad, f"{plant}: behaviour scenarios not passing: {bad}"

    def test_a_better_than_expected_response_is_not_a_failure(self):
        """The WHIMS grade check is one-sided. A concentrate grade that improves when the field
        is raised is the right answer on a deslimed feed, and a symmetric band would score it as
        a defect."""
        r = run_behaviour(PLANT, "S09_whims_field")["rows"][0]
        chk = next(c for c in r["checks"] if c["kpi"] == "pellet_fines_fe_pct")
        assert "not worse than" in chk["expected"]
        assert chk["verdict"] == "pass"

    def test_scrubber_dilution_response_is_counter_intuitive_and_correct(self):
        """More dilution water must make the lump product worse, not better."""
        r = next(x for x in run_behaviour(PLANT, "S07b_scrubber_dilution")["rows"])
        chk = next(c for c in r["checks"] if c["kpi"] == "lump_al2o3_pct")
        assert chk["verdict"] == "pass" and chk["change"] > 0

    def test_fail_safe_declines_to_extrapolate(self):
        f = run_fail_safe(PLANT)
        assert f["verdict"] == "pass"
        assert not f["envelope"]["inside_envelope"]
        assert all(c["verdict"] == "pass" for c in f["checks"])

    def test_system_run_reports_evidence_rather_than_assuming_it(self):
        s = run_system(PLANT, tests_pass=True)
        assert s["verdict"] in ("pass", "incomplete")
        ev = [r["id"] for r in s["results"] if r.get("evidence_required")]
        assert "availability" in ev, "a site-only measure must not be silently assumed"
        assert s["measured"]["reproducible"] is True
        assert s["measured"]["hybrid_gate_ok"] is True


# =================================================================== API
class TestV5Api:
    @pytest.mark.parametrize("path,params", [
        ("/api/v1/plant3d/model", {}),
        ("/api/v1/plant3d/state", {"overlay": "fe"}),
        ("/api/v1/plant3d/levels", {}),
        ("/api/v1/plant3d/clash", {}),
        ("/api/v1/plant3d/gltf-manifest", {}),
        ("/api/v1/plant3d/import-spec", {}),
        ("/api/v1/plant3d/import-formats", {}),
        ("/api/v1/hybrid/config", {}),
        ("/api/v1/hybrid/modes", {}),
        ("/api/v1/hybrid/predict", {}),
        ("/api/v1/hybrid/attribution", {}),
        ("/api/v1/hybrid/domain-check", {}),
        ("/api/v1/hybrid/extrapolation", {"steps": 6}),
        ("/api/v1/validation/criteria", {}),
        ("/api/v1/validation/scenarios", {}),
        ("/api/v1/validation/protocol", {}),
        ("/api/v1/validation/envelope", {"plant_id": PLANT}),
        ("/api/v1/validation/certificate", {}),
    ])
    def test_endpoint_returns_json(self, path, params):
        r = client.get(path, params=params)
        assert r.status_code == 200, r.text[:300]
        assert r.json()

    def test_model_can_be_filtered_by_level_and_area(self):
        full = client.get("/api/v1/plant3d/model").json()
        one = client.get("/api/v1/plant3d/model", params={"area": "A500",
                                                          "include_structures": False}).json()
        assert 0 < len(one["nodes"]) < len(full["nodes"])
        assert all(n["area"] == "A500" for n in one["nodes"])

    def test_unknown_asset_and_plant_are_404(self):
        assert client.get("/api/v1/plant3d/asset/nope").status_code == 404
        assert client.get("/api/v1/plant3d/state", params={"plant_id": "ZZ"}).status_code == 404

    def test_unknown_overlay_and_target_are_400(self):
        assert client.get("/api/v1/plant3d/state", params={"overlay": "nope"}).status_code == 400
        assert client.get("/api/v1/hybrid/predict", params={"target": "nope"}).status_code == 400

    def test_import_match_endpoint(self):
        r = client.post("/api/v1/plant3d/import/match",
                        json={"node_names": ["301-JG-001", "nonsense"]})
        assert r.status_code == 200
        assert r.json()["matched"][0]["asset_id"] == "lump_jig"
        assert client.post("/api/v1/plant3d/import/match", json={}).status_code == 400

    def test_registration_endpoint(self):
        r = client.post("/api/v1/plant3d/import/register", json={"pairs": [
            {"source": [0, 0, 0], "target": [10, 0, 5]},
            {"source": [10, 0, 0], "target": [20, 0, 5]},
            {"source": [0, 0, 10], "target": [10, 0, 15]}]})
        assert r.status_code == 200 and r.json()["quality"] == "good"
        assert client.post("/api/v1/plant3d/import/register",
                           json={"pairs": [{"source": [0, 0, 0], "target": [1, 1, 1]}]}).status_code == 400

    def test_envelope_check_endpoint(self):
        r = client.post("/api/v1/validation/envelope/check",
                        json={"values": {"rom_feed_tph": 1200.0}})
        assert r.status_code == 200 and not r.json()["inside_envelope"]
        assert client.post("/api/v1/validation/envelope/check", json={}).status_code == 400

    def test_validation_run_sections(self):
        for section in ("behaviour", "fail_safe", "system"):
            r = client.get("/api/v1/validation/run", params={"section": section})
            assert r.status_code == 200 and section in r.json()
        assert client.get("/api/v1/validation/run", params={"section": "zzz"}).status_code == 400

    def test_acceptance_report_renders(self):
        r = client.get("/api/v1/validation/report.md", params={"tests_pass": True})
        assert r.status_code == 200
        md = r.text
        for heading in ("Acceptance Test Report", "Summary of verdicts",
                        "Accuracy against plant data", "Behaviour — step tests",
                        "System criteria", "Acceptance procedure", "Signatures"):
            assert heading in md, heading
        assert len(md) > 6000

    def test_openapi_lists_the_new_groups(self):
        tags = {t for p in client.get("/openapi.json").json()["paths"].values()
                for op in p.values() for t in op.get("tags", [])}
        assert {"plant 3-D model", "hybrid model", "validation and acceptance"} <= tags
