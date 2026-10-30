"""First-principles twin: state representation, gravity unit models and flowsheet closure."""
from __future__ import annotations

import numpy as np
import pytest

from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.twin import comminution as cm
from app.twin import dewatering as dw
from app.twin import gravity as gv
from app.twin import separation as sp
from app.twin.circuit import solve
from app.twin.constraints import CONSTRAINTS, evaluate_all, penalty
from app.twin.psd import (G, N_BINS, N_CLASSES, SIZES_UM, blend, concentration_criterion,
                          liberation_curve, magnetic_susceptibility, make_feed, p_passing,
                          particle_sg, split, uplift_grade)


@pytest.fixture(scope="module")
def base():
    return solve(FlowsheetConfig(), OreConfig(), OperatingConfig(), EconomicsConfig())


@pytest.fixture(scope="module")
def rom():
    return make_feed(600, 30, 180_000, 54.0, 9.0, 5.0, 18_000.0)


def test_size_grid_spans_rom_to_slimes():
    ratios = SIZES_UM[:-1] / SIZES_UM[1:]
    assert np.allclose(ratios, 2 ** 0.5, rtol=1e-3)
    assert len(SIZES_UM) == N_CLASSES == 36
    assert SIZES_UM[0] == 250_000.0 and SIZES_UM[-1] < 2.0


def test_particle_density_spans_quartz_to_hematite():
    sg = particle_sg(0.22, 0.18)
    assert len(sg) == N_BINS
    assert sg[0] == pytest.approx(2.63, abs=0.05)         # free gangue
    assert sg[-1] == pytest.approx(4.92, abs=0.05)        # free iron mineral
    assert np.all(np.diff(sg) > 0)                        # density rises monotonically with grade


def test_concentration_criterion_says_gravity_is_viable():
    assert concentration_criterion(5.15, 2.65) > 2.5


def test_magnetic_susceptibility_tracks_iron_content():
    chi = magnetic_susceptibility(0.22)
    assert chi[0] == 0.0 and chi[-1] > 0.9
    assert np.all(np.diff(chi) > 0)


def test_feed_honours_the_head_assay(rom):
    a = rom.assay()
    assert a["fe_pct"] == pytest.approx(54.0, abs=0.3)
    assert a["al2o3_pct"] == pytest.approx(5.0, abs=1.0)
    assert rom.m.sum() == pytest.approx(1.0)


def test_liberation_is_capped_below_unity():
    lib = liberation_curve(18_000.0)
    assert lib.max() < 1.0
    assert np.all(np.diff(lib) >= -1e-9)                  # finer material is better liberated


def test_split_conserves_mass_and_iron(rom):
    rec = np.tile(np.linspace(0.1, 0.95, N_BINS), (N_CLASSES, 1))
    a, b = split(rom, rec, 0.4)
    assert a.solids_tph + b.solids_tph == pytest.approx(rom.solids_tph, rel=1e-9)
    assert a.fe_tph + b.fe_tph == pytest.approx(rom.fe_tph, rel=2e-3)


def test_uplift_grade_conserves_iron_units():
    row = np.zeros(N_BINS)
    row[3] = 0.4
    row[9] = 0.6
    iron_before = float((row * G).sum())
    out = uplift_grade(row, 1.08)
    assert float((out * G).sum()) == pytest.approx(iron_before, rel=1e-6)
    assert out.sum() < row.sum()                          # the particle lost its clay coating


def test_blend_is_mass_weighted():
    a = make_feed(100, 50, 40_000, 60, 6, 3, 18_000)
    b = make_feed(300, 90, 5_000, 45, 14, 7, 18_000)
    m = blend([a, b])
    assert m.solids_tph == pytest.approx(400)
    assert m.fe_tph == pytest.approx(a.fe_tph + b.fe_tph, rel=1e-6)


