"""Optimisation objectives for the ore-beneficiation plant.

Every objective is expressed so that **larger is better**, which lets the optimiser use one sign
convention and lets the desk plot them on a common axis. The interesting ones here are not the
single-number objectives but the trade-offs between them: this plant sells three products at three
prices, so pushing the lump jig for grade moves tonnes into the fines circuit rather than into the
tailings, and the right answer depends on the price deck of the day.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Objective:
    key: str
    label: str
    unit: str
    fn: Callable[[dict], float]
    description: str
    maximise: bool = True

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "unit": self.unit,
                "description": self.description, "maximise": self.maximise}

    def value(self, result: dict) -> float:
        return float(self.fn(result))


OBJECTIVES: list[Objective] = [
    Objective("margin", "Maximise operating margin", "USD/h", lambda r: r["kpis"]["margin_usd_h"],
              "Revenue from all three products less power, water, reagent, wear, mining and fixed cost. "
              "The default objective, and the one that balances the three products against each other."),
    Objective("fe_recovery", "Maximise iron recovery", "%", lambda r: r["kpis"]["fe_recovery_pct"],
              "Iron units in saleable product as a percentage of iron units in the ROM ore. Ignores "
              "which product they end up in, so it will trade lump grade for tonnes."),
    Objective("lump_yield", "Maximise lump yield", "%", lambda r: r["kpis"]["lump_yield_pct"],
              "Lump ore carries the premium and needs no further processing by the customer. "
              "Maximising it makes the jig cut looser, which costs lump grade."),
    Objective("lump_quality", "Minimise lump alumina", "% Al2O3", lambda r: -r["kpis"]["lump_al2o3_pct"],
              "Alumina is the binding penalty element for this ore. Driven by scrubber duty and by "
              "how much clay-bearing middling the jig allows into the sinks.", False),
    Objective("saleable", "Maximise saleable tonnes", "t/h", lambda r: r["kpis"]["saleable_tph"],
              "Total product across lump, sinter fines and pellet-plant feed, regardless of grade."),
    Objective("energy", "Minimise specific energy", "kWh/t", lambda r: -r["kpis"]["energy_kwh_t"],
              "Crushing and scrubbing dominate; the gravity circuit itself is nearly free.", False),
    Objective("water", "Minimise fresh-water draw", "m3/t", lambda r: -r["kpis"]["fresh_water_m3_t"],
              "Fresh make-up after pond reclaim — the number a water-stressed licence is judged on.", False),
    Objective("tailings_grade", "Minimise iron to tailings", "% Fe", lambda r: -r["kpis"]["tailings_fe_pct"],
              "Iron walking to the pond. A direct proxy for how much the gravity circuit is leaving "
              "behind in the middlings.", False),
]
OBJECTIVE_BY_KEY = {o.key: o for o in OBJECTIVES}
