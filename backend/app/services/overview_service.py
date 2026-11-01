"""Plant overview: area cards, flowsheet payload and shift performance."""
from __future__ import annotations

import numpy as np

from app.services.historian_service import get_historian
from app.services.live_service import current_hour, whole_hour
from app.services.plant_service import get_plant_service
from app.services.simulation_service import get_simulation_service

AREAS = [
    {"id": "A100", "name": "Crushing & screening",
     "units": ["primary_crusher", "secondary_crusher", "sizing_screen"],
     "kpi": ["specific_energy_kwh_t", "p80_mm", "circulating_load_pct"]},
    {"id": "A200", "name": "Scrubbing & sizing", "units": ["scrubber", "scrubber_trommel"],
     "kpi": ["clay_detachment_pct", "residence_time_min", "lump_fraction_pct"]},
    {"id": "A300", "name": "Lump jigging", "units": ["lump_jig"],
     "kpi": ["cut_sg_achieved", "yield_pct", "conc_fe_pct", "fe_recovery_pct"]},
    {"id": "A400", "name": "Classification", "units": ["spiral_classifier", "fines_screen"],
     "kpi": ["d50_quartz_um", "sand_loading_tph_m2", "overflow_tph"]},
    {"id": "A500", "name": "Fines jigging & recrush", "units": ["fines_jig", "tertiary_crusher", "recrush_screen"],
     "kpi": ["cut_sg_achieved", "conc_fe_pct", "circulating_load_pct"]},
    {"id": "A600", "name": "Cyclones & spirals", "units": ["spiral_cyclone", "spirals"],
     "kpi": ["d50c_um", "conc_fe_pct", "load_fraction", "fe_recovery_pct"]},
    {"id": "A700", "name": "Shaking tables", "units": ["shaking_tables"],
     "kpi": ["conc_fe_pct", "load_fraction", "fe_recovery_pct"]},
    {"id": "A800", "name": "Desliming & WHIMS", "units": ["deslime_cyclone", "whims"],
     "kpi": ["d50c_um", "conc_fe_pct", "fe_recovery_pct", "loading_fraction"]},
    {"id": "A900", "name": "Tailings & water", "units": ["tails_thickener", "water_recovery"],
     "kpi": ["underflow_solids_pct", "recycle_pct", "overflow_tss_mg_l"]},
]