def test_density_partition_is_monotonic_and_centred():
    sg = particle_sg()
    part = gv.density_partition(sg, 3.9, np.full(N_CLASSES, 0.2))
    assert np.all(np.diff(part[0]) >= -1e-9)
    mid = float(np.interp(3.9, sg, part[0]))
    assert mid == pytest.approx(0.5, abs=0.02)


def test_scrubber_moves_clay_off_the_lumps_and_into_the_fines(rom):
    """The scrubber does not change the stream assay — it moves clay from the lumps to the fines.

    That is the whole mechanism: the coating leaves the ore surface and reports to the -10 mm
    stream, so the lump product gets richer while the plant feed does not change at all.
    """
    crushed, _ = cm.crusher(rom, 150, 55, 600, 11.0, "primary", 18_000)
    _, sized, _ = cm.screen(crushed, 40_000)
    out, info = gv.rotary_scrubber(sized.copy(water_tph=400), diameter_m=3.6, length_m=9.0,
                                   speed_pct_critical=30, water_m3_h=420,
                                   feed_solids_pct_target=62, detachable_clay_frac=0.55)
    assert info["clay_detachment_pct"] > 20
    assert out.assay()["fe_pct"] == pytest.approx(sized.assay()["fe_pct"], rel=1e-6)  # nothing left
    lumps_before, _, _ = cm.screen(sized, 10_000)
    lumps_after, fines_after, _ = cm.screen(out, 10_000)
    assert lumps_after.assay()["al2o3_pct"] < lumps_before.assay()["al2o3_pct"]
    assert lumps_after.assay()["fe_pct"] > lumps_before.assay()["fe_pct"]
    assert fines_after.assay()["al2o3_pct"] > lumps_after.assay()["al2o3_pct"]


def test_harder_scrubbing_removes_more_clay(rom):
    kw = dict(diameter_m=3.6, length_m=9.0, water_m3_h=420, feed_solids_pct_target=62)
    _, lo = gv.rotary_scrubber(rom, speed_pct_critical=20, **kw)
    _, hi = gv.rotary_scrubber(rom, speed_pct_critical=40, **kw)
    assert hi["clay_detachment_pct"] > lo["clay_detachment_pct"] + 5


def test_jig_upgrades_and_conserves(rom):
    sink, floats, info = gv.jig(rom.copy(water_tph=500), cut_sg_target=4.2, stroke_mm=22,
                                frequency_rpm=120, bed_depth_mm=220, hutch_water_m3_h=260,
                                area_m2=6.0, n_cells=4)
    assert sink.solids_tph + floats.solids_tph == pytest.approx(rom.solids_tph, rel=1e-9)
    assert sink.assay()["fe_pct"] > rom.assay()["fe_pct"]
    assert floats.assay()["fe_pct"] < rom.assay()["fe_pct"]
    assert 0 < info["yield_pct"] < 100


def test_jig_is_sharp_on_lumps_and_blunt_on_fines(rom):
    _, _, info = gv.jig(rom, cut_sg_target=4.0, stroke_mm=22, frequency_rpm=120, bed_depth_mm=220,
                        hutch_water_m3_h=260, area_m2=6.0, n_cells=4)
    assert info["ep_at_10mm"] < info["ep_at_1mm"]           # the whole reason fines go to spirals


def test_raising_the_jig_cut_raises_grade_and_lowers_yield(rom):
    kw = dict(stroke_mm=22, frequency_rpm=120, bed_depth_mm=220, hutch_water_m3_h=260,
              area_m2=6.0, n_cells=4)
    lo_s, _, lo = gv.jig(rom, cut_sg_target=3.5, **kw)
    hi_s, _, hi = gv.jig(rom, cut_sg_target=4.6, **kw)
    assert hi["conc_fe_pct"] > lo["conc_fe_pct"]
    assert hi["yield_pct"] < lo["yield_pct"]


