"""Constraint hierarchy for the ore-beneficiation plant.

Constraints are ranked in five priority tiers, the way a real supervisory system ranks them:

1. **Safety and equipment protection** — nothing may exceed a mechanical rating.
2. **Product specification** — the contract the plant sells against. For this ore the binding
   spec is *alumina*, not silica: a lump at 2.6 % Al2O3 is discounted whatever its Fe grade.
3. **Environmental and licence** — water draw, tailings clarity.
4. **Process stability** — loads that keep every separator inside the range where its partition
   curve is sharp.
5. **Efficiency** — what is merely worth having.

Each constraint reports a margin in per cent of its own limit, so a single ``penalty`` can rank
a violated tier-1 constraint far above a missed tier-5 target.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Constraint:
    key: str
    label: str
    priority: int
    kind: str                     # "max" | "min" | "range"
    unit: str
    limit: float
    limit_hi: float | None = None
    group: str = "process"
    rationale: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "priority": self.priority, "kind": self.kind,
                "unit": self.unit, "limit": self.limit, "limit_hi": self.limit_hi,
                "group": self.group, "rationale": self.rationale}

    def evaluate(self, value: float | None) -> dict:
        if value is None:
            return {**self.as_dict(), "value": None, "margin_pct": None, "status": "offline", "violated": False}
        if self.kind == "max":
            margin = 100.0 * (self.limit - value) / max(abs(self.limit), 1e-9)
        elif self.kind == "min":
            margin = 100.0 * (value - self.limit) / max(abs(self.limit), 1e-9)
        else:
            lo, hi = self.limit, (self.limit_hi if self.limit_hi is not None else self.limit)
            span = max(hi - lo, 1e-9)
            margin = 100.0 * min(value - lo, hi - value) / span
        margin = float(margin)
        status = "alarm" if margin < 0 else ("caution" if margin < 8 else "normal")
        return {**self.as_dict(), "value": round(float(value), 4), "margin_pct": round(margin, 2),
                "status": status, "violated": bool(margin < 0)}


CONSTRAINTS: list[Constraint] = [
    # ---- tier 1: equipment protection --------------------------------------------------------
    Constraint("primary_power", "Primary crusher power", 1, "max", "% installed", 92.0, None, "crushing",
               "Jaw crusher motor rating"),
    Constraint("secondary_power", "Secondary crusher power", 1, "max", "% installed", 92.0, None, "crushing",
               "Cone crusher motor and hydroset rating"),
    Constraint("tertiary_power", "Tertiary crusher power", 1, "max", "% installed", 92.0, None, "crushing",
               "Recrush cone motor rating"),
    Constraint("scrubber_power", "Scrubber power", 1, "max", "% installed", 90.0, None, "scrubbing",
               "Drum drive and gearbox rating"),
    Constraint("screen_loading", "Sizing screen loading", 1, "max", "t/h/m2", 26.0, None, "crushing",
               "Deck loading above which screening efficiency collapses"),
    Constraint("tails_rake_torque", "Tailings rake torque", 1, "max", "% rating", 80.0, None, "tailings",
               "Rake drive protection — a buried rake is a multi-day outage"),
    # ---- tier 2: product specification --------------------------------------------------------
    Constraint("lump_fe", "Lump ore Fe grade", 2, "min", "% Fe", 61.5, None, "quality",
               "Direct blast-furnace feed specification"),
    Constraint("lump_al2o3", "Lump ore alumina", 2, "max", "% Al2O3", 2.5, None, "quality",
               "Alumina penalty threshold — the binding commercial constraint for this ore"),
    Constraint("lump_sio2", "Lump ore silica", 2, "max", "% SiO2", 6.5, None, "quality",
               "Sinter and blast-furnace slag volume"),
    Constraint("fines_fe", "Sinter fines Fe grade", 2, "min", "% Fe", 63.0, None, "quality",
               "Sinter plant feed specification"),
    Constraint("fines_al2o3", "Sinter fines alumina", 2, "max", "% Al2O3", 2.8, None, "quality",
               "Sinter productivity falls sharply above this alumina level"),
    Constraint("pellet_fe", "Pellet-plant feed Fe grade", 2, "min", "% Fe", 58.0, None, "quality",
               "Minimum grade the pellet plant will accept for further grinding"),
    Constraint("lump_yield", "Lump yield", 2, "min", "%", 28.0, None, "quality",
               "Lump is the premium product; contract commitments depend on it"),
    # ---- tier 3: environmental and licence ----------------------------------------------------
    Constraint("fresh_water", "Fresh-water draw", 3, "max", "m3/h", 1500.0, None, "water",
               "Abstraction licence"),
    Constraint("tails_overflow_tss", "Tailings overflow clarity", 3, "max", "mg/L", 180.0, None, "water",
               "Recycled water clarity — suspended solids foul the spiral wash-water sprays"),
    Constraint("tails_uf_solids", "Tailings underflow density", 3, "min", "% solids", 48.0, None, "tailings",
               "Pond consolidation and water recovery"),
    Constraint("slimes_loss", "Slimes lost to tailings", 3, "max", "% of feed", 6.0, None, "tailings",
               "Ultrafine loss — both a recovery loss and a pond-management problem"),
    # ---- tier 4: process stability -------------------------------------------------------------
    Constraint("spiral_load", "Spiral bank loading", 4, "max", "fraction", 1.0, None, "gravity",
               "Above nameplate the spiral band widens and the split loses definition"),
    Constraint("table_load", "Shaking-table loading", 4, "max", "fraction", 1.0, None, "gravity",
               "Overloaded decks lose the middling band"),
    Constraint("whims_load", "WHIMS loading", 4, "max", "fraction", 1.0, None, "magnetics",
               "Above nameplate magnetics wash through the matrix"),
    Constraint("jig_bed_looseness", "Lump jig bed condition", 4, "range", "index", 0.7, 1.6, "gravity",
               "Too tight and the bed will not stratify; too loose and it fluidises"),
    Constraint("classifier_loading", "Classifier sand loading", 4, "max", "t/h/m2", 9.0, None, "classification",
               "Rake capacity and pool disturbance"),
    Constraint("lump_jig_loading", "Lump jig bed loading", 4, "max", "t/h/m2", 24.0, None, "gravity",
               "Above this the bed will not stratify inside one pulsion cycle"),
    Constraint("fines_jig_loading", "Fines jig bed loading", 4, "max", "t/h/m2", 20.0, None, "gravity",
               "Fine feed needs a longer settling window per cycle"),
    Constraint("recrush_circulating_load", "Recrush circulating load", 4, "max", "%", 60.0, None, "crushing",
               "A runaway recrush loop starves the jig of fresh feed"),
    Constraint("spiral_cyclone_pressure", "Spiral cyclone pressure", 4, "range", "kPa", 80.0, 190.0,
               "classification", "Below range the cyclone ropes, above it the apex wears"),
    Constraint("deslime_cyclone_pressure", "Desliming cyclone pressure", 4, "range", "kPa", 100.0, 240.0,
               "classification", "Cut size control for the WHIMS feed"),
    Constraint("scrubber_residence", "Scrubber residence time", 4, "min", "min", 1.5, None, "scrubbing",
               "Below this the clay is not detached and alumina carries into the products"),
    # ---- tier 5: efficiency --------------------------------------------------------------------
    Constraint("fe_recovery", "Plant Fe recovery", 5, "min", "%", 88.0, None, "efficiency",
               "Business plan target"),
    Constraint("mass_yield", "Mass yield", 5, "min", "%", 72.0, None, "efficiency", "Saleable tonnes per ROM tonne"),
    Constraint("energy", "Specific energy", 5, "max", "kWh/t", 3.2, None, "efficiency", "Energy budget"),
    Constraint("tailings_fe", "Tailings Fe grade", 5, "max", "% Fe", 24.0, None, "efficiency",
               "Iron walking to the pond"),
    Constraint("clay_removal", "Scrubber clay removal", 5, "min", "%", 40.0, None, "scrubbing",
               "Effectiveness of the attrition duty"),
]
CONSTRAINT_BY_KEY = {c.key: c for c in CONSTRAINTS}


def constraint_values(result: dict) -> dict[str, float | None]:
    """Map a solved circuit onto the constraint register."""
    k, u = result["kpis"], result["units"]
    return {
        "primary_power": u["primary_crusher"].get("power_utilisation_pct"),
        "secondary_power": u["secondary_crusher"].get("power_utilisation_pct"),
        "tertiary_power": u["tertiary_crusher"].get("power_utilisation_pct"),
        "scrubber_power": u["scrubber"].get("power_utilisation_pct"),
        "screen_loading": u["sizing_screen"].get("screen_loading_tph_m2"),
        "tails_rake_torque": u["tails_thickener"].get("rake_torque_pct"),
        "lump_fe": k["lump_fe_pct"],
        "lump_al2o3": k["lump_al2o3_pct"],
        "lump_sio2": k["lump_sio2_pct"],
        "fines_fe": k["fines_fe_pct"],
        "fines_al2o3": k["fines_al2o3_pct"],
        "pellet_fe": k["pellet_fines_fe_pct"],
        "lump_yield": k["lump_yield_pct"],
        "fresh_water": k["fresh_water_m3_h"],
        "tails_overflow_tss": k["tails_overflow_tss_mg_l"],
        "tails_uf_solids": k["tails_uf_solids_pct"],
        "slimes_loss": k["slimes_to_tailings_pct"],
        "spiral_load": k["spiral_load_fraction"],
        "table_load": k["table_load_fraction"],
        "whims_load": k["whims_load_fraction"],
        "jig_bed_looseness": u["lump_jig"].get("bed_looseness"),
        "classifier_loading": u["spiral_classifier"].get("sand_loading_tph_m2"),
        "lump_jig_loading": u["lump_jig"].get("loading_tph_m2"),
        "fines_jig_loading": u["fines_jig"].get("loading_tph_m2"),
        "recrush_circulating_load": u["tertiary_crusher"].get("circulating_load_pct"),
        "spiral_cyclone_pressure": u["spiral_cyclone"].get("pressure_kpa"),
        "deslime_cyclone_pressure": u["deslime_cyclone"].get("pressure_kpa"),
        "scrubber_residence": u["scrubber"].get("residence_time_min"),
        "fe_recovery": k["fe_recovery_pct"],
        "mass_yield": k["mass_yield_pct"],
        "energy": k["energy_kwh_t"],
        "tailings_fe": k["tailings_fe_pct"],
        "clay_removal": k["scrubber_clay_removal_pct"],
    }


def evaluate_all(result: dict, overrides: dict[str, dict] | None = None) -> list[dict]:
    """Evaluate every constraint against a solved circuit."""
    values = constraint_values(result)
    rows = []
    for c in CONSTRAINTS:
        spec = c
        ov = (overrides or {}).get(c.key)
        if ov:
            spec = Constraint(**{**c.as_dict(), **{k: v for k, v in ov.items() if k in c.as_dict()}})
        rows.append(spec.evaluate(values.get(c.key)))
    return rows


def penalty(result: dict, overrides: dict[str, dict] | None = None) -> float:
    """Single scalar penalty, weighted so a tier-1 violation dominates a tier-5 shortfall."""
    weight = {1: 400.0, 2: 120.0, 3: 60.0, 4: 25.0, 5: 8.0}
    total = 0.0
    for row in evaluate_all(result, overrides):
        m = row["margin_pct"]
        if m is None or m >= 0:
            continue
        total += weight[row["priority"]] * (abs(m) / 100.0) ** 1.25
    return float(total)
