"""Diagnostics: mass-balance closure, data reconciliation and fault detection."""
from __future__ import annotations

import numpy as np

from app.services.historian_service import EVENTS, REPLAY_HOURS, get_historian
from app.services.live_service import current_hour
from app.services.plant_service import TAGS
from app.services.simulation_service import get_simulation_service


class DiagnosticsService:
    """Balances, reconciliation and fault detection.

    The residual sweep reads every PV and CV tag across a window of replay hours - about a
    thousand historian lookups - which is the slowest thing on the diagnostics page. It is
    deterministic within a replay hour, so the result is memoised on the integer hour and
    recomputed when the replay moves on.
    """

    def __init__(self) -> None:
        self._residuals: dict[tuple, dict] = {}

    # ---- balances ------------------------------------------------------------------------------
    def balance(self, plant_id: str) -> dict:
        """Solids, iron, alumina and water balance across the plant boundary.

        Three products leave this plant rather than one, so the balance has to be stated
        product-by-product; a single concentrate line would hide where the alumina actually goes.
        """
        sim = get_simulation_service().run_plant(plant_id)
        s = sim["streams"]
        feed = s["S01_rom"]
        products = [s["S08_lump_ore"], s["S19_ore_fines"], s["S27_pellet_fines"]]
        tails = s["S28_tailings"]
        rows = []
        for label, comp in (("Solids", "solids_tph"), ("Iron units", "fe_tph")):
            f = feed[comp]
            out = sum(p[comp] for p in products) + tails[comp]
            rows.append({"component": label, "in_tph": round(f, 3), "out_tph": round(out, 3),
                         "closure_pct": round(100 * out / max(f, 1e-9), 3),
                         "error_tph": round(out - f, 4)})
        for label, key in (("Silica", "sio2_pct"), ("Alumina", "al2o3_pct")):
            f = feed["solids_tph"] * feed[key] / 100.0
            out = sum(p["solids_tph"] * p[key] / 100.0 for p in products) + tails["solids_tph"] * tails[key] / 100.0
            rows.append({"component": label, "in_tph": round(f, 3), "out_tph": round(out, 3),
                         "closure_pct": round(100 * out / max(f, 1e-9), 3),
                         "error_tph": round(out - f, 4)})
        w = sim["water"]
        rows.append({"component": "Water", "in_m3_h": round(w["fresh_make_up_m3_h"] + w["recycled_m3_h"], 2),
                     "out_m3_h": round(w["losses_m3_h"] + w["thickener_overflow_m3_h"], 2),
                     "closure_pct": None, "error_m3_h": None})
        return {"plant_id": plant_id, "rows": rows, "node_check": self._node_check(sim),
                "products": [{"product": n, "tph": round(p["solids_tph"], 2), "fe_pct": p["fe_pct"],
                              "al2o3_pct": p["al2o3_pct"], "sio2_pct": p["sio2_pct"]}
                             for n, p in (("Lump ore", products[0]), ("Sinter fines", products[1]),
                                          ("Pellet-plant feed", products[2]), ("Tailings", tails))],
                "note": "Solids and iron close by construction; the residual is the recycle-convergence "
                        "error. Silica and alumina close to a few per cent because the secondary minerals "
                        "are re-partitioned by a first-order bias model at each separator rather than "
                        "being tracked as their own state axes. The same table run on reconciled plant "
                        "data is where real losses appear."}

    @staticmethod
    def _node_check(sim: dict) -> list[dict]:
        s = sim["streams"]
        nodes = [
            ("Lump jig", ["S06_lumps", "S10b_recrush_oversize"], ["S08_lump_ore", "S09a_lump_jig_floats"]),
            ("Screw classifier", ["S07_scrubber_fines", "S10c_recrush_fine"],
             ["S11_classifier_sand", "S12_classifier_overflow"]),
            ("Spirals", ["S14_spiral_cyclone_uf"],
             ["S16_spiral_conc", "S17_spiral_middling", "S18_spiral_tailing"]),
            ("Shaking tables", ["S17_spiral_middling"],
             ["S20_table_conc", "S21_table_tailing", "S25_table_middling"]),
            ("Tertiary crusher", ["S09a_lump_jig_floats", "S09b_fines_jig_floats"],
             ["S10_tertiary_product"]),
            ("Recrush screen", ["S10_tertiary_product"], ["S10b_recrush_oversize", "S10c_recrush_fine"]),
            ("Desliming cyclones", ["S12_classifier_overflow", "S15_spiral_cyclone_of"],
             ["S22_deslime_uf", "S23_deslime_of"]),
            ("WHIMS", ["S22_deslime_uf"], ["S27_pellet_fines", "S24_whims_tail"]),
        ]
        out = []
        for name, ins, outs in nodes:
            avail = [x for x in ins if x in s] and [x for x in outs if x in s]
            if not avail:
                continue
            i = sum(s[x]["solids_tph"] for x in ins if x in s)
            o = sum(s[x]["solids_tph"] for x in outs if x in s)
            fi = sum(s[x]["fe_tph"] for x in ins if x in s)
            fo = sum(s[x]["fe_tph"] for x in outs if x in s)
            out.append({"node": name, "in_tph": round(i, 2), "out_tph": round(o, 2),
                        "solids_closure_pct": round(100 * o / max(i, 1e-9), 3),
                        "fe_closure_pct": round(100 * fo / max(fi, 1e-9), 3)})
        return out

    # ---- reconciliation ------------------------------------------------------------------------
    def reconcile(self, plant_id: str, hour: float | None = None) -> dict:
        """Weighted least-squares reconciliation of the three-product node (feed / concentrate / tails)."""
        h = current_hour() if hour is None else float(hour)
        t = get_historian().truth(plant_id, h)
        rng = np.random.default_rng(int(h * 17) % 9999)
        k = t["kpis"]
        # measured values with realistic assay/flow uncertainty
        meas = {"feed_tph": k["throughput_tph"] * (1 + rng.normal(0, 0.012)),
                "conc_tph": k["saleable_tph"] * (1 + rng.normal(0, 0.02)),
                "tail_tph": (k["throughput_tph"] - k["saleable_tph"]) * (1 + rng.normal(0, 0.02)),
                "feed_fe": t["ore"]["fe_head_pct"] * (1 + rng.normal(0, 0.015)),
                "conc_fe": k["product_fe_pct"] * (1 + rng.normal(0, 0.006)),
                "tail_fe": k["tailings_fe_pct"] * (1 + rng.normal(0, 0.02))}
        sigma = {"feed_tph": 0.012, "conc_tph": 0.02, "tail_tph": 0.02, "feed_fe": 0.015, "conc_fe": 0.006,
                 "tail_fe": 0.02}
        x = np.array([meas[k_] for k_ in meas])
        w = np.array([1.0 / (sigma[k_] * max(abs(meas[k_]), 1e-6)) ** 2 for k_ in meas])

        def residuals(z):
            f, c, tl, ff, cf, tf = z
            return np.array([f - c - tl, f * ff - c * cf - tl * tf])

        # Lagrangian WLS: minimise (z-x)' W (z-x) s.t. r(z)=0, solved by successive linearisation
        z = x.copy()
        for _ in range(12):
            r = residuals(z)
            f, c, tl, ff, cf, tf = z
            J = np.array([[1.0, -1.0, -1.0, 0.0, 0.0, 0.0],
                          [ff, -cf, -tf, f, -c, -tl]])
            Winv = np.diag(1.0 / w)
            S = J @ Winv @ J.T
            lam = np.linalg.solve(S + 1e-9 * np.eye(2), r + J @ (x - z))
            z = x - Winv @ J.T @ lam
        names = list(meas)
        adj = [{"variable": n, "measured": round(float(x[i]), 4), "reconciled": round(float(z[i]), 4),
                "adjustment": round(float(z[i] - x[i]), 4),
                "adjustment_sigma": round(float((z[i] - x[i]) / (sigma[n] * max(abs(x[i]), 1e-6))), 2),
                "suspect": bool(abs((z[i] - x[i]) / (sigma[n] * max(abs(x[i]), 1e-6))) > 2.0)}
               for i, n in enumerate(names)]
        recovery = 100 * z[1] * z[4] / max(z[0] * z[3], 1e-9)
        return {"plant_id": plant_id, "hour": round(h, 3), "variables": adj,
                "reconciled_recovery_pct": round(float(recovery), 2),
                "raw_recovery_pct": round(float(100 * x[1] * x[4] / max(x[0] * x[3], 1e-9)), 2),
                "gross_error": bool(any(a["suspect"] for a in adj)),
                "method": "Weighted least squares with mass and iron-unit constraints (successive linearisation)."}

    # ---- fault detection -----------------------------------------------------------------------
    def residuals(self, plant_id: str, hours: float = 48.0, step_h: float = 1.0) -> dict:
        hist = get_historian()
        end = current_hour()
        key = (plant_id, float(hours), float(step_h), int(end))
        cached = self._residuals.get(key)
        if cached is not None:
            return cached
        tags = [t["tag"] for t in TAGS if t["type"] in ("PV", "CV")]
        rows = {t: [] for t in tags}
        hrs = []
        for i in range(int(hours / step_h)):
            # whole hours: these are hourly residuals, and a fractional hour misses the
            # replay cache and rebuilds a snapshot that already exists
            h = float(int(end - hours + i * step_h) % REPLAY_HOURS)
            hrs.append(round(h, 2))
            for t in tags:
                m = hist.tag_value(plant_id, t, h, "measurement")
                mo = hist.tag_value(plant_id, t, h, "model")
                rows[t].append(None if m is None or mo in (None, 0) else round(100 * (m - mo) / mo, 3))
        stats = []
        for t in tags:
            v = np.array([x for x in rows[t] if x is not None], dtype=float)
            if v.size < 4:
                continue
            stats.append({"tag": t, "mean_pct": round(float(v.mean()), 3), "std_pct": round(float(v.std()), 3),
                          "max_abs_pct": round(float(np.abs(v).max()), 3),
                          "status": "fault" if abs(v.mean()) > 8 or np.abs(v).max() > 20 else
                                    ("watch" if abs(v.mean()) > 3 else "normal")})
        out = {"plant_id": plant_id, "hours": hrs, "residual_pct": rows,
               "summary": sorted(stats, key=lambda s: -abs(s["mean_pct"])),
               "events": [e for e in EVENTS]}
        self._residuals = {key: out}          # one hour's worth is all that is ever wanted
        return out

    def event_catalogue(self) -> list[dict]:
        return get_historian().events()


_service: DiagnosticsService | None = None


def get_diagnostics_service() -> DiagnosticsService:
    global _service
    if _service is None:
        _service = DiagnosticsService()
    return _service
