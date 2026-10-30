"""Flowsheet solver for the gravity + WHIMS ore-beneficiation plant.

The circuit, as drawn on the plant flowsheet:

    ROM -> jaw crusher -> sizing screen (closed with the secondary cone)
        -> rotary scrubber (clay removal) -> scrubber trommel
            +10 mm lumps -> LUMP JIG -> sinks = LUMP ORE
                                     -> floats -> tertiary cone -> back to the fines
            -10 mm fines -> SCREW CLASSIFIER
                sand  -> sizing screen -> +2 mm -> FINES JIG -> sinks = ore fines
                                                             -> floats -> tertiary cone
                                       -> -2 mm -> spiral-feed cyclone
                                             U/F -> SPIRALS -> conc = ore fines
                                                            -> middling -> SHAKING TABLES -> conc = ore fines
                                                            -> tailing
                                             O/F -> to the slimes
                slime -> desliming cyclone
                    U/F -> WHIMS -> magnetics = PELLET FINES
                    O/F -> ultrafine slime to tailings
    tailings -> thickener -> TSF ; overflow water -> recovery -> recycle

Three products leave the plant: **lump ore** for direct blast-furnace feed, **ore fines** for the
sinter plant, and **pellet fines** from the WHIMS. Because they carry different prices and
different specifications, the optimiser has a genuine three-way trade-off to make rather than a
single grade-recovery curve to climb.

Three recycles close the circuit — the secondary crusher around the sizing screen, the tertiary
crusher on both jig floats, and the table middling back to the spirals — and are solved by
direct substitution.
"""
from __future__ import annotations

import time

import numpy as np

from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.twin import comminution as cm
from app.twin import dewatering as dw
from app.twin import gravity as gv
from app.twin import separation as sp
from app.twin.psd import N_BINS, N_CLASSES, Stream, blend, make_feed


def _empty(name: str = "") -> Stream:
    return Stream(0.0, np.zeros((N_CLASSES, N_BINS)), 0.0, name=name)


class _Accel:
    """Wegstein-style acceleration for a recycle stream.

    Direct substitution converges at the rate of the circulating load, so a 50 % recycle needs
    dozens of passes for a closed balance. Extrapolating each recycle to its fixed point from the
    observed contraction ratio gets the same answer in a handful of passes, which is what lets the
    whole plant solve inside 100 ms — fast enough for the optimiser and the controller to call it
    hundreds of times.
    """

    def __init__(self, damping: float = 0.98) -> None:
        self.hist: list[float] = []
        self.damping = damping

    def step(self, stream: Stream, enabled: bool = True) -> Stream:
        x = float(stream.solids_tph)
        self.hist.append(x)
        if not enabled or len(self.hist) < 3:
            return stream
        x2, x1, x0 = self.hist[-1], self.hist[-2], self.hist[-3]
        denom = x1 - x0
        if abs(denom) < 1e-9 or x2 <= 1e-9:
            return stream
        r = (x2 - x1) / denom
        if not (0.0 < r < 0.995):
            return stream
        target = x2 + self.damping * r * (x2 - x1) / (1.0 - r)
        scale = float(np.clip(target / max(x2, 1e-9), 0.4, 6.0))
        self.hist[-1] = x2 * scale
        return stream.copy(solids_tph=x2 * scale, water_tph=stream.water_tph * scale)


def _dilute(stream: Stream, target_solids_pct: float) -> tuple[Stream, float]:
    """Add water to hit a target pulp density; returns the diluted stream and the water added."""
    target = float(np.clip(target_solids_pct, 5.0, 90.0))
    need = stream.solids_tph * (100.0 - target) / max(target, 1e-6)
    add = max(need - stream.water_tph, 0.0)
    return stream.copy(water_tph=stream.water_tph + add), add


