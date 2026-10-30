"""Per-unit detail pages: operating point, design data and characteristic curves.

Every curve on this page is evaluated with the full flowsheet, not with the unit in isolation, so
what it shows already includes the circuit's recycles. Moving the lump jig cut density changes the
recrush load, which changes the classifier feed, which changes the spiral duty — and the curve
reflects all of it.
"""
from __future__ import annotations

import numpy as np

from app.models.domain import OperatingConfig
from app.services.plant_service import get_plant_service
from app.services.simulation_service import get_simulation_service
from app.twin.gravity import partition_curve, size_window
from app.twin.psd import GEO_MEAN_UM, particle_sg
from app.twin.separation import capture_curve, size_recovery_curve

UNITS = [
    {"id": "primary_crusher", "label": "Primary jaw crusher", "area": "A100", "stream_in": "S01_rom",
     "stream_out": "S02_primary_product", "model": "Whiten classification-breakage + Bond power"},
    {"id": "sizing_screen", "label": "Sizing screen (40 mm)", "area": "A100",
     "stream_in": "S02_primary_product", "stream_out": "S04_screen_undersize",
     "model": "Whiten partition with true-undersize efficiency"},
    {"id": "secondary_crusher", "label": "Secondary cone crusher", "area": "A100",
     "stream_in": "S03_screen_oversize", "stream_out": "S04_screen_undersize",
     "model": "Whiten classification-breakage + Bond power"},
    {"id": "scrubber", "label": "Rotary scrubber", "area": "A200", "stream_in": "S04_screen_undersize",
     "stream_out": "S05_scrubbed",
     "model": "First-order attrition of the clay coating with drum residence time"},
    {"id": "scrubber_trommel", "label": "Scrubber discharge trommel", "area": "A200",
     "stream_in": "S05_scrubbed", "stream_out": "S06_lumps", "model": "Whiten partition curve"},
    {"id": "lump_jig", "label": "Lump jig (Baum / Batac)", "area": "A300", "stream_in": "S06_lumps",
     "stream_out": "S08_lump_ore",
     "model": "Tromp density partition with size-dependent probable error"},
    {"id": "tertiary_crusher", "label": "Tertiary cone crusher (recrush)", "area": "A500",
     "stream_in": "S09_jig_floats", "stream_out": "S10_tertiary_product",
     "model": "Whiten classification-breakage + Bond power"},
    {"id": "recrush_screen", "label": "Recrush closing screen", "area": "A500",
     "stream_in": "S10_tertiary_product", "stream_out": "S10b_recrush_oversize",
     "model": "Whiten partition curve"},
    {"id": "spiral_classifier", "label": "Screw (spiral) classifier", "area": "A400",
     "stream_in": "S07_scrubber_fines", "stream_out": "S11_classifier_sand",
     "model": "Hindered-settling classification with the equal-settling correction for hematite"},
    {"id": "fines_screen", "label": "Fines sizing screen (2 mm)", "area": "A400",
     "stream_in": "S11_classifier_sand", "stream_out": "S14_spiral_cyclone_uf",
     "model": "Whiten partition curve"},
    {"id": "fines_jig", "label": "Fines jig", "area": "A500", "stream_in": "S11_classifier_sand",
     "stream_out": "S13_fines_jig_conc",
     "model": "Tromp density partition with size-dependent probable error"},
    {"id": "spiral_cyclone", "label": "Spiral-feed cyclones", "area": "A600",
     "stream_in": "S14_spiral_cyclone_uf", "stream_out": "S14_spiral_cyclone_uf",
     "model": "Plitt d50c with Whiten efficiency curve"},
    {"id": "spirals", "label": "Spiral concentrators", "area": "A600", "stream_in": "S14_spiral_cyclone_uf",
     "stream_out": "S16_spiral_conc",
     "model": "Flowing-film density separation, three products from two splitters"},
    {"id": "shaking_tables", "label": "Shaking tables", "area": "A700", "stream_in": "S17_spiral_middling",
     "stream_out": "S20_table_conc",
     "model": "Asymmetric-deck density separation, sharpest Ep of the three gravity units"},
    {"id": "deslime_cyclone", "label": "Desliming cyclones", "area": "A800",
     "stream_in": "S12_classifier_overflow", "stream_out": "S22_deslime_uf",
     "model": "Plitt d50c with Whiten efficiency curve"},
    {"id": "whims", "label": "Wet high-intensity magnetic separators", "area": "A800",
     "stream_in": "S22_deslime_uf", "stream_out": "S27_pellet_fines",
     "model": "Magnetic / drag / gravity force balance at the matrix surface"},
    {"id": "tails_thickener", "label": "Tailings thickener", "area": "A900", "stream_in": "S28_tailings",
     "stream_out": "S29_tails_underflow", "model": "Yoshioka solids-flux with flocculant response"},
    {"id": "water_recovery", "label": "Water recovery and recycle", "area": "A900",
     "stream_in": "S30_tails_overflow", "stream_out": "S30_tails_overflow",
     "model": "Plant-boundary water balance with pond reclaim"},
]
UNIT_BY_ID = {u["id"]: u for u in UNITS}