def test_classifier_overflow_is_leaner_than_its_feed():
    feed = make_feed(300, 400, 6_000, 52, 11, 6, 18_000)
    sand, slime, info = gv.spiral_classifier(feed, tank_width_m=3.0, tank_length_m=11.0, slope_deg=18,
                                             screw_rpm=4.5, weir_height_m=0.30,
                                             dilution_water_m3_h=180, n_units=4)
    assert sand.solids_tph + slime.solids_tph == pytest.approx(feed.solids_tph, rel=1e-9)
    assert slime.assay()["fe_pct"] < feed.assay()["fe_pct"] < sand.assay()["fe_pct"]
    assert info["equal_settling_ratio"] > 1.2              # hematite settles like a coarser quartz grain
    assert slime.p80_um < sand.p80_um


def test_spiral_makes_three_products_and_conserves():
    feed = make_feed(180, 420, 900, 48, 14, 7, 18_000)
    c, m, t, info = gv.spiral_concentrator(feed, n_starts=120, turns=5.0, diameter_m=0.9,
                                           feed_solids_pct_target=28, wash_water_m3_h=120,
                                           conc_splitter=0.26, middling_splitter=0.52)
    assert c.solids_tph + m.solids_tph + t.solids_tph == pytest.approx(feed.solids_tph, rel=1e-9)
    assert c.assay()["fe_pct"] > feed.assay()["fe_pct"] > t.assay()["fe_pct"]
    assert info["cut_sg_conc"] > info["cut_sg_middling"]


def test_moving_the_spiral_splitter_trades_grade_for_recovery():
    feed = make_feed(180, 420, 900, 48, 14, 7, 18_000)
    kw = dict(n_starts=120, turns=5.0, diameter_m=0.9, feed_solids_pct_target=28,
              wash_water_m3_h=120, middling_splitter=0.52)
    _, _, _, tight = gv.spiral_concentrator(feed, conc_splitter=0.14, **kw)
    _, _, _, wide = gv.spiral_concentrator(feed, conc_splitter=0.45, **kw)
    assert tight["conc_fe_pct"] > wide["conc_fe_pct"]
    assert tight["fe_recovery_pct"] < wide["fe_recovery_pct"]


def test_table_is_sharper_than_the_spiral():
    feed = make_feed(30, 95, 400, 47, 15, 7, 18_000)
    _, _, _, tbl = gv.shaking_table(feed, n_decks=28, deck_area_m2=7.6, slope_deg=3.2, stroke_mm=16,
                                    frequency_rpm=265, wash_water_m3_h=65, conc_cut=0.30)
    _, _, _, spi = gv.spiral_concentrator(feed, n_starts=120, turns=5.0, diameter_m=0.9,
                                          feed_solids_pct_target=28, wash_water_m3_h=120,
                                          conc_splitter=0.26, middling_splitter=0.52)
    assert tbl["ep_at_200um"] < spi["ep_at_500um"]


def test_whims_recovers_fine_hematite_and_rejects_alumina():
    feed = make_feed(60, 200, 300, 34, 20, 12, 18_000)
    conc, tail, info = sp.whims(feed, field_tesla=1.15, matrix="expanded_metal", gap_mm=4.0,
                                ring_speed_rpm=4.0, wash_water_m3_h=95, feed_solids_pct_target=30,
                                n_units=3)
    assert conc.solids_tph + tail.solids_tph == pytest.approx(feed.solids_tph, rel=1e-9)
    assert conc.assay()["fe_pct"] > feed.assay()["fe_pct"] + 10
    assert conc.assay()["al2o3_pct"] < feed.assay()["al2o3_pct"]
    assert 0 < info["fe_recovery_pct"] <= 100


def test_higher_field_recovers_more_iron():
    feed = make_feed(60, 200, 300, 34, 20, 12, 18_000)
    kw = dict(matrix="expanded_metal", gap_mm=4.0, ring_speed_rpm=4.0, wash_water_m3_h=95,
              feed_solids_pct_target=30, n_units=3)
    _, _, lo = sp.whims(feed, field_tesla=0.6, **kw)
    _, _, hi = sp.whims(feed, field_tesla=1.4, **kw)
    assert hi["fe_recovery_pct"] > lo["fe_recovery_pct"] + 5


