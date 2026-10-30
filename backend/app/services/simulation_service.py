"""Steady-state simulation, what-if studies, sensitivity and scenario comparison."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

import numpy as np

from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.services.plant_service import get_plant_service
from app.twin.circuit import solve
from app.twin.constraints import evaluate_all, penalty
from app.twin.psd import GEO_MEAN_UM, SIZES_UM, Stream

_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 600


def _key(*parts) -> str:  # noqa: ANN002
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def stream_payload(s: Stream, name: str) -> dict:
    """Serialise a stream for the desk (summary + size distribution + liberation spectrum)."""
    sf = s.size_frac
    passing = np.cumsum(sf[::-1])[::-1]
    return {"name": name, **s.summary(),
            "psd": {"size_um": [float(x) for x in SIZES_UM], "retained_pct": [round(100 * float(v), 4) for v in sf],
                    "passing_pct": [round(100 * float(v), 4) for v in passing],
                    "geo_mean_um": [round(float(x), 3) for x in GEO_MEAN_UM]},
            "liberation_spectrum": [round(100 * float(v), 4) for v in s.m.sum(axis=0)]}


class SimulationService:
    def run(self, flowsheet: FlowsheetConfig, ore: OreConfig, operating: OperatingConfig,
            economics: EconomicsConfig, *, include_streams: bool = True,
            constraint_overrides: dict | None = None) -> dict:
        k = _key(flowsheet.model_dump(), ore.model_dump(), operating.model_dump(), economics.model_dump(),
                 include_streams)
        if k in _CACHE:
            _CACHE.move_to_end(k)
            return _CACHE[k]
        res = solve(flowsheet, ore, operating, economics)
        out = {"kpis": res["kpis"], "units": res["units"], "power": res["power"], "costs": res["costs"],
               "water": res["water"], "economics": res["economics"], "balance": res["balance"],
               "liberation": res["liberation"], "warnings": res["warnings"], "runtime_ms": res["solve_ms"],
               "constraints": evaluate_all(res, constraint_overrides),
               "constraint_penalty": round(penalty(res, constraint_overrides), 2)}
        if include_streams:
            out["streams"] = {n: stream_payload(s, n) for n, s in res["streams"].items()}
            out["sankey"] = self._sankey(res)
        _CACHE[k] = out
        _CACHE.move_to_end(k)
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
        return out

    def run_plant(self, plant_id: str, overrides: dict | None = None, **kw) -> dict:
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        ov = overrides or {}
        if ov.get("flowsheet"):
            fs = FlowsheetConfig(**{**fs.model_dump(), **ov["flowsheet"]})
        if ov.get("ore"):
            ore = OreConfig(**{**ore.model_dump(), **ov["ore"]})
        if ov.get("operating"):
            op = OperatingConfig(**{**op.model_dump(), **ov["operating"]})
        if ov.get("economics"):
            ec = EconomicsConfig(**{**ec.model_dump(), **ov["economics"]})
        return {"plant_id": plant_id, **self.run(fs, ore, op, ec, **kw)}

    # ---- studies -------------------------------------------------------------------------------
    def sensitivity(self, plant_id: str, variable: str, values: list[float], kpis: list[str],
                    group: str = "operating") -> dict:
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        rows = []
        for v in values:
            cfgs = {"flowsheet": fs, "ore": ore, "operating": op, "economics": ec}
            data = cfgs[group].model_dump()
            if variable not in data:
                from app.core.exceptions import ValidationFailure
                raise ValidationFailure(f"'{variable}' is not a field of {group}")
            data[variable] = round(v) if isinstance(data[variable], int) else float(v)
            cls = {"flowsheet": FlowsheetConfig, "ore": OreConfig, "operating": OperatingConfig,
                   "economics": EconomicsConfig}[group]
            cfgs[group] = cls(**data)
            r = self.run(cfgs["flowsheet"], cfgs["ore"], cfgs["operating"], cfgs["economics"], include_streams=False)
            rows.append({"value": float(v), **{k: r["kpis"].get(k) for k in kpis},
                         "constraint_penalty": r["constraint_penalty"]})
        return {"plant_id": plant_id, "group": group, "variable": variable, "kpis": kpis, "rows": rows}

    def tornado(self, plant_id: str, kpi: str = "margin_usd_h", delta_pct: float = 8.0) -> dict:
        """Which inputs move the KPI most — one-at-a-time +/- perturbation."""
        from app.control.identification import MVS
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        base = self.run(fs, ore, op, ec, include_streams=False)["kpis"][kpi]
        rows = []
        targets = [("operating", m["key"]) for m in MVS] + [
            ("ore", "fe_head_pct"), ("ore", "sio2_head_pct"), ("ore", "liberation_d50_um"),
            ("ore", "bond_wi_kwh_t"), ("ore", "axb"), ("economics", "iron_ore_index_usd_dmt")]
        for group, key in targets:
            cfg = {"operating": op, "ore": ore, "economics": ec}[group]
            data = cfg.model_dump()
            v0 = data[key]
            out = {}
            for sign in (-1, 1):
                d = dict(data)
                nv = v0 * (1 + sign * delta_pct / 100.0)
                d[key] = round(nv) if isinstance(v0, int) else float(nv)
                cls = {"operating": OperatingConfig, "ore": OreConfig, "economics": EconomicsConfig}[group]
                cfgs = {"flowsheet": fs, "ore": ore, "operating": op, "economics": ec}
                cfgs[group] = cls(**d)
                try:
                    r = self.run(cfgs["flowsheet"], cfgs["ore"], cfgs["operating"], cfgs["economics"],
                                 include_streams=False)
                    out["low" if sign < 0 else "high"] = r["kpis"][kpi]
                except Exception:  # noqa: BLE001
                    out["low" if sign < 0 else "high"] = base
            rows.append({"group": group, "variable": key, "base": base, "low": out["low"], "high": out["high"],
                         "span": round(abs(out["high"] - out["low"]), 4)})
        rows.sort(key=lambda r: -r["span"])
        return {"plant_id": plant_id, "kpi": kpi, "base": base, "delta_pct": delta_pct, "rows": rows}

    def compare(self, plant_id: str, scenarios: list[dict]) -> dict:
        """Run several named override sets side by side."""
        out = []
        for sc in scenarios:
            r = self.run_plant(plant_id, sc.get("overrides"), include_streams=False)
            out.append({"name": sc.get("name", "scenario"), "overrides": sc.get("overrides", {}),
                        "kpis": r["kpis"], "constraint_penalty": r["constraint_penalty"],
                        "violations": [c["label"] for c in r["constraints"] if c["violated"]]})
        return {"plant_id": plant_id, "scenarios": out}

    def grade_recovery(self, plant_id: str, cut_range: tuple[float, float] = (3.4, 4.8),
                       points: int = 9) -> dict:
        """Grade-recovery envelope traced by the lump jig cut density.

        On a gravity plant the cut density is the grade-recovery knob, and the curve it traces is
        not the familiar flotation one: material rejected from the lump jig does not go to the
        tailings, it goes to the fines circuit and is recovered there at a different grade. The
        trade-off is therefore between *products*, which is why the curve carries the lump and
        fines tonnages alongside the grades.
        """
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        rows = []
        for c in np.linspace(*cut_range, points):
            d = op.model_dump()
            d["lump_jig_cut_sg"] = float(c)
            r = self.run(fs, ore, OperatingConfig(**d), ec, include_streams=False)
            k = r["kpis"]
            rows.append({"cut_sg": round(float(c), 3), "fe_recovery_pct": k["fe_recovery_pct"],
                         "lump_fe_pct": k["lump_fe_pct"], "lump_al2o3_pct": k["lump_al2o3_pct"],
                         "lump_tph": k["lump_tph"], "fines_fe_pct": k["fines_fe_pct"],
                         "fines_tph": k["fines_tph"], "product_fe_pct": k["product_fe_pct"],
                         "mass_yield_pct": k["mass_yield_pct"], "tailings_fe_pct": k["tailings_fe_pct"],
                         "margin_usd_h": k["margin_usd_h"]})
        return {"plant_id": plant_id, "curve": rows, "driver": "lump_jig_cut_sg",
                "note": "Traced by the lump jig cut density. Material rejected from the lump is not lost — "
                        "it is recrushed and recovered in the fines circuit, so the trade-off is between "
                        "products rather than between grade and recovery."}

    def washability(self, plant_id: str) -> dict:
        """Float-and-sink analysis of the plant feed and of each product.

        The washability curve is the first thing a gravity metallurgist asks for: it says how much
        of the ore *could* be separated at a given density, and therefore how much of the gap
        between the twin and the plant is the machine rather than the ore.
        """
        fs, ore, op, ec = get_plant_service().configs(plant_id)
        res = solve(fs, ore, op, ec)
        out = {}
        for label, key in (("ROM feed", "S01_rom"), ("Jig feed (lumps)", "S06_lumps"),
                           ("Lump ore", "S08_lump_ore"), ("Spiral feed", "S14_spiral_cyclone_uf"),
                           ("Sinter fines", "S19_ore_fines"), ("Tailings", "S28_tailings")):
            st = res["streams"].get(key)
            if st is None:
                continue
            d = st.sg_distribution()
            cum_mass, cum_fe, run_m, run_fe = [], [], 0.0, 0.0
            for m, f in zip(reversed(d["mass_pct"]), reversed(d["fe_pct"])):
                run_fe += m * f
                run_m += m
                cum_mass.append(round(run_m, 3))
                cum_fe.append(round(run_fe / max(run_m, 1e-9), 3))
            out[label] = {"sg_mid": d["sg_mid"], "mass_pct": [round(x, 3) for x in d["mass_pct"]],
                          "fe_pct": [round(x, 3) for x in d["fe_pct"]],
                          "cum_float_mass_pct": list(reversed(cum_mass)),
                          "cum_float_fe_pct": list(reversed(cum_fe))}
        return {"plant_id": plant_id, "streams": out,
                "concentration_criterion": round(float(
                    (5.15 - 1.0) / (2.65 - 1.0)), 3),
                "note": "Mass and grade by particle density. A concentration criterion above 2.5 means "
                        "the separation is easy down to about 75 um, which is what makes a jig-spiral-table "
                        "flowsheet viable on this ore."}

    @staticmethod
    def _sankey(res: dict) -> dict:
        s = res["streams"]

        def t(n):  # noqa: ANN001, ANN202
            st = s.get(n)
            return round(st.solids_tph, 2) if st is not None else 0.0

        nodes = ["ROM", "Crushing", "Scrubber", "Lump jig", "Lump ore", "Recrush", "Classifier",
                 "Fines jig", "Spirals", "Tables", "Sinter fines", "Desliming", "WHIMS",
                 "Pellet-plant feed", "Tailings"]
        links = [
            {"source": "ROM", "target": "Crushing", "value": t("S01_rom")},
            {"source": "Crushing", "target": "Scrubber", "value": t("S04_screen_undersize")},
            {"source": "Scrubber", "target": "Lump jig", "value": t("S06_lumps")},
            {"source": "Scrubber", "target": "Classifier", "value": t("S07_scrubber_fines")},
            {"source": "Lump jig", "target": "Lump ore", "value": t("S08_lump_ore")},
            {"source": "Lump jig", "target": "Recrush", "value": t("S09_jig_floats")},
            {"source": "Recrush", "target": "Classifier", "value": t("S10_tertiary_product")},
            {"source": "Classifier", "target": "Fines jig", "value": t("S11_classifier_sand")},
            {"source": "Classifier", "target": "Desliming", "value": t("S12_classifier_overflow")},
            {"source": "Fines jig", "target": "Sinter fines", "value": t("S13_fines_jig_conc")},
            {"source": "Fines jig", "target": "Spirals", "value": t("S14_spiral_cyclone_uf")},
            {"source": "Spirals", "target": "Sinter fines", "value": t("S16_spiral_conc")},
            {"source": "Spirals", "target": "Tables", "value": t("S17_spiral_middling")},
            {"source": "Spirals", "target": "Tailings", "value": t("S18_spiral_tailing")},
            {"source": "Tables", "target": "Sinter fines", "value": t("S20_table_conc")},
            {"source": "Tables", "target": "Tailings", "value": t("S21_table_tailing")},
            {"source": "Desliming", "target": "WHIMS", "value": t("S22_deslime_uf")},
            {"source": "Desliming", "target": "Tailings", "value": t("S23_deslime_of")},
            {"source": "WHIMS", "target": "Pellet-plant feed", "value": t("S27_pellet_fines")},
            {"source": "WHIMS", "target": "Tailings", "value": t("S24_whims_tail")},
        ]
        return {"nodes": nodes, "links": links, "unit": "t/h (dry solids)"}


_service: SimulationService | None = None


def get_simulation_service() -> SimulationService:
    global _service
    if _service is None:
        _service = SimulationService()
    return _service