def _bounds(key: str) -> tuple[float, float]:
    """Engineering limits of a set-point, read from the configuration schema."""
    f = OperatingConfig.model_fields[key]
    lo, hi = None, None
    for meta in f.metadata:
        lo = getattr(meta, "ge", None) if getattr(meta, "ge", None) is not None else lo
        hi = getattr(meta, "le", None) if getattr(meta, "le", None) is not None else hi
    return (float(lo) if lo is not None else -1e12, float(hi) if hi is not None else 1e12)


def _span(op: OperatingConfig, key: str, lo_mult: float = 0.7, hi_mult: float = 1.4,
          points: int = 9) -> list[float]:
    """A sweep around the current set-point, clipped to the variable's engineering limits."""
    v0 = float(getattr(op, key))
    lo_lim, hi_lim = _bounds(key)
    lo = max(v0 * lo_mult, lo_lim)
    hi = min(v0 * hi_mult, hi_lim)
    if hi <= lo:
        lo, hi = lo_lim, hi_lim
    return [float(x) for x in np.linspace(lo, hi, points)]


def _range(key: str, lo: float, hi: float, points: int = 9) -> list[float]:
    """An absolute sweep, clipped to the variable's engineering limits."""
    lo_lim, hi_lim = _bounds(key)
    return [float(x) for x in np.linspace(max(lo, lo_lim), min(hi, hi_lim), points)]


