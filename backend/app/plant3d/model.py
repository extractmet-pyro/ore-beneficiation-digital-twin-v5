"""Plant 3D model — the asset registry.

This module holds the *engineering* description of the plant: every major asset with its
plant tag, its position on the plant grid, its principal dimensions, the geometry archetype
that represents it, the level (floor) it sits on, and the twin variables that drive its
appearance. The browser builds the scene from this data; nothing about the plant layout is
hard-coded in the front end.

Coordinate convention (right-handed, metres):

    +x  east along the main process axis (ROM tip at the west end, products at the east)
    +y  up from the plant datum, 0.000 m = finished grade
    +z  north across the process axis

A real deployment replaces the ``ASSETS`` table below with the site's own survey or CAD
extract (see ``importers.py``); the rest of the layer is unchanged, because everything
downstream reads this table rather than the geometry.
"""
from __future__ import annotations

from typing import Any

#: Plant areas, matching the P&ID area numbering used across the rest of the twin.
AREAS: dict[str, dict[str, Any]] = {
    "A100": {"name": "Crushing and screening", "colour": "#8d6e63", "x_from": -130.0, "x_to": -62.0},
    "A200": {"name": "Scrubbing", "colour": "#00897b", "x_from": -62.0, "x_to": -26.0},
    "A300": {"name": "Lump jigging and recrush", "colour": "#5c6bc0", "x_from": -26.0, "x_to": 2.0},
    "A400": {"name": "Classification and fines jigging", "colour": "#1e88e5", "x_from": -26.0, "x_to": 38.0},
    "A500": {"name": "Spirals and tables", "colour": "#0288d1", "x_from": 38.0, "x_to": 78.0},
    "A600": {"name": "Desliming and WHIMS", "colour": "#c62828", "x_from": 2.0, "x_to": 44.0},
    "A700": {"name": "Product handling and stockpiles", "colour": "#f9a825", "x_from": 78.0, "x_to": 120.0},
    "A800": {"name": "Tailings and thickening", "colour": "#6d4c41", "x_from": 126.0, "x_to": 165.0},
    "A900": {"name": "Water and services", "colour": "#29b6f6", "x_from": 66.0, "x_to": 120.0},
}

#: Elevation bands. A plant 3-D model is only useful if it can be sliced by floor, because
#: that is how maintenance and operations actually think about the building.
LEVELS: list[dict[str, Any]] = [
    {"level_id": "L00", "name": "Grade / ground", "elevation_m": 0.0, "to_m": 4.5},
    {"level_id": "L01", "name": "Pump and sump floor", "elevation_m": 4.5, "to_m": 9.0},
    {"level_id": "L02", "name": "Main process floor", "elevation_m": 9.0, "to_m": 15.0},
    {"level_id": "L03", "name": "Distribution floor", "elevation_m": 15.0, "to_m": 22.0},
    {"level_id": "L04", "name": "Feed and screening floor", "elevation_m": 22.0, "to_m": 34.0},
]