FLOWSHEET_NODES = [
    {"id": "rom", "label": "ROM ore", "area": "A100", "type": "source", "x": 40, "y": 110},
    {"id": "crushing", "label": "Primary / secondary crushing", "area": "A100", "type": "crusher",
     "x": 170, "y": 110},
    {"id": "sizing_screen", "label": "Sizing screen 40 mm", "area": "A100", "type": "screen", "x": 300, "y": 110},
    {"id": "scrubber", "label": "Rotary scrubber", "area": "A200", "type": "scrubber", "x": 430, "y": 110},
    {"id": "trommel", "label": "Scrubber trommel", "area": "A200", "type": "screen", "x": 550, "y": 110},
    {"id": "lump_jig", "label": "Lump jig", "area": "A300", "type": "jig", "x": 690, "y": 70},
    {"id": "lump_product", "label": "Lump ore", "area": "A300", "type": "product", "x": 850, "y": 70},
    {"id": "tertiary_crusher", "label": "Tertiary crusher (recrush)", "area": "A500", "type": "crusher",
     "x": 690, "y": 190},
    {"id": "classifier", "label": "Screw classifier", "area": "A400", "type": "classifier", "x": 170, "y": 300},
    {"id": "fines_screen", "label": "Fines screen 2 mm", "area": "A400", "type": "screen", "x": 300, "y": 300},
    {"id": "fines_jig", "label": "Fines jig", "area": "A500", "type": "jig", "x": 430, "y": 250},
    {"id": "spiral_cyclone", "label": "Spiral-feed cyclones", "area": "A600", "type": "cyclone",
     "x": 430, "y": 360},
    {"id": "spirals", "label": "Spiral concentrators", "area": "A600", "type": "spiral", "x": 570, "y": 360},
    {"id": "tables", "label": "Shaking tables", "area": "A700", "type": "table", "x": 700, "y": 430},
    {"id": "fines_product", "label": "Sinter fines", "area": "A700", "type": "product", "x": 850, "y": 360},
    {"id": "deslime_cyclone", "label": "Desliming cyclones", "area": "A800", "type": "cyclone",
     "x": 170, "y": 460},
    {"id": "whims", "label": "WHIMS", "area": "A800", "type": "magnet", "x": 300, "y": 460},
    {"id": "pellet_product", "label": "Pellet-plant feed", "area": "A800", "type": "product", "x": 430, "y": 460},
    {"id": "tails_thickener", "label": "Tailings thickener", "area": "A900", "type": "thickener",
     "x": 700, "y": 540},
    {"id": "water", "label": "Water recovery", "area": "A900", "type": "water", "x": 880, "y": 540},
]
FLOWSHEET_EDGES = [
    {"from": "rom", "to": "crushing", "stream": "S01_rom"},
    {"from": "crushing", "to": "sizing_screen", "stream": "S02_primary_product"},
    {"from": "sizing_screen", "to": "crushing", "stream": "S03_screen_oversize", "kind": "recycle",
     "label": "oversize to secondary"},
    {"from": "sizing_screen", "to": "scrubber", "stream": "S04_screen_undersize", "label": "-40 mm"},
    {"from": "scrubber", "to": "trommel", "stream": "S05_scrubbed"},
    {"from": "trommel", "to": "lump_jig", "stream": "S06_lumps", "label": "+10 mm lumps"},
    {"from": "trommel", "to": "classifier", "stream": "S07_scrubber_fines", "label": "-10 mm fines"},
    {"from": "lump_jig", "to": "lump_product", "stream": "S08_lump_ore", "kind": "product", "label": "sinks"},
    {"from": "lump_jig", "to": "tertiary_crusher", "stream": "S09_jig_floats", "label": "floats"},
    {"from": "tertiary_crusher", "to": "lump_jig", "stream": "S10b_recrush_oversize", "kind": "recycle",
     "label": "+10 mm recrush"},
    {"from": "tertiary_crusher", "to": "classifier", "stream": "S10_tertiary_product", "label": "-10 mm"},
    {"from": "classifier", "to": "fines_screen", "stream": "S11_classifier_sand", "label": "sand"},
    {"from": "classifier", "to": "deslime_cyclone", "stream": "S12_classifier_overflow", "label": "slimes"},
    {"from": "fines_screen", "to": "fines_jig", "stream": "S11_classifier_sand", "label": "+2 mm"},
    {"from": "fines_screen", "to": "spiral_cyclone", "stream": "S14_spiral_cyclone_uf", "label": "-2 mm"},
    {"from": "fines_jig", "to": "fines_product", "stream": "S13_fines_jig_conc", "kind": "product",
     "label": "sinks"},
    {"from": "fines_jig", "to": "tertiary_crusher", "stream": "S09_jig_floats", "label": "floats"},
    {"from": "spiral_cyclone", "to": "spirals", "stream": "S14_spiral_cyclone_uf", "label": "underflow"},
    {"from": "spiral_cyclone", "to": "deslime_cyclone", "stream": "S15_spiral_cyclone_of",
     "label": "overflow"},
    {"from": "spirals", "to": "fines_product", "stream": "S16_spiral_conc", "kind": "product",
     "label": "concentrate"},
    {"from": "spirals", "to": "tables", "stream": "S17_spiral_middling", "label": "middling"},
    {"from": "spirals", "to": "tails_thickener", "stream": "S18_spiral_tailing", "kind": "tailings"},
    {"from": "tables", "to": "fines_product", "stream": "S20_table_conc", "kind": "product"},
    {"from": "tables", "to": "spiral_cyclone", "stream": "S17_spiral_middling", "kind": "recycle",
     "label": "middling recycle"},
    {"from": "tables", "to": "tails_thickener", "stream": "S21_table_tailing", "kind": "tailings"},
    {"from": "deslime_cyclone", "to": "whims", "stream": "S22_deslime_uf", "label": "underflow"},
    {"from": "deslime_cyclone", "to": "tails_thickener", "stream": "S23_deslime_of", "kind": "tailings",
     "label": "ultrafine slime"},
    {"from": "whims", "to": "pellet_product", "stream": "S27_pellet_fines", "kind": "product",
     "label": "magnetics"},
    {"from": "whims", "to": "tails_thickener", "stream": "S24_whims_tail", "kind": "tailings"},
    {"from": "tails_thickener", "to": "water", "stream": "S30_tails_overflow", "kind": "water",
     "label": "overflow"},
    {"from": "water", "to": "scrubber", "stream": "S30_tails_overflow", "kind": "water",
     "label": "recycle water"},
]