class UnitService:
    def list(self) -> list[dict]:
        return UNITS

    def detail(self, plant_id: str, unit_id: str) -> dict:
        if unit_id not in UNIT_BY_ID:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(f"Unknown unit '{unit_id}'")
        sim = get_simulation_service().run_plant(plant_id)
        meta = UNIT_BY_ID[unit_id]
        streams = sim["streams"]
        return {"plant_id": plant_id, **meta, "state": sim["units"].get(unit_id, {}),
                "feed": streams.get(meta["stream_in"]), "product": streams.get(meta["stream_out"]),
                "curves": self.curves(plant_id, unit_id)}

    def curves(self, plant_id: str, unit_id: str) -> dict:  # noqa: C901 — one branch per unit type
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        sim = get_simulation_service().run_plant(plant_id)
        sv = get_simulation_service()
        state = sim["units"].get(unit_id, {})

        if unit_id in ("primary_crusher", "secondary_crusher", "tertiary_crusher"):
            key = {"primary_crusher": "primary_css_mm", "secondary_crusher": "secondary_css_mm",
                   "tertiary_crusher": "tertiary_css_mm"}[unit_id]
            r = sv.sensitivity(plant_id, key, _span(op, key, 0.65, 1.45),
                               ["energy_kwh_t", "lump_yield_pct", "fines_tph", "mass_yield_pct"])
            return {"css_response": r["rows"], "x_label": f"{key.replace('_', ' ')} (mm)"}

        if unit_id == "scrubber":
            r = sv.sensitivity(plant_id, "scrubber_speed_pct_critical",
                               _range("scrubber_speed_pct_critical", 20.0, 40.0),
                               ["lump_al2o3_pct", "lump_fe_pct", "fines_al2o3_pct", "energy_kwh_t"])
            rw = sv.sensitivity(plant_id, "scrubber_water_m3_h",
                                _range("scrubber_water_m3_h", 180.0, 820.0),
                                ["lump_al2o3_pct", "scrubber_clay_removal_pct", "fresh_water_m3_t"])
            return {"speed_response": r["rows"], "water_response": rw["rows"],
                    "x_label": "Drum speed (% critical)",
                    "attrition_curve": self._attrition_curve(state)}

        if unit_id in ("lump_jig", "fines_jig"):
            key = "lump_jig_cut_sg" if unit_id == "lump_jig" else "fines_jig_cut_sg"
            xs = _range(key, 3.3, 4.8)
            outs = (["lump_fe_pct", "lump_al2o3_pct", "lump_yield_pct", "fe_recovery_pct"]
                    if unit_id == "lump_jig" else
                    ["fines_fe_pct", "fines_al2o3_pct", "fines_tph", "fe_recovery_pct"])
            r = sv.sensitivity(plant_id, key, xs, outs)
            ep_key = "ep_at_10mm" if unit_id == "lump_jig" else "ep_at_1mm"
            return {"cut_density_response": r["rows"], "x_label": "Cut density (SG)",
                    "partition_curve": partition_curve(state.get("cut_sg_achieved", 4.0),
                                                       state.get(ep_key, 0.25)),
                    "ep_by_size": self._ep_by_size(unit_id, state),
                    "grade_recovery": sv.grade_recovery(plant_id, points=9)["curve"] if unit_id == "lump_jig" else None}

        if unit_id == "spiral_classifier":
            r = sv.sensitivity(plant_id, "classifier_dilution_water_m3_h",
                               _range("classifier_dilution_water_m3_h", 100.0, 700.0),
                               ["classifier_d50_um", "pellet_fines_tph", "fines_fe_pct", "slimes_to_tailings_pct"])
            return {"dilution_response": r["rows"], "x_label": "Dilution water (m3/h)",
                    "settling_curve": self._settling_curve(state, ore.goethite_share, ore.clay_share)}

        if unit_id == "spirals":
            r = sv.sensitivity(plant_id, "spiral_conc_splitter",
                               _range("spiral_conc_splitter", 0.12, 0.50),
                               ["fines_fe_pct", "fines_tph", "fe_recovery_pct", "tailings_fe_pct"])
            return {"splitter_response": r["rows"], "x_label": "Concentrate splitter (fraction of width)",
                    "partition_curve": partition_curve(state.get("cut_sg_conc", 4.0),
                                                       state.get("ep_at_500um", 0.35)),
                    "size_window": self._size_window(62.0, 2400.0, 1.9, 2.6)}

        if unit_id == "shaking_tables":
            r = sv.sensitivity(plant_id, "table_conc_cut", _range("table_conc_cut", 0.15, 0.60),
                               ["fines_fe_pct", "fines_tph", "fe_recovery_pct", "tailings_fe_pct"])
            return {"cut_response": r["rows"], "x_label": "Concentrate cut (fraction of deck)",
                    "partition_curve": partition_curve(state.get("cut_sg_conc", 4.2),
                                                       state.get("ep_at_200um", 0.15)),
                    "size_window": self._size_window(38.0, 1800.0, 2.2, 2.8)}

        if unit_id == "whims":
            r = sv.sensitivity(plant_id, "whims_field_tesla", _range("whims_field_tesla", 0.55, 1.55),
                               ["pellet_fines_fe_pct", "pellet_fines_tph", "fe_recovery_pct", "tailings_fe_pct"])
            return {"field_response": r["rows"], "x_label": "Field intensity (T)",
                    "capture_curve": capture_curve(state.get("field_tesla", 1.15), state.get("matrix", "expanded_metal"),
                                                   state.get("gap_mm", 4.0), ore.goethite_share,
                                                   state.get("loading_fraction", 1.0)),
                    "size_recovery": size_recovery_curve(state.get("field_tesla", 1.15))}

        if unit_id in ("spiral_cyclone", "deslime_cyclone"):
            key = ("spiral_cyclone_pressure_kpa" if unit_id == "spiral_cyclone"
                   else "deslime_cyclone_pressure_kpa")
            r = sv.sensitivity(plant_id, key, _span(op, key, 0.65, 1.45),
                               ["fines_fe_pct", "pellet_fines_tph", "slimes_to_tailings_pct", "fe_recovery_pct"])
            return {"pressure_response": r["rows"], "x_label": "Manifold pressure (kPa)",
                    "partition_curve": self._cyclone_partition(state)}

        if unit_id in ("sizing_screen", "scrubber_trommel", "fines_screen", "recrush_screen"):
            ap = {"sizing_screen": fs.crushing.sizing_screen_aperture_mm,
                  "scrubber_trommel": op.trommel_aperture_mm,
                  "fines_screen": op.fines_screen_aperture_mm,
                  "recrush_screen": op.trommel_aperture_mm}[unit_id]
            return {"partition_curve": self._screen_partition(ap * 1000.0),
                    "x_label": "Particle size (um)"}

        if unit_id == "tails_thickener":
            return {"flux_curve": self._flux_curve(state), "x_label": "Solids volume fraction"}

        if unit_id == "water_recovery":
            r = sv.sensitivity(plant_id, "reclaim_water_fraction",
                               _range("reclaim_water_fraction", 0.5, 0.94),
                               ["fresh_water_m3_t", "water_recycle_pct", "cost_usd_t"])
            return {"reclaim_response": r["rows"], "x_label": "Pond reclaim fraction"}
        return {}

    # ---- curve builders --------------------------------------------------------------------------
    @staticmethod
    def _ep_by_size(unit_id: str, info: dict) -> list[dict]:
        """How the probable error of a jig degrades with particle size — the reason this plant has
        three different gravity machines instead of one."""
        ep_ref = info.get("ep_at_10mm", 0.2) if unit_id == "lump_jig" else info.get("ep_at_1mm", 0.4)
        d_ref, base = (3200.0, 10_000.0) if unit_id == "lump_jig" else (3200.0, 1_000.0)
        scale = ep_ref / max(0.55 + (d_ref / base) ** 0.80, 1e-6)
        d = GEO_MEAN_UM[(GEO_MEAN_UM > 40.0) & (GEO_MEAN_UM < 90_000.0)]
        return [{"size_um": round(float(x), 1),
                 "ep": round(float(scale * (0.55 + (d_ref / x) ** 0.80)), 4)} for x in d]

    @staticmethod
    def _size_window(lo: float, hi: float, lo_s: float, hi_s: float) -> list[dict]:
        d = GEO_MEAN_UM[(GEO_MEAN_UM > 8.0) & (GEO_MEAN_UM < 12_000.0)]
        w = size_window(lo, hi, lo_s, hi_s)[(GEO_MEAN_UM > 8.0) & (GEO_MEAN_UM < 12_000.0)]
        return [{"size_um": round(float(x), 2), "efficiency_pct": round(float(100 * y), 2)}
                for x, y in zip(d, w)]

    @staticmethod
    def _settling_curve(info: dict, goethite_share: float, clay_share: float) -> list[dict]:
        """Cut size against particle density: the hindered-settling reason a classifier overflow
        is always leaner than its feed."""
        d50 = info.get("d50_quartz_um", 200.0)
        sgs = particle_sg(goethite_share, clay_share)
        return [{"sg": round(float(s), 3),
                 "d50_um": round(float(d50 * np.sqrt((2.65 - 1.0) / max(s - 1.0, 1e-6))), 2)}
                for s in sgs]

    @staticmethod
    def _attrition_curve(info: dict) -> list[dict]:
        """First-order clay detachment against scrubber residence time."""
        k = info.get("scrubbing_index", 0.8) / max(info.get("residence_time_min", 2.0), 1e-6)
        return [{"residence_min": round(float(t), 2), "detached_pct": round(float(100 * (1 - np.exp(-k * t))), 2)}
                for t in np.linspace(0.2, 8.0, 24)]

    @staticmethod
    def _cyclone_partition(info: dict) -> list[dict]:
        d50 = info.get("d50c_um", 60.0)
        d = GEO_MEAN_UM[(GEO_MEAN_UM > 1.0) & (GEO_MEAN_UM < 4000.0)]
        m = 1.9
        mx = np.clip(m * d / max(d50, 1e-6), 0.0, 60.0)
        ec = (np.exp(mx) - 1.0) / (np.exp(mx) + np.exp(m) - 2.0)
        return [{"size_um": round(float(x), 2), "to_underflow_pct": round(float(100 * y), 2)}
                for x, y in zip(d, np.clip(ec, 0.0, 1.0))]

    @staticmethod
    def _screen_partition(aperture_um: float, sharpness: float = 2.8) -> list[dict]:
        d = GEO_MEAN_UM[(GEO_MEAN_UM > aperture_um / 60.0) & (GEO_MEAN_UM < aperture_um * 12.0)]
        p = 1.0 / (1.0 + (aperture_um / np.maximum(d, 1e-6)) ** sharpness)
        return [{"size_um": round(float(x), 2), "to_oversize_pct": round(float(100 * y), 2)}
                for x, y in zip(d, p)]

    @staticmethod
    def _flux_curve(info: dict) -> list[dict]:
        phi = np.linspace(0.02, 0.42, 26)
        v0, n = 0.0022, 4.6
        flux = v0 * (1 - phi) ** n * phi * 3600.0
        return [{"phi": round(float(p), 4), "flux_m_h": round(float(f), 4)} for p, f in zip(phi, flux)]


_service: UnitService | None = None


def get_unit_service() -> UnitService:
    global _service
    if _service is None:
        _service = UnitService()
    return _service