#: Geometry archetypes the viewer knows how to build. Keeping the list short and explicit is
#: deliberate: a plant model that needs arbitrary meshes to be legible is a model nobody
#: maintains. Imported CAD geometry is attached separately (see ``importers.py``).
ARCHETYPES: dict[str, dict[str, Any]] = {
    "jaw_crusher": {"primitive": "wedge", "params": ["width_m", "length_m", "height_m"]},
    "cone_crusher": {"primitive": "cone_body", "params": ["diameter_m", "height_m"]},
    "screen_deck": {"primitive": "inclined_box", "params": ["width_m", "length_m", "height_m", "incline_deg"]},
    "scrubber_drum": {"primitive": "drum", "params": ["diameter_m", "length_m", "incline_deg"]},
    "trommel": {"primitive": "drum", "params": ["diameter_m", "length_m", "incline_deg"]},
    "jig_bank": {"primitive": "cell_bank", "params": ["n_cells", "cell_width_m", "cell_length_m", "height_m"]},
    "screw_classifier": {"primitive": "inclined_trough", "params": ["width_m", "length_m", "incline_deg"]},
    "cyclone_cluster": {"primitive": "cyclone_ring", "params": ["n_units", "diameter_mm", "radius_m", "height_m"]},
    "spiral_bank": {"primitive": "helix_bank", "params": ["n_starts", "turns", "diameter_m", "height_m"]},
    "table_bank": {"primitive": "deck_bank", "params": ["n_decks", "deck_width_m", "deck_length_m"]},
    "whims_carousel": {"primitive": "carousel", "params": ["n_units", "diameter_m", "height_m"]},
    "thickener": {"primitive": "tank_cone", "params": ["diameter_m", "side_depth_m"]},
    "tank": {"primitive": "cylinder", "params": ["diameter_m", "height_m"]},
    "pump": {"primitive": "pump_set", "params": ["length_m", "height_m"]},
    "conveyor": {"primitive": "belt", "params": ["length_m", "width_m", "incline_deg"]},
    "stockpile": {"primitive": "cone_pile", "params": ["base_radius_m", "height_m"]},
    "bin": {"primitive": "hopper", "params": ["top_m", "bottom_m", "height_m"]},
    "building": {"primitive": "shell", "params": ["width_m", "length_m", "height_m"]},
    "platform": {"primitive": "slab", "params": ["width_m", "length_m", "thickness_m"]},
}


def _a(asset_id, tag, name, atype, area, level, pos, dims, *, unit_key=None, power_key=None,
       rot=0.0, streams_in=(), streams_out=(), datasheet=None, criticality="B", bindings=()):
    return {
        "asset_id": asset_id, "tag": tag, "name": name, "type": atype, "area": area, "level": level,
        "position": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
        "rotation_deg": float(rot), "dims": dims,
        "unit_key": unit_key, "power_key": power_key,
        "streams_in": list(streams_in), "streams_out": list(streams_out),
        "datasheet": datasheet or {}, "criticality": criticality,
        "bindings": list(bindings),
    }