class OverviewService:
    def overview(self, plant_id: str, hour: float | None = None) -> dict:
        h = current_hour() if hour is None else float(hour)
        t = get_historian().truth(plant_id, h)
        meta = get_plant_service().get(plant_id)
        k, u = t["kpis"], t["units"]
        cards = []
        for a in AREAS:
            vals = {}
            for un in a["units"]:
                info = u.get(un, {})
                for key in a["kpi"]:
                    if key in info and key not in vals:
                        vals[key] = info[key]
            cards.append({**a, "values": vals,
                          "power_kw": round(sum(u.get(un, {}).get("power_kw", 0.0) or 0.0 for un in a["units"]), 1)})
        return {"plant_id": plant_id, "name": meta["name"], "description": meta["description"],
                "product_spec": meta["product"], "nameplate_tph": meta["nameplate_tph"],
                "timestamp": t["timestamp"], "hour": round(h, 3), "kpis": k, "areas": cards,
                "power": t["power"], "water": t["water"], "economics": t["economics"], "events": t["events"]}

    def flowsheet(self, plant_id: str, hour: float | None = None) -> dict:
        h = current_hour() if hour is None else float(hour)
        sim = get_simulation_service().run_plant(plant_id)
        streams = sim["streams"]
        edges = []
        for e in FLOWSHEET_EDGES:
            s = streams.get(e["stream"], {})
            edges.append({**e, "solids_tph": s.get("solids_tph"), "fe_pct": s.get("fe_pct"),
                          "sio2_pct": s.get("sio2_pct"), "al2o3_pct": s.get("al2o3_pct"), "p80_um": s.get("p80_um"),
                          "solids_pct": s.get("solids_pct")})
        nodes = []
        for n in FLOWSHEET_NODES:
            key = {"crushing": "secondary_crusher", "trommel": "scrubber_trommel",
                   "classifier": "spiral_classifier", "tables": "shaking_tables",
                   "water": "water_recovery", "lump_product": "lump_jig",
                   "fines_product": "spirals", "pellet_product": "whims",
                   "rom": "primary_crusher"}.get(n["id"], n["id"])
            nodes.append({**n, "unit": sim["units"].get(key, {})})
        return {"plant_id": plant_id, "hour": round(h, 3), "nodes": nodes, "edges": edges,
                "kpis": sim["kpis"], "sankey": sim["sankey"], "streams": streams}

    def shift_performance(self, plant_id: str, shifts: int = 6) -> dict:
        hist = get_historian()
        end = current_hour()
        rows = []
        for i in range(shifts):
            start = whole_hour(end - (i + 1) * 8)
            series = hist.kpi_series(plant_id, ["saleable_tph", "lump_fe_pct", "lump_al2o3_pct",
                                                "fines_fe_pct", "fe_recovery_pct", "energy_kwh_t",
                                                "margin_usd_h"],
                                     start_h=start, end_h=start + 8, step_h=1.0)
            def avg(key):  # noqa: ANN001, ANN202
                v = [x for x in series[key] if x is not None]
                return round(float(np.mean(v)), 3) if v else None
            rows.append({"shift": f"-{i + 1}", "start_hour": round(start, 1),
                         "saleable_tph": avg("saleable_tph"), "lump_fe_pct": avg("lump_fe_pct"),
                         "lump_al2o3_pct": avg("lump_al2o3_pct"), "fines_fe_pct": avg("fines_fe_pct"),
                         "fe_recovery_pct": avg("fe_recovery_pct"),
                         "energy_kwh_t": avg("energy_kwh_t"), "margin_usd_h": avg("margin_usd_h"),
                         "tonnes": round((avg("saleable_tph") or 0) * 8, 1)})
        return {"plant_id": plant_id, "shifts": list(reversed(rows))}


_service: OverviewService | None = None


def get_overview_service() -> OverviewService:
    global _service
    if _service is None:
        _service = OverviewService()
    return _service
