"""Configuration models for the ore-beneficiation plant.

These pydantic models are the single source of truth for what the plant *is* (equipment), what it
is *fed* (ore), how it is *run* (set-points) and what the products are *worth* (economics). The
operator desk builds its input forms directly from the JSON schema of these classes, so adding a
field here makes it editable in the browser without touching the frontend.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CrushingConfig(BaseModel):
    """Three-stage crushing: jaw, secondary cone (closed with the sizing screen), tertiary cone."""

    primary_css_mm: float = Field(150.0, ge=80, le=250, description="Jaw crusher closed side setting")
    primary_installed_kw: float = Field(600.0, ge=100, le=2000)
    secondary_css_mm: float = Field(35.0, ge=15, le=80, description="Secondary cone closed side setting")
    secondary_installed_kw: float = Field(450.0, ge=100, le=1500)
    tertiary_css_mm: float = Field(8.0, ge=4, le=25, description="Tertiary cone recrushing the jig floats")
    tertiary_installed_kw: float = Field(450.0, ge=50, le=1500)
    sizing_screen_aperture_mm: float = Field(40.0, ge=15, le=90)
    sizing_screen_area_m2: float = Field(44.0, ge=6, le=140)
    axb_override: float | None = Field(None, description="Overrides the ore A x b if the survey differs")


class ScrubberConfig(BaseModel):
    """Rotary scrubber that detaches clay and ochre from the ore surface."""

    diameter_m: float = Field(3.6, ge=1.8, le=6.0)
    length_m: float = Field(9.0, ge=4.0, le=16.0)
    lifter_count: int = Field(8, ge=4, le=16)
    installed_kw: float = Field(400.0, ge=75, le=1200)
    trommel_aperture_mm: float = Field(10.0, ge=4.0, le=25.0,
                                       description="Scrubber discharge trommel: lump / fines split size")


class JigConfig(BaseModel):
    """Pulsed-bed jig (Baum / Batac type)."""

    n_cells: int = Field(2, ge=1, le=6)
    cell_area_m2: float = Field(6.0, ge=1.0, le=20.0)
    installed_kw: float = Field(75.0, ge=10, le=400)
    screen_aperture_mm: float | None = Field(None, description="Pre-screen ahead of this jig, if any")


class ClassifierConfig(BaseModel):
    """Screw (spiral) classifier making the sand / slime split ahead of the gravity circuit."""

    n_units: int = Field(4, ge=1, le=10)
    tank_width_m: float = Field(3.0, ge=0.9, le=5.0)
    tank_length_m: float = Field(11.0, ge=4.0, le=18.0)
    slope_deg: float = Field(18.0, ge=12.0, le=22.0)
    installed_kw: float = Field(75.0, ge=7.5, le=300)


class CycloneConfig(BaseModel):
    n_installed: int = Field(12, ge=2, le=40)
    diameter_mm: float = Field(350.0, ge=100, le=800)
    vortex_mm: float = Field(120.0, ge=40, le=320)
    apex_mm: float = Field(85.0, ge=25, le=250)


class SpiralConfig(BaseModel):
    """Bank of spiral concentrators — the workhorse of the fines circuit."""

    n_starts: int = Field(120, ge=8, le=400, description="Total spiral starts in the bank")
    turns: float = Field(5.0, ge=3.0, le=9.0)
    diameter_m: float = Field(0.9, ge=0.4, le=1.5)
    capacity_tph_per_start: float = Field(2.0, ge=0.5, le=4.0)


class TableConfig(BaseModel):
    """Bank of shaking tables cleaning the spiral middling."""

    n_decks: int = Field(28, ge=4, le=120)
    deck_area_m2: float = Field(7.6, ge=2.0, le=14.0)
    frequency_rpm: float = Field(265.0, ge=180, le=340)
    stroke_mm: float = Field(16.0, ge=8, le=30)
    capacity_tph_per_deck: float = Field(1.1, ge=0.3, le=3.0)
    installed_kw_per_deck: float = Field(2.2, ge=0.5, le=6.0)


class WhimsConfig(BaseModel):
    """Wet high-intensity magnetic separators recovering the deslimed fines as pellet feed."""

    n_units: int = Field(3, ge=1, le=10)
    matrix: str = Field("expanded_metal", description="expanded_metal | grooved_plate | steel_wool | rod")
    gap_mm: float = Field(4.0, ge=1.0, le=12.0)
    ring_speed_rpm: float = Field(4.0, ge=1.0, le=8.0)
    capacity_tph_per_unit: float = Field(45.0, ge=10, le=150)
    installed_kw: float = Field(110.0, ge=25, le=400)


class ThickenerConfig(BaseModel):
    diameter_m: float = Field(45.0, ge=8, le=90)
    depth_m: float = Field(4.0, ge=2, le=9)
    rake_torque_rating_knm: float = Field(900.0, ge=50, le=4000)


class FlowsheetConfig(BaseModel):
    """Equipment inventory and design intent for the whole plant."""

    circuit: str = Field("SCRUB_JIG_SPIRAL_TABLE_WHIMS",
                         description="Scrubbing + jigging + spirals + tables + WHIMS")
    design_throughput_tph: float = Field(600.0, ge=100, le=2000)
    design_lump_fe_pct: float = Field(62.5, ge=55, le=68)
    design_fines_fe_pct: float = Field(64.0, ge=54, le=68)
    design_pellet_fe_pct: float = Field(62.0, ge=55, le=69)
    design_lump_al2o3_pct: float = Field(2.20, ge=0.5, le=6.0)
    design_fe_recovery_pct: float = Field(92.0, ge=50, le=97)
    fresh_water_allocation_m3_h: float = Field(1500.0, ge=200, le=5000)
    crushing: CrushingConfig = CrushingConfig()
    scrubber: ScrubberConfig = ScrubberConfig()
    lump_jig: JigConfig = JigConfig(n_cells=4, cell_area_m2=6.0, installed_kw=110.0)
    fines_jig: JigConfig = JigConfig(n_cells=4, cell_area_m2=6.0, installed_kw=90.0, screen_aperture_mm=2.0)
    classifier: ClassifierConfig = ClassifierConfig()
    deslime_cyclone: CycloneConfig = CycloneConfig(n_installed=14, diameter_mm=250.0, vortex_mm=80.0, apex_mm=55.0)
    spiral_cyclone: CycloneConfig = CycloneConfig()
    spirals: SpiralConfig = SpiralConfig()
    tables: TableConfig = TableConfig()
    whims: WhimsConfig = WhimsConfig()
    tails_thickener: ThickenerConfig = ThickenerConfig()


class OreConfig(BaseModel):
    """Run-of-mine ore descriptors. These are what a survey or a drill-core programme delivers."""

    fe_head_pct: float = Field(54.0, ge=40, le=66, description="Fe in the run-of-mine ore")
    sio2_head_pct: float = Field(9.0, ge=1, le=35)
    al2o3_head_pct: float = Field(5.0, ge=0.5, le=12, description="Alumina — the dominant penalty element")
    goethite_share: float = Field(0.22, ge=0.0, le=0.7, description="Goethite fraction of the iron minerals")
    liberation_d50_um: float = Field(18_000.0, ge=2_000, le=60_000,
                                     description="Mineralogical banding scale: ore is liberated below this size")
    bond_wi_kwh_t: float = Field(11.0, ge=6, le=20)
    axb: float = Field(55.0, ge=20, le=140, description="Drop-weight impact parameter (soft ore = high A x b)")
    f80_mm: float = Field(180.0, ge=50, le=600)
    moisture_pct: float = Field(5.0, ge=0.0, le=14.0)
    clay_share: float = Field(0.55, ge=0.0, le=0.85,
                              description="Fraction of the alumina gangue that is detachable surface clay "
                                          "(the rest is locked in the ore and leaves in the products)")
    lump_friability: float = Field(0.25, ge=0.0, le=0.8,
                                   description="How readily lumps degrade to fines in handling and scrubbing")


class OperatingConfig(BaseModel):
    """Every set-point an operator or the supervisory controller can move."""

    rom_feed_tph: float = Field(600.0, ge=250, le=900)
    primary_css_mm: float = Field(150.0, ge=90, le=220)
    secondary_css_mm: float = Field(35.0, ge=18, le=65)
    tertiary_css_mm: float = Field(8.0, ge=4, le=20)
    scrubber_speed_pct_critical: float = Field(30.0, ge=18, le=42)
    scrubber_water_m3_h: float = Field(420.0, ge=120, le=900)
    scrubber_solids_pct: float = Field(62.0, ge=45, le=78)
    trommel_aperture_mm: float = Field(10.0, ge=5, le=20)
    lump_jig_cut_sg: float = Field(4.20, ge=2.9, le=4.9)
    lump_jig_stroke_mm: float = Field(22.0, ge=10, le=45)
    lump_jig_frequency_rpm: float = Field(120.0, ge=60, le=220)
    lump_jig_bed_depth_mm: float = Field(220.0, ge=100, le=420)
    lump_jig_hutch_water_m3_h: float = Field(260.0, ge=60, le=600)
    classifier_dilution_water_m3_h: float = Field(180.0, ge=80, le=900)
    classifier_weir_height_m: float = Field(0.30, ge=0.15, le=0.55)
    classifier_screw_rpm: float = Field(4.5, ge=2.0, le=9.0)
    fines_screen_aperture_mm: float = Field(2.0, ge=0.8, le=6.0)
    fines_jig_cut_sg: float = Field(4.20, ge=2.9, le=4.8)
    fines_jig_hutch_water_m3_h: float = Field(130.0, ge=30, le=360)
    deslime_cyclone_pressure_kpa: float = Field(150.0, ge=70, le=280)
    deslime_cyclones_open: int = Field(11, ge=3, le=30)
    spiral_cyclone_pressure_kpa: float = Field(110.0, ge=60, le=220)
    spiral_cyclones_open: int = Field(9, ge=3, le=30)
    spiral_feed_solids_pct: float = Field(28.0, ge=16, le=42)
    spiral_wash_water_m3_h: float = Field(120.0, ge=20, le=320)
    spiral_conc_splitter: float = Field(0.26, ge=0.08, le=0.55,
                                        description="Concentrate splitter, fraction of trough width from the inside")
    spiral_middling_splitter: float = Field(0.52, ge=0.20, le=0.85)
    table_slope_deg: float = Field(3.2, ge=1.2, le=7.0)
    table_wash_water_m3_h: float = Field(65.0, ge=15, le=180)
    table_conc_cut: float = Field(0.30, ge=0.12, le=0.65)
    whims_field_tesla: float = Field(1.15, ge=0.4, le=1.6)
    whims_wash_water_m3_h: float = Field(95.0, ge=20, le=260)
    whims_feed_solids_pct: float = Field(30.0, ge=15, le=45)
    tails_flocculant_g_t: float = Field(32.0, ge=5, le=90)
    tails_underflow_target_pct: float = Field(55.0, ge=40, le=70)
    reclaim_water_fraction: float = Field(0.84, ge=0.4, le=0.95)


class EconomicsConfig(BaseModel):
    """Price deck and cost basis. Indian domestic iron-ore realisations, USD per dry tonne."""

    iron_ore_index_usd_dmt: float = Field(105.0, ge=40, le=220, description="62 % Fe index")
    lump_premium_usd_dmt: float = Field(9.0, ge=0, le=30, description="Lump ore premium over fines")
    pellet_feed_premium_usd_dmt: float = Field(14.0, ge=0, le=45)
    fe_adjustment_usd_per_pct: float = Field(2.35, ge=0.5, le=6.0)
    silica_penalty_usd_per_pct: float = Field(1.10, ge=0, le=5)
    alumina_penalty_usd_per_pct: float = Field(2.60, ge=0, le=8,
                                               description="Alumina penalty — the binding quality constraint")
    alumina_free_allowance_pct: float = Field(2.5, ge=0.5, le=5.0)
    loi_penalty_usd_per_pct: float = Field(0.55, ge=0, le=3)
    freight_usd_dmt: float = Field(7.5, ge=0, le=40)
    power_usd_kwh: float = Field(0.085, ge=0.02, le=0.30)
    water_usd_m3: float = Field(0.28, ge=0.02, le=1.5)
    flocculant_usd_kg: float = Field(3.4, ge=0.5, le=12)
    mining_cost_usd_t: float = Field(11.0, ge=2, le=40)
    fixed_cost_usd_h: float = Field(2350.0, ge=200, le=12000)
    wear_parts_usd_t: float = Field(0.42, ge=0.05, le=3.0)