#: The asset register. ``unit_key`` ties the geometry to the unit the simulator solves, and
#: ``power_key`` to the motor in the power balance; those two links are what make this a twin
#: of the plant rather than a drawing of it.
ASSETS: list[dict[str, Any]] = [
    # ---------------- A100 crushing and screening -------------------------------------------
    _a("rom_bin", "101-BN-001", "ROM tip bin", "bin", "A100", "L04", (-120, 14.0, -10),
       {"top_m": 9.0, "bottom_m": 2.4, "height_m": 7.5}, streams_out=["S01_rom"],
       datasheet={"live_capacity_t": 320, "liner": "AR400", "grizzly_aperture_mm": 800}, criticality="A",
       bindings=[{"channel": "fill", "source": "stream", "key": "S01_rom.solids_tph", "lo": 0, "hi": 900}]),
    _a("apron_feeder", "101-AF-001", "ROM apron feeder", "conveyor", "A100", "L03", (-112, 10.5, -10),
       {"length_m": 11.0, "width_m": 2.1, "incline_deg": 8.0}, streams_out=["S01_rom"],
       datasheet={"width_mm": 2100, "duty_tph": 900, "drive_kw": 110}),
    _a("primary_crusher", "101-CR-001", "Primary jaw crusher", "jaw_crusher", "A100", "L03",
       (-96, 9.5, -10), {"width_m": 4.6, "length_m": 5.8, "height_m": 6.2},
       unit_key="primary_crusher", power_key="primary_crusher_kw",
       streams_in=["S01_rom"], streams_out=["S02_primary_product"], criticality="A",
       datasheet={"gape_mm": 1200, "css_range_mm": "120-220", "installed_kw": 700, "toggle": "single"},
       bindings=[{"channel": "duty", "source": "unit", "key": "primary_crusher.power_utilisation_pct", "lo": 0, "hi": 100},
                 {"channel": "status", "source": "constraint", "key": "primary_power"}]),
    _a("primary_conveyor", "101-CV-002", "Primary product conveyor", "conveyor", "A100", "L02",
       (-86, 6.0, -10), {"length_m": 13.0, "width_m": 1.2, "incline_deg": -6.0},
       streams_in=["S02_primary_product"], streams_out=["S02_primary_product"],
       datasheet={"width_mm": 1200, "belt_speed_m_s": 2.1, "drive_kw": 75}),
    _a("sizing_screen", "102-SN-001", "Sizing screen", "screen_deck", "A100", "L02", (-76, 9.0, -10),
       {"width_m": 3.6, "length_m": 7.8, "height_m": 2.4, "incline_deg": 18.0},
       unit_key="sizing_screen", power_key="screens_kw",
       streams_in=["S02_primary_product"], streams_out=["S03_screen_oversize", "S04_screen_undersize"],
       datasheet={"decks": 2, "aperture_mm": 40, "area_m2": 44, "drive_kw": 30},
       bindings=[{"channel": "duty", "source": "unit", "key": "sizing_screen.screen_loading_tph_m2", "lo": 0, "hi": 45},
                 {"channel": "status", "source": "constraint", "key": "screen_loading"}]),
    _a("secondary_crusher", "102-CR-002", "Secondary cone crusher", "cone_crusher", "A100", "L02",
       (-76, 6.0, 2), {"diameter_m": 3.0, "height_m": 5.0},
       unit_key="secondary_crusher", power_key="secondary_crusher_kw",
       streams_in=["S03_screen_oversize"], streams_out=["S02_primary_product"], criticality="A",
       datasheet={"mantle_mm": 1300, "css_range_mm": "25-60", "installed_kw": 500}),

    # ---------------- A200 scrubbing ---------------------------------------------------------
    _a("scrubber", "201-SC-001", "Rotary scrubber", "scrubber_drum", "A200", "L02", (-50, 7.5, -10),
       {"diameter_m": 3.6, "length_m": 9.0, "incline_deg": 2.0},
       unit_key="scrubber", power_key="scrubber_kw",
       streams_in=["S04_screen_undersize"], streams_out=["S05_scrubbed"], criticality="A",
       datasheet={"diameter_mm": 3600, "length_mm": 9000, "drive_kw": 250, "lifters": "bolt-in rubber"},
       bindings=[{"channel": "rotation", "source": "unit", "key": "scrubber.speed_pct_critical", "lo": 0, "hi": 45},
                 {"channel": "fill", "source": "unit", "key": "scrubber.solids_pct", "lo": 20, "hi": 65},
                 {"channel": "status", "source": "constraint", "key": "scrubber_residence"}]),
    _a("scrubber_trommel", "201-TR-001", "Scrubber discharge trommel", "trommel", "A200", "L02",
       (-34, 6.5, -10), {"diameter_m": 2.4, "length_m": 5.0, "incline_deg": 3.0},
       unit_key="scrubber_trommel", power_key="screens_kw",
       streams_in=["S05_scrubbed"], streams_out=["S06_lumps", "S07_scrubber_fines"],
       datasheet={"aperture_mm": 10, "open_area_pct": 38}),
    _a("scrubber_sump", "201-SP-001", "Scrubber fines sump and pump", "pump", "A200", "L01",
       (-30, 3.2, -4), {"length_m": 3.2, "height_m": 2.4}, power_key="pumps_kw",
       streams_in=["S07_scrubber_fines"], streams_out=["S07_scrubber_fines"],
       datasheet={"duty_m3_h": 950, "head_m": 28, "drive_kw": 160, "liner": "natural rubber"}),

    # ---------------- A300 lump jigging ------------------------------------------------------
    _a("lump_jig", "301-JG-001", "Lump ore jig", "jig_bank", "A300", "L02", (-14, 9.0, -22),
       {"n_cells": 4, "cell_width_m": 3.0, "cell_length_m": 3.4, "height_m": 5.5},
       unit_key="lump_jig", power_key="lump_jig_kw",
       streams_in=["S06_lumps", "S10b_recrush_oversize"], streams_out=["S08_lump_ore", "S09a_lump_jig_floats"],
       criticality="A",
       datasheet={"cells": 4, "bed_area_m2": 40.8, "ragging": "feldspar", "pulsion_type": "air-pulsed"},
       bindings=[{"channel": "duty", "source": "unit", "key": "lump_jig.loading_tph_m2", "lo": 0.0, "hi": 30.0},
                 {"channel": "value", "source": "unit", "key": "lump_jig.cut_sg_achieved", "lo": 2.8, "hi": 5.0},
                 {"channel": "value", "source": "unit", "key": "lump_jig.bed_looseness", "lo": 0.5, "hi": 2.2},
                 {"channel": "status", "source": "constraint", "key": "jig_bed_looseness"}]),
    _a("lump_dewater_screen", "301-SN-002", "Lump dewatering screen", "screen_deck", "A300", "L01",
       (-2, 5.0, -22), {"width_m": 3.0, "length_m": 6.0, "height_m": 1.8, "incline_deg": 5.0},
       power_key="screens_kw", streams_in=["S08_lump_ore"], streams_out=["S08_lump_ore"],
       datasheet={"aperture_mm": 6, "area_m2": 18}),
    _a("tertiary_crusher", "302-CR-003", "Tertiary recrush cone", "cone_crusher", "A300", "L01",
       (10, 4.5, -30), {"diameter_m": 2.8, "height_m": 4.6},
       unit_key="tertiary_crusher", power_key="tertiary_crusher_kw",
       streams_in=["S09a_lump_jig_floats", "S09b_fines_jig_floats"], streams_out=["S10_tertiary_product"],
       datasheet={"css_range_mm": "6-18", "installed_kw": 450},
       bindings=[{"channel": "duty", "source": "unit", "key": "tertiary_crusher.power_utilisation_pct", "lo": 0, "hi": 100},
                 {"channel": "status", "source": "constraint", "key": "tertiary_power"}]),
    _a("recrush_screen", "302-SN-003", "Recrush classifying screen", "screen_deck", "A300", "L02",
       (20, 7.5, -30), {"width_m": 2.4, "length_m": 5.4, "height_m": 1.8, "incline_deg": 15.0},
       unit_key="recrush_screen", power_key="screens_kw",
       streams_in=["S10_tertiary_product"], streams_out=["S10b_recrush_oversize", "S10c_recrush_fine"],
       datasheet={"aperture_mm": 10, "area_m2": 13}),

    # ---------------- A400 classification and fines jigging -----------------------------------
    _a("spiral_classifier", "401-CL-001", "Screw classifier bank", "screw_classifier", "A400", "L02",
       (-14, 7.0, 6), {"width_m": 3.0, "length_m": 11.0, "incline_deg": 16.0},
       unit_key="spiral_classifier", power_key="classifier_kw",
       streams_in=["S07_scrubber_fines", "S10c_recrush_fine"],
       streams_out=["S11_classifier_sand", "S12_classifier_overflow"], criticality="A",
       datasheet={"screws": 4, "diameter_mm": 3000, "length_mm": 11000, "drive_kw": 4 * 15},
       bindings=[{"channel": "rotation", "source": "unit", "key": "spiral_classifier.screw_rpm", "lo": 0, "hi": 6},
                 {"channel": "value", "source": "unit", "key": "spiral_classifier.d50_quartz_um", "lo": 80, "hi": 500},
                 {"channel": "status", "source": "constraint", "key": "classifier_loading"}]),
    _a("fines_screen", "402-SN-004", "Classifier sand screen", "screen_deck", "A400", "L02", (6, 7.0, 6),
       {"width_m": 2.4, "length_m": 5.0, "height_m": 1.6, "incline_deg": 15.0},
       unit_key="fines_screen", power_key="screens_kw",
       streams_in=["S11_classifier_sand"], streams_out=["S11_classifier_sand"],
       datasheet={"aperture_mm": 3, "area_m2": 12}),
    _a("fines_jig", "402-JG-002", "Fines jig", "jig_bank", "A400", "L02", (18, 9.0, 6),
       {"n_cells": 4, "cell_width_m": 2.4, "cell_length_m": 2.5, "height_m": 4.8},
       unit_key="fines_jig", power_key="fines_jig_kw",
       streams_in=["S11_classifier_sand"], streams_out=["S13_fines_jig_conc", "S09b_fines_jig_floats"],
       datasheet={"cells": 4, "bed_area_m2": 24.0, "ragging": "haematite shot"},
       bindings=[{"channel": "duty", "source": "unit", "key": "fines_jig.loading_tph_m2", "lo": 0.0, "hi": 30.0},
                 {"channel": "value", "source": "unit", "key": "fines_jig.bed_looseness", "lo": 0.5, "hi": 2.2},
                 {"channel": "status", "source": "constraint", "key": "fines_jig_loading"}]),
    _a("spiral_feed_sump", "403-SP-002", "Spiral feed sump and pump", "pump", "A400", "L01", (32, 3.2, 6),
       {"length_m": 3.0, "height_m": 2.2}, power_key="pumps_kw",
       streams_in=["S13_fines_jig_conc"], streams_out=["S13_fines_jig_conc"],
       datasheet={"duty_m3_h": 620, "head_m": 34, "drive_kw": 110}),
    _a("spiral_cyclone", "403-CY-001", "Spiral feed cyclone cluster", "cyclone_cluster", "A400", "L03",
       (44, 15.5, 6), {"n_units": 6, "diameter_mm": 350, "radius_m": 2.2, "height_m": 3.6},
       unit_key="spiral_cyclone", streams_in=["S13_fines_jig_conc"],
       streams_out=["S14_spiral_cyclone_uf", "S15_spiral_cyclone_of"],
       datasheet={"units": 6, "diameter_mm": 350, "vortex_mm": 120, "spigot_mm": 75},
       bindings=[{"channel": "value", "source": "unit", "key": "spiral_cyclone.d50c_um", "lo": 40, "hi": 250}]),

    # ---------------- A500 spirals and tables ------------------------------------------------
    _a("spirals", "501-SP-001", "Spiral concentrator bank", "spiral_bank", "A500", "L03", (58, 10.0, 6),
       {"n_starts": 120, "turns": 5.0, "diameter_m": 0.9, "height_m": 7.0},
       unit_key="spirals", streams_in=["S14_spiral_cyclone_uf"],
       streams_out=["S16_spiral_conc", "S17_spiral_middling", "S18_spiral_tailing"], criticality="A",
       datasheet={"starts": 120, "turns": 5, "diameter_mm": 900, "wash_water": "none"},
       bindings=[{"channel": "duty", "source": "kpi", "key": "spiral_load_fraction", "lo": 0, "hi": 1.2},
                 {"channel": "status", "source": "constraint", "key": "spiral_load"}]),
    _a("shaking_tables", "502-TB-001", "Shaking table bank", "table_bank", "A500", "L02", (58, 7.0, 28),
       {"n_decks": 24, "deck_width_m": 1.8, "deck_length_m": 4.6},
       unit_key="shaking_tables", power_key="tables_kw",
       streams_in=["S17_spiral_middling"],
       streams_out=["S20_table_conc", "S21_table_tailing", "S25_table_middling"],
       datasheet={"decks": 24, "deck_area_m2": 8.3, "stroke_mm": 16, "frequency_rpm": 270},
       bindings=[{"channel": "duty", "source": "kpi", "key": "table_load_fraction", "lo": 0, "hi": 1.2},
                 {"channel": "status", "source": "constraint", "key": "table_load"}]),
    _a("fines_dewater_screen", "503-SN-005", "Sinter fines dewatering screen", "screen_deck", "A500", "L01",
       (74, 5.0, 20), {"width_m": 3.0, "length_m": 6.0, "height_m": 1.8, "incline_deg": 4.0},
       power_key="screens_kw", streams_in=["S19_ore_fines"], streams_out=["S19_ore_fines"],
       datasheet={"aperture_mm": 0.5, "area_m2": 18, "type": "horizontal vibrating"}),

    # ---------------- A600 desliming and WHIMS -----------------------------------------------
    _a("deslime_cyclone", "601-CY-002", "Desliming cyclone cluster", "cyclone_cluster", "A600", "L03",
       (6, 15.5, 40), {"n_units": 10, "diameter_mm": 150, "radius_m": 1.8, "height_m": 2.4},
       unit_key="deslime_cyclone", streams_in=["S12_classifier_overflow", "S15_spiral_cyclone_of"],
       streams_out=["S22_deslime_uf", "S23_deslime_of"],
       datasheet={"units": 10, "diameter_mm": 150, "cut_target_um": 20},
       bindings=[{"channel": "value", "source": "unit", "key": "deslime_cyclone.d50c_um", "lo": 8, "hi": 45}]),
    _a("whims", "602-MS-001", "WHIMS carousel", "whims_carousel", "A600", "L02", (24, 7.5, 40),
       {"n_units": 3, "diameter_m": 3.0, "height_m": 4.2},
       unit_key="whims", power_key="whims_kw",
       streams_in=["S22_deslime_uf"], streams_out=["S27_pellet_fines", "S24_whims_tail"], criticality="A",
       datasheet={"units": 3, "matrix": "expanded metal 1.2 mm", "field_range_T": "0.4-1.6",
                  "rated_tph_each": 60},
       bindings=[{"channel": "rotation", "source": "unit", "key": "whims.ring_speed_rpm", "lo": 0, "hi": 6},
                 {"channel": "value", "source": "unit", "key": "whims.field_tesla", "lo": 0.3, "hi": 1.7},
                 {"channel": "status", "source": "constraint", "key": "whims_load"}]),

    # ---------------- A700 products ----------------------------------------------------------
    _a("lump_stockpile", "701-SK-001", "Lump ore stockpile", "stockpile", "A700", "L00", (100, 0.0, -24),
       {"base_radius_m": 15.0, "height_m": 11.0}, streams_in=["S08_lump_ore"],
       datasheet={"live_capacity_t": 18000, "reclaim": "front-end loader"},
       bindings=[{"channel": "fill", "source": "kpi", "key": "lump_tph", "lo": 0, "hi": 320},
                 {"channel": "value", "source": "kpi", "key": "lump_fe_pct", "lo": 58, "hi": 66}]),
    _a("fines_stockpile", "702-SK-002", "Sinter fines stockpile", "stockpile", "A700", "L00", (100, 0.0, 14),
       {"base_radius_m": 13.0, "height_m": 9.5}, streams_in=["S19_ore_fines"],
       datasheet={"live_capacity_t": 14000},
       bindings=[{"channel": "fill", "source": "kpi", "key": "fines_tph", "lo": 0, "hi": 260},
                 {"channel": "value", "source": "kpi", "key": "fines_fe_pct", "lo": 58, "hi": 68}]),
    _a("pellet_stockpile", "703-SK-003", "Pellet-plant feed stockpile", "stockpile", "A700", "L00",
       (100, 0.0, 50), {"base_radius_m": 10.0, "height_m": 8.0}, streams_in=["S27_pellet_fines"],
       datasheet={"live_capacity_t": 9000},
       bindings=[{"channel": "fill", "source": "kpi", "key": "pellet_fines_tph", "lo": 0, "hi": 160},
                 {"channel": "value", "source": "kpi", "key": "pellet_fines_fe_pct", "lo": 55, "hi": 65}]),
    _a("product_conveyor", "701-CV-010", "Product transfer conveyor", "conveyor", "A700", "L02",
       (84, 8.0, -6), {"length_m": 26.0, "width_m": 1.2, "incline_deg": -10.0},
       streams_in=["S08_lump_ore"], streams_out=["S08_lump_ore"],
       datasheet={"width_mm": 1200, "belt_speed_m_s": 2.4, "drive_kw": 90}),

    # ---------------- A800 tailings ----------------------------------------------------------
    _a("tails_thickener", "801-TH-001", "Tailings thickener", "thickener", "A800", "L01", (140, 2.0, 34),
       {"diameter_m": 22.0, "side_depth_m": 3.6},
       unit_key="tails_thickener", power_key="thickener_kw",
       streams_in=["S28_tailings"], streams_out=["S29_tails_underflow", "S30_tails_overflow"],
       datasheet={"diameter_m": 22, "rake_drive_kw": 18, "flocculant": "anionic polyacrylamide"},
       bindings=[{"channel": "fill", "source": "kpi", "key": "tails_uf_solids_pct", "lo": 30, "hi": 70},
                 {"channel": "status", "source": "constraint", "key": "tails_uf_solids"}]),
    _a("tails_pump", "801-SP-003", "Tailings underflow pump set", "pump", "A800", "L00", (158, 1.4, 44),
       {"length_m": 4.2, "height_m": 2.8}, power_key="pumps_kw",
       streams_in=["S29_tails_underflow"], streams_out=["S29_tails_underflow"],
       datasheet={"duty_m3_h": 420, "head_m": 55, "drive_kw": 200, "arrangement": "2 x 100 % duty/standby"}),

    # ---------------- A900 water and services -------------------------------------------------
    _a("process_water_tank", "901-TK-001", "Process water tank", "tank", "A900", "L00", (92, 0.0, -48),
       {"diameter_m": 12.0, "height_m": 9.0}, streams_in=["S30_tails_overflow"],
       datasheet={"capacity_m3": 1000, "material": "mild steel, epoxy lined"},
       bindings=[{"channel": "fill", "source": "kpi", "key": "water_recycle_pct", "lo": 0, "hi": 100}]),
    _a("water_pumps", "901-SP-004", "Process water pump set", "pump", "A900", "L00", (104, 1.2, -48),
       {"length_m": 3.6, "height_m": 2.4}, power_key="pumps_kw",
       datasheet={"duty_m3_h": 1400, "head_m": 42, "drive_kw": 250}),
    _a("mcc_building", "902-BL-001", "Motor control centre", "building", "A900", "L00", (104, 0.0, -62),
       {"width_m": 10.0, "length_m": 22.0, "height_m": 6.5},
       datasheet={"transformers": 2, "rating_mva": 2.5}),
    _a("control_room", "902-BL-002", "Control room", "building", "A900", "L00", (76, 0.0, -48),
       {"width_m": 9.0, "length_m": 14.0, "height_m": 5.0},
       datasheet={"operator_stations": 3, "dcs": "site standard"}),
]

