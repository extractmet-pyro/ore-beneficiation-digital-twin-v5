"""Demo plant register. All sites are anonymised as Industry-X (IX-OB-xx)."""
from __future__ import annotations

from functools import lru_cache

from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig

PLANTS: dict[str, dict] = {
    "IX-OB-01": {
        "plant_id": "IX-OB-01", "name": "Industry-X Ore Beneficiation Plant 1",
        "description": "Scrubbing, jigging, spiral and table gravity circuit with a WHIMS on the "
                       "deslimed fines. Makes lump ore for the blast furnace, sinter fines and a "
                       "pellet-plant feed from one run-of-mine stream.",
        "commodity": "Iron ore (hematite / goethite, clay-bearing)", "region": "Anonymised",
        "timezone": "Asia/Kolkata", "commissioned": "2019", "nameplate_tph": 650.0,
        "product": "Lump 62.5 % Fe / 2.2 % Al2O3, sinter fines 64 % Fe, pellet-plant feed 61 % Fe",
        "flowsheet": FlowsheetConfig().model_dump(), "ore": OreConfig().model_dump(),
        "operating": OperatingConfig().model_dump(), "economics": EconomicsConfig().model_dump(),
    },
    "IX-OB-02": {
        "plant_id": "IX-OB-02", "name": "Industry-X Ore Beneficiation Plant 2 (high-clay ore)",
        "description": "Same flowsheet on a lateritic, heavily clay-coated ore. Scrubber duty and "
                       "desliming set the alumina in every product, and the WHIMS circuit carries a "
                       "much larger share of the plant.",
        "commodity": "Iron ore (lateritic, high alumina)", "region": "Anonymised",
        "timezone": "Asia/Kolkata", "commissioned": "2022", "nameplate_tph": 480.0,
        "product": "Lump 61 % Fe / 2.6 % Al2O3, sinter fines 63 % Fe, pellet-plant feed 60 % Fe",
        "flowsheet": FlowsheetConfig(design_throughput_tph=480.0, design_lump_fe_pct=61.0,
                                     design_lump_al2o3_pct=2.6, design_fines_fe_pct=63.0,
                                     design_fe_recovery_pct=89.0).model_dump(),
        "ore": OreConfig(fe_head_pct=51.5, sio2_head_pct=8.0, al2o3_head_pct=7.2, clay_share=0.72,
                         goethite_share=0.38, liberation_d50_um=12_000.0, lump_friability=0.45,
                         axb=68.0, bond_wi_kwh_t=9.4).model_dump(),
        "operating": OperatingConfig(rom_feed_tph=480.0, scrubber_speed_pct_critical=36.0,
                                     scrubber_water_m3_h=560.0, whims_field_tesla=1.30,
                                     deslime_cyclone_pressure_kpa=175.0).model_dump(),
        "economics": EconomicsConfig(alumina_penalty_usd_per_pct=3.2).model_dump(),
    },
    "IX-OB-03": {
        "plant_id": "IX-OB-03", "name": "Industry-X Ore Beneficiation Plant 3 (hard banded ore)",
        "description": "Harder, coarsely banded ore at higher throughput. Jigging does most of the "
                       "work, the spiral circuit is small, and the recrush loop is the bottleneck.",
        "commodity": "Iron ore (hard banded hematite)", "region": "Anonymised",
        "timezone": "Asia/Kolkata", "commissioned": "2024", "nameplate_tph": 820.0,
        "product": "Lump 63.5 % Fe / 1.8 % Al2O3, sinter fines 65 % Fe",
        "flowsheet": FlowsheetConfig(design_throughput_tph=820.0, design_lump_fe_pct=63.5,
                                     design_lump_al2o3_pct=1.8, design_fines_fe_pct=65.0,
                                     crushing={"primary_css_mm": 160.0, "primary_installed_kw": 850.0,
                                               "secondary_css_mm": 38.0, "secondary_installed_kw": 650.0,
                                               "tertiary_css_mm": 8.0, "tertiary_installed_kw": 600.0,
                                               "sizing_screen_aperture_mm": 40.0,
                                               "sizing_screen_area_m2": 58.0},
                                     spirals={"n_starts": 84, "turns": 5.0, "diameter_m": 0.9,
                                              "capacity_tph_per_start": 2.0},
                                     tables={"n_decks": 20, "deck_area_m2": 7.6, "frequency_rpm": 265.0,
                                             "stroke_mm": 16.0, "capacity_tph_per_deck": 1.1,
                                             "installed_kw_per_deck": 2.2},
                                     fresh_water_allocation_m3_h=1800.0).model_dump(),
        "ore": OreConfig(fe_head_pct=57.5, sio2_head_pct=10.5, al2o3_head_pct=3.2, clay_share=0.35,
                         goethite_share=0.12, liberation_d50_um=26_000.0, lump_friability=0.14,
                         axb=42.0, bond_wi_kwh_t=13.8, f80_mm=210.0).model_dump(),
        "operating": OperatingConfig(rom_feed_tph=820.0, secondary_css_mm=38.0,
                                     lump_jig_cut_sg=4.35, lump_jig_hutch_water_m3_h=320.0,
                                     scrubber_speed_pct_critical=26.0).model_dump(),
        "economics": EconomicsConfig(iron_ore_index_usd_dmt=112.0, lump_premium_usd_dmt=11.0).model_dump(),
    },
}