def test_crusher_and_screen_behave():
    feed = make_feed(600, 0, 180_000, 54, 9, 5, 18_000)
    prod, info = cm.crusher(feed, 150, 55, 600, 11.0, "primary", 18_000)
    assert prod.p80_um < feed.p80_um
    over, under, si = cm.screen(prod, 40_000)
    assert over.solids_tph + under.solids_tph == pytest.approx(prod.solids_tph, rel=1e-9)
    assert over.p80_um > under.p80_um
    assert 0 < si["screening_efficiency_pct"] <= 100


def test_thickener_reaches_target(rom):
    uf, of, info = dw.thickener(rom.copy(solids_tph=130, water_tph=900), diameter_m=45, depth_m=4,
                                target_underflow_solids_pct=55, flocculant_g_t=32,
                                rake_torque_rating_knm=900)
    assert uf.solids_tph + of.solids_tph == pytest.approx(130, rel=1e-6)
    assert info["overflow_tss_mg_l"] > 0


def test_flowsheet_closes_mass_and_iron(base):
    s = base["streams"]
    out = (s["S08_lump_ore"].solids_tph + s["S19_ore_fines"].solids_tph
           + s["S27_pellet_fines"].solids_tph + s["S28_tailings"].solids_tph)
    assert out == pytest.approx(s["S01_rom"].solids_tph, rel=2e-3)
    fe_out = (s["S08_lump_ore"].fe_tph + s["S19_ore_fines"].fe_tph
              + s["S27_pellet_fines"].fe_tph + s["S28_tailings"].fe_tph)
    assert fe_out == pytest.approx(s["S01_rom"].fe_tph, rel=2e-3)
    assert base["balance"]["closure_pct"] == pytest.approx(100.0, abs=0.5)


def test_baseline_meets_product_specifications(base):
    k = base["kpis"]
    assert 60.0 <= k["lump_fe_pct"] <= 67.0
    assert k["lump_al2o3_pct"] <= 2.6
    assert 62.0 <= k["fines_fe_pct"] <= 68.0
    assert 85.0 <= k["fe_recovery_pct"] <= 97.0
    assert 70.0 <= k["mass_yield_pct"] <= 90.0
    assert 1.2 <= k["energy_kwh_t"] <= 4.0                 # no grinding in this circuit


def test_three_products_leave_the_plant(base):
    k = base["kpis"]
    assert k["lump_tph"] > 0 and k["fines_tph"] > 0 and k["pellet_fines_tph"] > 0
    assert k["saleable_tph"] == pytest.approx(k["lump_tph"] + k["fines_tph"] + k["pellet_fines_tph"],
                                              rel=1e-6)


def test_constraints_evaluate_and_penalise(base):
    rows = evaluate_all(base)
    assert len(rows) == len(CONSTRAINTS) == 33
    assert all("status" in r for r in rows)
    assert penalty(base) == pytest.approx(0.0, abs=1e-6)   # the shipped baseline is feasible


def test_clay_rich_ore_lifts_product_alumina():
    clean = solve(FlowsheetConfig(), OreConfig(al2o3_head_pct=3.0), OperatingConfig(), EconomicsConfig())
    dirty = solve(FlowsheetConfig(), OreConfig(al2o3_head_pct=8.0), OperatingConfig(), EconomicsConfig())
    assert dirty["kpis"]["lump_al2o3_pct"] > clean["kpis"]["lump_al2o3_pct"] + 0.5


def test_washability_curve_is_ordered(base):
    d = base["streams"]["S01_rom"].sg_distribution()
    assert sum(d["mass_pct"]) == pytest.approx(100.0, abs=1.0)
    assert d["fe_pct"][-1] > d["fe_pct"][0]                # denser fractions are richer


def test_p_passing_interpolation(rom):
    assert p_passing(rom.size_frac, 80.0) > p_passing(rom.size_frac, 50.0)