#: Structural steel and floors, so the model reads as a plant rather than as equipment floating
#: in space. These carry no process meaning and are excluded from clash checking by default.
STRUCTURES: list[dict[str, Any]] = [
    {"structure_id": "plat_crushing", "name": "Crushing platform", "type": "platform", "area": "A100",
     "position": {"x": -86.0, "y": 9.0, "z": -6.0}, "dims": {"width_m": 26.0, "length_m": 44.0, "thickness_m": 0.4}},
    {"structure_id": "plat_scrub", "name": "Scrubber platform", "type": "platform", "area": "A200",
     "position": {"x": -42.0, "y": 4.5, "z": -8.0}, "dims": {"width_m": 20.0, "length_m": 34.0, "thickness_m": 0.4}},
    {"structure_id": "plat_grav", "name": "Gravity plant main floor", "type": "platform", "area": "A400",
     "position": {"x": 14.0, "y": 4.5, "z": 8.0}, "dims": {"width_m": 44.0, "length_m": 70.0, "thickness_m": 0.4}},
    {"structure_id": "plat_spiral", "name": "Spiral tower floors", "type": "platform", "area": "A500",
     "position": {"x": 58.0, "y": 9.0, "z": 14.0}, "dims": {"width_m": 30.0, "length_m": 36.0, "thickness_m": 0.4}},
    {"structure_id": "plat_whims", "name": "WHIMS floor", "type": "platform", "area": "A600",
     "position": {"x": 16.0, "y": 4.5, "z": 40.0}, "dims": {"width_m": 22.0, "length_m": 30.0, "thickness_m": 0.4}},
    {"structure_id": "bl_gravity", "name": "Gravity plant building", "type": "building", "area": "A400",
     "position": {"x": 16.0, "y": 0.0, "z": 8.0}, "dims": {"width_m": 46.0, "length_m": 74.0, "height_m": 22.0},
     "transparent": True},
    {"structure_id": "bl_spiral", "name": "Spiral tower", "type": "building", "area": "A500",
     "position": {"x": 58.0, "y": 0.0, "z": 14.0}, "dims": {"width_m": 32.0, "length_m": 38.0, "height_m": 20.0},
     "transparent": True},
]