#: Instrument register — the tags the twin reads and writes. A gravity plant carries far fewer
#: instruments than a flotation circuit, which is exactly why the twin earns its place: most of
#: what an operator needs to know here is inferred, not measured.
TAGS: list[dict] = [
    # ---- 100 crushing and screening -----------------------------------------------------------
    {"tag": "101_WIC_001", "label": "ROM feed rate", "unit": "t/h", "area": "100 Crushing", "type": "MV",
     "path": "operating.rom_feed_tph", "sample_s": 5, "noise_pct": 0.9},
    {"tag": "101_AI_002", "label": "Head grade (on-belt XRF)", "unit": "% Fe", "area": "100 Crushing",
     "type": "DV", "path": "ore.fe_head_pct", "sample_s": 60, "noise_pct": 1.3},
    {"tag": "101_AI_003", "label": "Head alumina (on-belt XRF)", "unit": "% Al2O3", "area": "100 Crushing",
     "type": "DV", "path": "ore.al2o3_head_pct", "sample_s": 60, "noise_pct": 2.2},
    {"tag": "102_HIC_004", "label": "Secondary crusher CSS", "unit": "mm", "area": "100 Crushing",
     "type": "MV", "path": "operating.secondary_css_mm", "sample_s": 30, "noise_pct": 0.6},
    {"tag": "102_JI_005", "label": "Secondary crusher power", "unit": "kW", "area": "100 Crushing",
     "type": "PV", "path": "units.secondary_crusher.power_kw", "sample_s": 5, "noise_pct": 2.4},
    {"tag": "103_WI_006", "label": "Sizing screen undersize", "unit": "t/h", "area": "100 Crushing",
     "type": "PV", "path": "units.sizing_screen.undersize_tph", "sample_s": 10, "noise_pct": 1.6},
    # ---- 200 scrubbing -------------------------------------------------------------------------
    {"tag": "201_SIC_010", "label": "Scrubber drum speed", "unit": "% Cs", "area": "200 Scrubbing",
     "type": "MV", "path": "operating.scrubber_speed_pct_critical", "sample_s": 5, "noise_pct": 0.7},
    {"tag": "201_FIC_011", "label": "Scrubber water flow", "unit": "m3/h", "area": "200 Scrubbing",
     "type": "MV", "path": "operating.scrubber_water_m3_h", "sample_s": 5, "noise_pct": 1.2},
    {"tag": "201_JI_012", "label": "Scrubber motor power", "unit": "kW", "area": "200 Scrubbing",
     "type": "PV", "path": "units.scrubber.power_kw", "sample_s": 5, "noise_pct": 2.6},
    {"tag": "202_HS_014", "label": "Trommel lump cut size", "unit": "mm", "area": "200 Scrubbing",
     "type": "MV", "path": "operating.trommel_aperture_mm", "sample_s": 300, "noise_pct": 0.3},
    {"tag": "202_WI_015", "label": "Lump stream rate", "unit": "t/h", "area": "200 Scrubbing",
     "type": "PV", "path": "units.scrubber_trommel.oversize_tph", "sample_s": 10, "noise_pct": 1.8},
    # ---- 300 lump jigging ----------------------------------------------------------------------
    {"tag": "301_DIC_020", "label": "Lump jig cut density (bed pressure)", "unit": "SG",
     "area": "300 Lump jigging", "type": "MV", "path": "operating.lump_jig_cut_sg", "sample_s": 5,
     "noise_pct": 1.5},
    {"tag": "301_FIC_021", "label": "Lump jig hutch water", "unit": "m3/h", "area": "300 Lump jigging",
     "type": "MV", "path": "operating.lump_jig_hutch_water_m3_h", "sample_s": 5, "noise_pct": 1.4},
    {"tag": "301_LIC_022", "label": "Lump jig bed depth", "unit": "mm", "area": "300 Lump jigging",
     "type": "MV", "path": "operating.lump_jig_bed_depth_mm", "sample_s": 10, "noise_pct": 2.0},
    {"tag": "301_HIC_023", "label": "Lump jig stroke", "unit": "mm", "area": "300 Lump jigging",
     "type": "MV", "path": "operating.lump_jig_stroke_mm", "sample_s": 30, "noise_pct": 0.8},
    {"tag": "302_AIC_024", "label": "Lump product Fe (on-belt)", "unit": "% Fe",
     "area": "300 Lump jigging", "type": "CV", "path": "kpis.lump_fe_pct", "sample_s": 120,
     "noise_pct": 0.9},
    {"tag": "302_AIC_025", "label": "Lump product alumina (on-belt)", "unit": "% Al2O3",
     "area": "300 Lump jigging", "type": "CV", "path": "kpis.lump_al2o3_pct", "sample_s": 120,
     "noise_pct": 2.6},
    {"tag": "302_WI_027", "label": "Lump product rate", "unit": "t/h", "area": "300 Lump jigging",
     "type": "PV", "path": "kpis.lump_tph", "sample_s": 10, "noise_pct": 1.5},
    # ---- 400 classification ---------------------------------------------------------------------
    {"tag": "401_FIC_030", "label": "Classifier dilution water", "unit": "m3/h",
     "area": "400 Classification", "type": "MV", "path": "operating.classifier_dilution_water_m3_h",
     "sample_s": 5, "noise_pct": 1.3},
    {"tag": "401_LIC_031", "label": "Classifier weir height", "unit": "m", "area": "400 Classification",
     "type": "MV", "path": "operating.classifier_weir_height_m", "sample_s": 60, "noise_pct": 0.9},
    {"tag": "401_DI_032", "label": "Classifier overflow density", "unit": "% solids",
     "area": "400 Classification", "type": "PV", "path": "units.spiral_classifier.overflow_solids_pct",
     "sample_s": 10, "noise_pct": 2.8},
    {"tag": "401_JI_033", "label": "Classifier screw power", "unit": "kW", "area": "400 Classification",
     "type": "PV", "path": "units.spiral_classifier.power_kw", "sample_s": 10, "noise_pct": 2.2},
    # ---- 500 fines jigging -----------------------------------------------------------------------
    {"tag": "501_DIC_040", "label": "Fines jig cut density", "unit": "SG", "area": "500 Fines jigging",
     "type": "MV", "path": "operating.fines_jig_cut_sg", "sample_s": 5, "noise_pct": 1.7},
    {"tag": "501_FIC_041", "label": "Fines jig hutch water", "unit": "m3/h", "area": "500 Fines jigging",
     "type": "MV", "path": "operating.fines_jig_hutch_water_m3_h", "sample_s": 5, "noise_pct": 1.5},
    {"tag": "502_HIC_043", "label": "Tertiary crusher CSS", "unit": "mm", "area": "500 Fines jigging",
     "type": "MV", "path": "operating.tertiary_css_mm", "sample_s": 30, "noise_pct": 0.7},
    {"tag": "502_JI_044", "label": "Tertiary crusher power", "unit": "kW", "area": "500 Fines jigging",
     "type": "PV", "path": "units.tertiary_crusher.power_kw", "sample_s": 5, "noise_pct": 2.5},
    # ---- 600 spirals ------------------------------------------------------------------------------
    {"tag": "601_PIC_050", "label": "Spiral cyclone manifold pressure", "unit": "kPa", "area": "600 Spirals",
     "type": "MV", "path": "operating.spiral_cyclone_pressure_kpa", "sample_s": 2, "noise_pct": 1.8},
    {"tag": "601_DIC_051", "label": "Spiral feed density", "unit": "% solids", "area": "600 Spirals",
     "type": "MV", "path": "operating.spiral_feed_solids_pct", "sample_s": 5, "noise_pct": 2.1},
    {"tag": "601_HIC_052", "label": "Spiral concentrate splitter", "unit": "fraction", "area": "600 Spirals",
     "type": "MV", "path": "operating.spiral_conc_splitter", "sample_s": 300, "noise_pct": 0.5},
    {"tag": "601_FIC_054", "label": "Spiral wash water", "unit": "m3/h", "area": "600 Spirals", "type": "MV",
     "path": "operating.spiral_wash_water_m3_h", "sample_s": 5, "noise_pct": 1.4},
    # ---- 700 tables -------------------------------------------------------------------------------
    {"tag": "701_HIC_060", "label": "Table concentrate cut", "unit": "fraction", "area": "700 Tables",
     "type": "MV", "path": "operating.table_conc_cut", "sample_s": 300, "noise_pct": 0.6},
    {"tag": "701_HIC_061", "label": "Table deck slope", "unit": "deg", "area": "700 Tables", "type": "MV",
     "path": "operating.table_slope_deg", "sample_s": 300, "noise_pct": 0.8},
    {"tag": "701_AIC_064", "label": "Sinter fines Fe (on-belt)", "unit": "% Fe", "area": "700 Tables",
     "type": "CV", "path": "kpis.fines_fe_pct", "sample_s": 120, "noise_pct": 0.9},
    {"tag": "702_WI_065", "label": "Sinter fines rate", "unit": "t/h", "area": "700 Tables", "type": "PV",
     "path": "kpis.fines_tph", "sample_s": 10, "noise_pct": 1.6},
    # ---- 800 WHIMS ---------------------------------------------------------------------------------
    {"tag": "801_PIC_070", "label": "Desliming cyclone pressure", "unit": "kPa", "area": "800 WHIMS",
     "type": "MV", "path": "operating.deslime_cyclone_pressure_kpa", "sample_s": 2, "noise_pct": 1.9},
    {"tag": "801_JIC_071", "label": "WHIMS field intensity", "unit": "T", "area": "800 WHIMS", "type": "MV",
     "path": "operating.whims_field_tesla", "sample_s": 5, "noise_pct": 1.1},
    {"tag": "801_FIC_072", "label": "WHIMS wash water", "unit": "m3/h", "area": "800 WHIMS", "type": "MV",
     "path": "operating.whims_wash_water_m3_h", "sample_s": 5, "noise_pct": 1.5},
    {"tag": "801_DI_073", "label": "WHIMS feed density", "unit": "% solids", "area": "800 WHIMS",
     "type": "PV", "path": "operating.whims_feed_solids_pct", "sample_s": 10, "noise_pct": 2.7},
    {"tag": "802_AI_075", "label": "Pellet-plant feed Fe", "unit": "% Fe", "area": "800 WHIMS", "type": "CV",
     "path": "kpis.pellet_fines_fe_pct", "sample_s": 240, "noise_pct": 1.2},
    # ---- 900 tailings and water -----------------------------------------------------------------------
    {"tag": "901_FIC_080", "label": "Tailings flocculant", "unit": "g/t", "area": "900 Tailings", "type": "MV",
     "path": "operating.tails_flocculant_g_t", "sample_s": 30, "noise_pct": 1.6},
    {"tag": "901_FIC_081", "label": "Pond reclaim fraction", "unit": "fraction", "area": "900 Tailings",
     "type": "MV", "path": "operating.reclaim_water_fraction", "sample_s": 60, "noise_pct": 0.6},
    {"tag": "901_AI_082", "label": "Tailings Fe grade", "unit": "% Fe", "area": "900 Tailings", "type": "CV",
     "path": "kpis.tailings_fe_pct", "sample_s": 240, "noise_pct": 1.8},
    {"tag": "901_LIC_083", "label": "Tailings thickener bed level", "unit": "m", "area": "900 Tailings",
     "type": "PV", "path": "units.tails_thickener.bed_level_m", "sample_s": 10, "noise_pct": 2.4},
    {"tag": "901_DI_084", "label": "Tailings underflow density", "unit": "% solids", "area": "900 Tailings",
     "type": "PV", "path": "kpis.tails_uf_solids_pct", "sample_s": 10, "noise_pct": 1.9},
    {"tag": "902_JI_091", "label": "Plant specific energy", "unit": "kWh/t", "area": "900 Tailings",
     "type": "CV", "path": "kpis.energy_kwh_t", "sample_s": 60, "noise_pct": 1.2},
]


class PlantService:
    def ids(self) -> list[str]:
        return list(PLANTS)

    def list(self) -> list[dict]:
        return [{k: v for k, v in p.items() if k not in ("flowsheet", "ore", "operating", "economics")}
                for p in PLANTS.values()]

    def get(self, plant_id: str) -> dict:
        if plant_id not in PLANTS:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(f"Unknown plant '{plant_id}'")
        return PLANTS[plant_id]

    def configs(self, plant_id: str) -> tuple[FlowsheetConfig, OreConfig, OperatingConfig, EconomicsConfig]:
        p = self.get(plant_id)
        return (FlowsheetConfig(**p["flowsheet"]), OreConfig(**p["ore"]),
                OperatingConfig(**p["operating"]), EconomicsConfig(**p["economics"]))

    def tags(self, plant_id: str) -> list[dict]:
        self.get(plant_id)
        return [{**t, "plant_id": plant_id, "fqn": f"{plant_id}.{t['tag']}"} for t in TAGS]


@lru_cache(maxsize=1)
def get_plant_service() -> PlantService:
    return PlantService()