def solve(flowsheet: FlowsheetConfig, ore: OreConfig, operating: OperatingConfig,
          economics: EconomicsConfig, iterations: int = 24) -> dict:
    """Solve the whole plant at steady state. Returns kpis, unit states, streams and diagnostics."""
    t0 = time.perf_counter()
    fs, op, ec = flowsheet, operating, economics
    axb = fs.crushing.axb_override or ore.axb
    warnings: list[str] = []

    # ---- feed ---------------------------------------------------------------------------------
    rom = make_feed(op.rom_feed_tph, op.rom_feed_tph * ore.moisture_pct / 100.0,
                    ore.f80_mm * 1000.0, ore.fe_head_pct, ore.sio2_head_pct, ore.al2o3_head_pct,
                    ore.liberation_d50_um, ore.goethite_share,
                    rr_n=float(np.clip(0.92 - 0.55 * ore.lump_friability, 0.55, 1.0)), name="S01_rom")
    detachable_clay = float(np.clip(ore.clay_share, 0.0, 0.85))

    # ---- A100 crushing and sizing --------------------------------------------------------------
    prim, prim_info = cm.crusher(rom, op.primary_css_mm, axb, fs.crushing.primary_installed_kw,
                                 ore.bond_wi_kwh_t, "primary", ore.liberation_d50_um)
    sec_recycle = _empty("secondary_recycle")
    screen_info = sec_info = {}
    sized = prim
    acc_sec = _Accel()
    #: accelerate early, then let plain substitution settle so the final pass is self-consistent
    settle_from = max(int(0.70 * iterations), 4)
    for it in range(iterations):
        screen_feed = blend([prim, sec_recycle], "screen_feed")
        over, under, screen_info = cm.screen(screen_feed, fs.crushing.sizing_screen_aperture_mm * 1000.0,
                                             sharpness=2.8, water_to_oversize=0.2)
        sec_recycle, sec_info = cm.crusher(over, op.secondary_css_mm, axb,
                                           fs.crushing.secondary_installed_kw, ore.bond_wi_kwh_t,
                                           "secondary", ore.liberation_d50_um)
        sec_recycle = acc_sec.step(sec_recycle, it < settle_from)
        sized = under
    screen_info["screen_area_m2"] = fs.crushing.sizing_screen_area_m2
    screen_info["screen_loading_tph_m2"] = round(
        (sized.solids_tph + sec_recycle.solids_tph) / max(fs.crushing.sizing_screen_area_m2, 1e-6), 2)

    # ---- A200 scrubbing and the lump / fines split ----------------------------------------------
    scrub_feed, scrub_dilution = _dilute(sized, op.scrubber_solids_pct)
    scrubbed, scrub_info = gv.rotary_scrubber(
        scrub_feed, diameter_m=fs.scrubber.diameter_m, length_m=fs.scrubber.length_m,
        speed_pct_critical=op.scrubber_speed_pct_critical, water_m3_h=op.scrubber_water_m3_h,
        feed_solids_pct_target=op.scrubber_solids_pct, lifter_count=fs.scrubber.lifter_count,
        installed_kw=fs.scrubber.installed_kw, detachable_clay_frac=detachable_clay,
        friability=ore.lump_friability)
    lumps, fines_raw, trommel_info = cm.screen(scrubbed, op.trommel_aperture_mm * 1000.0,
                                               sharpness=3.1, water_to_oversize=0.18)
    lumps = lumps.copy(name="S06_lumps")
    trommel_info["aperture_mm"] = round(op.trommel_aperture_mm, 2)
    trommel_info["lump_fraction_pct"] = round(100 * lumps.solids_tph / max(scrubbed.solids_tph, 1e-6), 2)

    # ---- fixed-point over the two recycles that re-enter the fines circuit ----------------------
    tertiary_product = _empty("tertiary_product")
    tertiary_coarse = _empty("tertiary_coarse")
    table_middling_recycle = _empty("table_middling_recycle")
    (lump_conc, lump_jig_info, class_sand, class_slime, class_info, fines_jig_conc, fines_jig_info,
     sp_cyc_info, spiral_conc, spiral_mid, spiral_tail, spiral_info, table_conc, table_tail,
     table_info, fines_screen_info, tertiary_info) = (None,) * 17
    spiral_feed = _empty()
    cyc_of = _empty()
    tertiary_fine = _empty("tertiary_fine")
    tert_screen_info: dict = {}
    acc_tert, acc_mid = _Accel(), _Accel()
    for it in range(iterations):
        # A300 lump jigging — the recrushed jig floats come back here as circulating load
        lump_jig_feed, _ = _dilute(blend([lumps, tertiary_coarse], "lump_jig_feed"), 55.0)
        lump_conc, lump_floats, lump_jig_info = gv.jig(
            lump_jig_feed, cut_sg_target=op.lump_jig_cut_sg, stroke_mm=op.lump_jig_stroke_mm,
            frequency_rpm=op.lump_jig_frequency_rpm, bed_depth_mm=op.lump_jig_bed_depth_mm,
            hutch_water_m3_h=op.lump_jig_hutch_water_m3_h, area_m2=fs.lump_jig.cell_area_m2,
            n_cells=fs.lump_jig.n_cells, installed_kw=fs.lump_jig.installed_kw, machine="lump")

        # A400 classification of the fines, including the fine half of the recrushed floats
        class_feed = blend([fines_raw, tertiary_fine], "S07_fines")
        class_feed, class_dilution = _dilute(class_feed, 45.0)
        class_sand, class_slime, class_info = gv.spiral_classifier(
            class_feed, tank_width_m=fs.classifier.tank_width_m, tank_length_m=fs.classifier.tank_length_m,
            slope_deg=fs.classifier.slope_deg, screw_rpm=op.classifier_screw_rpm,
            weir_height_m=op.classifier_weir_height_m,
            dilution_water_m3_h=op.classifier_dilution_water_m3_h, n_units=fs.classifier.n_units,
            installed_kw=fs.classifier.installed_kw)

        # A500 fines jigging on the coarse sand
        coarse_sand, fine_sand, fines_screen_info = cm.screen(
            class_sand, op.fines_screen_aperture_mm * 1000.0, sharpness=2.5, water_to_oversize=0.3)
        fines_screen_info["aperture_mm"] = round(op.fines_screen_aperture_mm, 3)
        fj_feed, _ = _dilute(coarse_sand, 50.0)
        fines_jig_conc, fines_jig_floats, fines_jig_info = gv.jig(
            fj_feed, cut_sg_target=op.fines_jig_cut_sg, stroke_mm=max(op.lump_jig_stroke_mm * 0.6, 8.0),
            frequency_rpm=min(op.lump_jig_frequency_rpm * 1.5, 280.0), bed_depth_mm=140.0,
            hutch_water_m3_h=op.fines_jig_hutch_water_m3_h, area_m2=fs.fines_jig.cell_area_m2,
            n_cells=fs.fines_jig.n_cells, installed_kw=fs.fines_jig.installed_kw, machine="fines")

        # tertiary crushing of both jig floats, returned to the fines circuit
        tert_feed = blend([lump_floats, fines_jig_floats], "tertiary_feed")
        tertiary_product, tertiary_info = cm.crusher(
            tert_feed, op.tertiary_css_mm, axb, fs.crushing.tertiary_installed_kw, ore.bond_wi_kwh_t,
            "tertiary", ore.liberation_d50_um)
        tertiary_coarse, tertiary_fine, tert_screen_info = cm.screen(
            tertiary_product, op.trommel_aperture_mm * 1000.0, sharpness=3.0, water_to_oversize=0.2)
        tertiary_info["recrush_screen_oversize_tph"] = round(tertiary_coarse.solids_tph, 2)
        tertiary_info["recrush_screen_undersize_tph"] = round(tertiary_fine.solids_tph, 2)
        tertiary_info["circulating_load_pct"] = round(
            100 * tertiary_coarse.solids_tph / max(lumps.solids_tph, 1e-6), 1)
        tertiary_coarse = acc_tert.step(tertiary_coarse, it < settle_from)

        # A600 spiral-feed cyclone and the spirals
        cyc_feed = blend([fine_sand, table_middling_recycle], "spiral_cyclone_feed")
        cyc_feed, _ = _dilute(cyc_feed, 38.0)
        cyc_uf, cyc_of, sp_cyc_info = cm.hydrocyclone(
            cyc_feed, n_open=op.spiral_cyclones_open, diameter_mm=fs.spiral_cyclone.diameter_mm,
            vortex_mm=fs.spiral_cyclone.vortex_mm, apex_mm=fs.spiral_cyclone.apex_mm,
            pressure_kpa=op.spiral_cyclone_pressure_kpa)
        spiral_feed, _ = _dilute(cyc_uf, op.spiral_feed_solids_pct)
        spiral_conc, spiral_mid, spiral_tail, spiral_info = gv.spiral_concentrator(
            spiral_feed, n_starts=fs.spirals.n_starts, turns=fs.spirals.turns,
            diameter_m=fs.spirals.diameter_m, feed_solids_pct_target=op.spiral_feed_solids_pct,
            wash_water_m3_h=op.spiral_wash_water_m3_h, conc_splitter=op.spiral_conc_splitter,
            middling_splitter=op.spiral_middling_splitter,
            feed_tph_per_start=fs.spirals.capacity_tph_per_start)

        # A700 shaking tables on the spiral middling
        table_feed, _ = _dilute(spiral_mid, 24.0)
        table_conc, table_mid, table_tail, table_info = gv.shaking_table(
            table_feed, n_decks=fs.tables.n_decks, deck_area_m2=fs.tables.deck_area_m2,
            slope_deg=op.table_slope_deg, stroke_mm=fs.tables.stroke_mm,
            frequency_rpm=fs.tables.frequency_rpm, wash_water_m3_h=op.table_wash_water_m3_h,
            conc_cut=op.table_conc_cut, feed_tph_per_deck=fs.tables.capacity_tph_per_deck,
            installed_kw=fs.tables.installed_kw_per_deck)
        table_middling_recycle = acc_mid.step(table_mid.copy(name="table_middling_recycle"), it < settle_from)

    # ---- A800 desliming and WHIMS ----------------------------------------------------------------
    slimes = blend([class_slime, cyc_of], "S12_slimes")
    slimes, _ = _dilute(slimes, 22.0)
    deslime_uf, deslime_of, deslime_info = cm.hydrocyclone(
        slimes, n_open=op.deslime_cyclones_open, diameter_mm=fs.deslime_cyclone.diameter_mm,
        vortex_mm=fs.deslime_cyclone.vortex_mm, apex_mm=fs.deslime_cyclone.apex_mm,
        pressure_kpa=op.deslime_cyclone_pressure_kpa)
    whims_feed, _ = _dilute(deslime_uf, op.whims_feed_solids_pct)
    pellet_fines, whims_tail, whims_info = sp.whims(
        whims_feed, field_tesla=op.whims_field_tesla, matrix=fs.whims.matrix, gap_mm=fs.whims.gap_mm,
        ring_speed_rpm=fs.whims.ring_speed_rpm, wash_water_m3_h=op.whims_wash_water_m3_h,
        feed_solids_pct_target=op.whims_feed_solids_pct, n_units=fs.whims.n_units,
        capacity_tph_per_unit=fs.whims.capacity_tph_per_unit, installed_kw=fs.whims.installed_kw)

    # ---- products ---------------------------------------------------------------------------------
    lump_product = lump_conc.copy(name="S08_lump_ore")
    ore_fines = blend([fines_jig_conc, spiral_conc, table_conc], "S19_ore_fines")
    pellet_product = pellet_fines.copy(name="S27_pellet_fines")
    tailings = blend([spiral_tail, table_tail, deslime_of, whims_tail], "S28_tailings")

    # ---- A900 tailings thickening and water ---------------------------------------------------
    tails_uf, tails_of, tails_info = dw.thickener(
        tailings, diameter_m=fs.tails_thickener.diameter_m, depth_m=fs.tails_thickener.depth_m,
        target_underflow_solids_pct=op.tails_underflow_target_pct,
        flocculant_g_t=op.tails_flocculant_g_t,
        rake_torque_rating_knm=fs.tails_thickener.rake_torque_rating_knm, name="tails_thickener")

    # ---- water balance around the plant boundary -----------------------------------------------
    # Process water circulates: what the units add comes out of the process-water tank. Water
    # only *leaves* the boundary as product moisture, as the water locked into the thickener
    # underflow sent to the tailings pond, and as evaporation. Fresh make-up therefore equals
    # those losses less what the pond gives back — which is the number a water-stressed site
    # is actually judged on, not the total the pumps move.
    water_added = (scrub_dilution + op.scrubber_water_m3_h + op.lump_jig_hutch_water_m3_h
                   + op.classifier_dilution_water_m3_h + op.fines_jig_hutch_water_m3_h
                   + op.spiral_wash_water_m3_h + op.table_wash_water_m3_h + op.whims_wash_water_m3_h)
    drained = {"lump": 0.04, "fines": 0.10, "pellet": 0.12}
    water_out_lump = lump_product.solids_tph * drained["lump"] / (1 - drained["lump"])
    water_out_fines = ore_fines.solids_tph * drained["fines"] / (1 - drained["fines"])
    water_out_pellet = pellet_product.solids_tph * drained["pellet"] / (1 - drained["pellet"])
    water_out_products = water_out_lump + water_out_fines + water_out_pellet
    water_to_tsf = tails_uf.water_tph
    evaporation = 0.012 * (water_added + water_to_tsf)
    reclaim = water_to_tsf * float(np.clip(op.reclaim_water_fraction, 0.0, 0.95))
    losses = water_out_products + water_to_tsf + evaporation
    fresh = max(losses - reclaim - rom.water_tph, 0.0)
    recycled = tails_of.water_tph + reclaim
    demand = water_added

    # ---- power and cost -------------------------------------------------------------------------
    power = {
        "primary_crusher_kw": prim_info["power_kw"],
        "secondary_crusher_kw": sec_info["power_kw"],
        "tertiary_crusher_kw": tertiary_info["power_kw"],
        "screens_kw": round(0.9 * fs.crushing.sizing_screen_area_m2 + 14.0, 1),
        "scrubber_kw": scrub_info["power_kw"],
        "lump_jig_kw": lump_jig_info["power_kw"],
        "fines_jig_kw": fines_jig_info["power_kw"],
        "classifier_kw": class_info["power_kw"],
        "tables_kw": table_info["power_kw"],
        "whims_kw": whims_info["power_kw"],
        "pumps_kw": round(0.42 * (spiral_feed.slurry_m3_h + slimes.slurry_m3_h) ** 0.82 + 60.0, 1),
        "thickener_kw": round(tails_info.get("rake_power_kw", 18.0), 1),
    }
    total_kw = float(sum(power.values()))
    energy_kwh_t = total_kw / max(rom.solids_tph, 1e-6)

    a_l, a_f, a_p, a_t = (lump_product.assay(), ore_fines.assay(), pellet_product.assay(),
                          tailings.assay())

    def _price(assay: dict, premium: float) -> float:
        base = ec.iron_ore_index_usd_dmt + premium
        fe_adj = (assay["fe_pct"] - 62.0) * ec.fe_adjustment_usd_per_pct
        sio2_pen = max(assay["sio2_pct"] - 4.0, 0.0) * ec.silica_penalty_usd_per_pct
        al_pen = max(assay["al2o3_pct"] - ec.alumina_free_allowance_pct, 0.0) * ec.alumina_penalty_usd_per_pct
        loi_pen = max(assay["loi_pct"] - 3.0, 0.0) * ec.loi_penalty_usd_per_pct
        return max(base + fe_adj - sio2_pen - al_pen - loi_pen - ec.freight_usd_dmt, 0.0)

    price_l, price_f, price_p = (_price(a_l, ec.lump_premium_usd_dmt), _price(a_f, 0.0),
                                 _price(a_p, ec.pellet_feed_premium_usd_dmt))
    revenue = (lump_product.solids_tph * price_l + ore_fines.solids_tph * price_f
               + pellet_product.solids_tph * price_p)
    costs = {
        "power_usd_h": round(total_kw * ec.power_usd_kwh, 1),
        "water_usd_h": round(fresh * ec.water_usd_m3, 1),
        "flocculant_usd_h": round(tailings.solids_tph * op.tails_flocculant_g_t / 1000.0 * ec.flocculant_usd_kg, 1),
        "wear_parts_usd_h": round(rom.solids_tph * ec.wear_parts_usd_t, 1),
        "mining_usd_h": round(rom.solids_tph * ec.mining_cost_usd_t, 1),
        "fixed_usd_h": round(ec.fixed_cost_usd_h, 1),
    }
    total_cost = float(sum(costs.values()))
    saleable = lump_product.solids_tph + ore_fines.solids_tph + pellet_product.solids_tph

    kpis = {
        "throughput_tph": round(rom.solids_tph, 2),
        "lump_tph": round(lump_product.solids_tph, 2),
        "fines_tph": round(ore_fines.solids_tph, 2),
        "pellet_fines_tph": round(pellet_product.solids_tph, 2),
        "saleable_tph": round(saleable, 2),
        "tailings_tph": round(tailings.solids_tph, 2),
        "mass_yield_pct": round(100 * saleable / max(rom.solids_tph, 1e-6), 2),
        "lump_yield_pct": round(100 * lump_product.solids_tph / max(rom.solids_tph, 1e-6), 2),
        "fines_yield_pct": round(100 * ore_fines.solids_tph / max(rom.solids_tph, 1e-6), 2),
        "pellet_yield_pct": round(100 * pellet_product.solids_tph / max(rom.solids_tph, 1e-6), 2),
        "lump_fe_pct": round(a_l["fe_pct"], 3),
        "lump_sio2_pct": round(a_l["sio2_pct"], 3),
        "lump_al2o3_pct": round(a_l["al2o3_pct"], 3),
        "lump_loi_pct": round(a_l["loi_pct"], 3),
        "fines_fe_pct": round(a_f["fe_pct"], 3),
        "fines_sio2_pct": round(a_f["sio2_pct"], 3),
        "fines_al2o3_pct": round(a_f["al2o3_pct"], 3),
        "pellet_fines_fe_pct": round(a_p["fe_pct"], 3),
        "pellet_fines_sio2_pct": round(a_p["sio2_pct"], 3),
        "pellet_fines_al2o3_pct": round(a_p["al2o3_pct"], 3),
        "pellet_fines_blaine_cm2_g": round(pellet_product.blaine, 0),
        "product_fe_pct": round((lump_product.fe_tph + ore_fines.fe_tph + pellet_product.fe_tph)
                                / max(saleable, 1e-6) * 100.0 / 100.0 * 100.0, 3),
        "tailings_fe_pct": round(a_t["fe_pct"], 3),
        "fe_loss_tph": round(tailings.fe_tph, 3),
        "fe_recovery_pct": round(100 * (lump_product.fe_tph + ore_fines.fe_tph + pellet_product.fe_tph)
                                 / max(rom.fe_tph, 1e-9), 2),
        "lump_fe_recovery_pct": round(100 * lump_product.fe_tph / max(rom.fe_tph, 1e-9), 2),
        "fines_fe_recovery_pct": round(100 * ore_fines.fe_tph / max(rom.fe_tph, 1e-9), 2),
        "pellet_fe_recovery_pct": round(100 * pellet_product.fe_tph / max(rom.fe_tph, 1e-9), 2),
        "slimes_to_tailings_pct": round(100 * deslime_of.solids_tph / max(rom.solids_tph, 1e-6), 2),
        "lump_p80_mm": round(lump_product.p80_um / 1000.0, 2),
        "fines_p80_um": round(ore_fines.p80_um, 1),
        "pellet_fines_p80_um": round(pellet_product.p80_um, 2),
        "scrubber_clay_removal_pct": round(scrub_info["clay_detachment_pct"], 2),
        "classifier_d50_um": round(class_info["d50_quartz_um"], 1),
        "spiral_load_fraction": round(spiral_info["load_fraction"], 3),
        "table_load_fraction": round(table_info["load_fraction"], 3),
        "whims_load_fraction": round(whims_info["loading_fraction"], 3),
        "energy_kwh_t": round(energy_kwh_t, 3),
        "energy_per_product_kwh_t": round(total_kw / max(saleable, 1e-6), 3),
        "total_power_mw": round(total_kw / 1000.0, 3),
        "fresh_water_m3_t": round(fresh / max(rom.solids_tph, 1e-6), 4),
        "total_water_m3_t": round(water_added / max(rom.solids_tph, 1e-6), 4),
        "fresh_water_m3_h": round(fresh, 1),
        "water_recycle_pct": round(100 * recycled / max(recycled + fresh, 1e-6), 2),
        "tails_uf_solids_pct": round(tails_info["underflow_solids_pct"], 2),
        "tails_overflow_tss_mg_l": round(tails_info["overflow_tss_mg_l"], 1),
        "realised_lump_usd_dmt": round(price_l, 2),
        "realised_fines_usd_dmt": round(price_f, 2),
        "realised_pellet_usd_dmt": round(price_p, 2),
        "revenue_usd_h": round(revenue, 1),
        "cost_usd_h": round(total_cost, 1),
        "cost_usd_t": round(total_cost / max(rom.solids_tph, 1e-6), 3),
        "cost_usd_product_t": round(total_cost / max(saleable, 1e-6), 3),
        "margin_usd_h": round(revenue - total_cost, 1),
        "margin_usd_product_t": round((revenue - total_cost) / max(saleable, 1e-6), 3),
        "carbon_kgco2_t": round(energy_kwh_t * 0.71, 3),
    }
    kpis["product_fe_pct"] = round(
        100 * (lump_product.fe_tph + ore_fines.fe_tph + pellet_product.fe_tph) / max(saleable, 1e-6), 3)

    balance_in = rom.solids_tph
    balance_out = saleable + tailings.solids_tph
    closure = 100.0 * balance_out / max(balance_in, 1e-9)
    if abs(closure - 100.0) > 0.5:
        warnings.append(f"solids balance closure {closure:.2f} % — check the recycle convergence")
    if spiral_info["load_fraction"] > 1.05:
        warnings.append("spiral bank above nameplate capacity — sharpness is degrading")
    if table_info["load_fraction"] > 1.05:
        warnings.append("shaking tables above nameplate capacity — middling is being lost")
    if whims_info["loading_fraction"] > 1.05:
        warnings.append("WHIMS above nameplate capacity — magnetics are being washed through")
    if kpis["lump_al2o3_pct"] > ec.alumina_free_allowance_pct + 0.8:
        warnings.append("lump alumina above the penalty allowance — check scrubber duty and trommel washing")

    units = {
        "primary_crusher": prim_info, "sizing_screen": screen_info, "secondary_crusher": sec_info,
        "scrubber": scrub_info, "scrubber_trommel": trommel_info, "lump_jig": lump_jig_info,
        "tertiary_crusher": tertiary_info, "spiral_classifier": class_info,
        "fines_screen": fines_screen_info, "fines_jig": fines_jig_info,
        "recrush_screen": tert_screen_info,
        "spiral_cyclone": sp_cyc_info, "spirals": spiral_info, "shaking_tables": table_info,
        "deslime_cyclone": deslime_info, "whims": whims_info, "tails_thickener": tails_info,
        "water_recovery": {"water_added_m3_h": round(water_added, 1),
                           "thickener_overflow_m3_h": round(tails_of.water_tph, 1),
                           "pond_reclaim_m3_h": round(reclaim, 1),
                           "recycled_m3_h": round(recycled, 1),
                           "product_moisture_m3_h": round(water_out_products, 1),
                           "water_to_tsf_m3_h": round(water_to_tsf, 1),
                           "evaporation_m3_h": round(evaporation, 1),
                           "losses_m3_h": round(losses, 1), "demand_m3_h": round(demand, 1),
                           "fresh_make_up_m3_h": round(fresh, 1),
                           "reclaim_fraction": round(op.reclaim_water_fraction, 3),
                           "recycle_pct": round(100 * recycled / max(recycled + fresh, 1e-6), 2),
                           "allocation_m3_h": fs.fresh_water_allocation_m3_h},
    }
    streams = {
        "S01_rom": rom, "S02_primary_product": prim, "S03_screen_oversize": sec_recycle,
        "S04_screen_undersize": sized, "S05_scrubbed": scrubbed, "S06_lumps": lumps,
        "S07_scrubber_fines": fines_raw, "S08_lump_ore": lump_product,
        "S09_jig_floats": tert_feed, "S09a_lump_jig_floats": lump_floats,
        "S09b_fines_jig_floats": fines_jig_floats, "S10_tertiary_product": tertiary_product,
        "S10b_recrush_oversize": tertiary_coarse, "S10c_recrush_fine": tertiary_fine,
        "S11_classifier_sand": class_sand, "S12_classifier_overflow": class_slime,
        "S13_fines_jig_conc": fines_jig_conc, "S14_spiral_cyclone_uf": spiral_feed,
        "S15_spiral_cyclone_of": cyc_of, "S16_spiral_conc": spiral_conc,
        "S17_spiral_middling": spiral_mid, "S18_spiral_tailing": spiral_tail,
        "S19_ore_fines": ore_fines, "S20_table_conc": table_conc, "S21_table_tailing": table_tail,
        "S25_table_middling": table_middling_recycle,
        "S22_deslime_uf": deslime_uf, "S23_deslime_of": deslime_of,
        "S24_whims_tail": whims_tail, "S27_pellet_fines": pellet_product,
        "S28_tailings": tailings, "S29_tails_underflow": tails_uf, "S30_tails_overflow": tails_of,
    }
    return {
        "kpis": kpis, "units": units, "streams": streams, "power": power, "costs": costs,
        "water": units["water_recovery"],
        "economics": {"revenue_usd_h": round(revenue, 1), "cost_usd_h": round(total_cost, 1),
                      "margin_usd_h": round(revenue - total_cost, 1),
                      "lump_price_usd_dmt": round(price_l, 2), "fines_price_usd_dmt": round(price_f, 2),
                      "pellet_price_usd_dmt": round(price_p, 2), **costs},
        "liberation": {"rom_pct": round(rom.liberation_pct, 2),
                       "lump_pct": round(lump_product.liberation_pct, 2),
                       "fines_pct": round(ore_fines.liberation_pct, 2),
                       "pellet_pct": round(pellet_product.liberation_pct, 2),
                       "tailings_pct": round(tailings.liberation_pct, 2)},
        "balance": {"in_tph": round(balance_in, 3), "out_tph": round(balance_out, 3),
                    "closure_pct": round(closure, 4)},
        "warnings": warnings, "solve_ms": round(1000 * (time.perf_counter() - t0), 1),
    }