#: Saved camera positions. Operators navigate a plant model by place, not by orbiting.
BOOKMARKS: list[dict[str, Any]] = [
    {"id": "overview", "name": "Plant overview", "eye": [-70, 110, 175], "target": [14, 6, 2]},
    {"id": "crushing", "name": "Crushing and screening", "eye": [-120, 36, 36], "target": [-88, 8, -8]},
    {"id": "scrubbing", "name": "Scrubber", "eye": [-62, 24, 22], "target": [-44, 7, -8]},
    {"id": "jigging", "name": "Lump jig", "eye": [-34, 26, -2], "target": [-12, 8, -20]},
    {"id": "classification", "name": "Classification and fines jig", "eye": [-10, 28, 40], "target": [8, 7, 8]},
    {"id": "spirals", "name": "Spiral and table tower", "eye": [92, 32, 46], "target": [58, 9, 16]},
    {"id": "whims", "name": "Desliming and WHIMS", "eye": [-6, 30, 74], "target": [16, 7, 40]},
    {"id": "products", "name": "Product stockpiles", "eye": [150, 48, 14], "target": [100, 5, 14]},
    {"id": "tailings", "name": "Tailings and water", "eye": [178, 40, 70], "target": [142, 4, 36]},
]

#: Heat-map overlays. Painting a live number onto the geometry is the whole reason a plant
#: model earns its place next to the flowsheet.
OVERLAYS: list[dict[str, Any]] = [
    {"id": "none", "name": "Equipment colours", "unit": "", "scale": None},
    {"id": "status", "name": "Constraint status", "unit": "", "scale": "status"},
    {"id": "duty", "name": "Equipment duty", "unit": "% of limit", "scale": "sequential", "lo": 0, "hi": 110},
    {"id": "power", "name": "Motor power", "unit": "kW", "scale": "sequential", "lo": 0, "hi": 320},
    {"id": "throughput", "name": "Solids throughput", "unit": "t/h", "scale": "sequential", "lo": 0, "hi": 650},
    {"id": "fe", "name": "Stream Fe grade", "unit": "% Fe", "scale": "diverging", "lo": 30, "hi": 68},
    {"id": "solids", "name": "Slurry density", "unit": "% solids", "scale": "sequential", "lo": 0, "hi": 80},
]


def assets() -> list[dict[str, Any]]:
    return [dict(a) for a in ASSETS]


def asset_index() -> dict[str, dict[str, Any]]:
    return {a["asset_id"]: a for a in ASSETS}


def by_tag(tag: str) -> dict[str, Any] | None:
    for a in ASSETS:
        if a["tag"].upper() == tag.upper():
            return a
    return None


def level_of(y: float) -> str:
    for lv in LEVELS:
        if lv["elevation_m"] <= y < lv["to_m"]:
            return lv["level_id"]
    return LEVELS[-1]["level_id"] if y >= LEVELS[-1]["elevation_m"] else LEVELS[0]["level_id"]
