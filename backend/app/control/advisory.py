"""Control-room advisory: pairing analysis, loop readiness and operator guidance."""
from __future__ import annotations

import numpy as np

from app.control.identification import CV_BY_KEY, MV_BY_KEY


def pairing_analysis(ident: dict) -> dict:
    """Relative-gain-array pairing recommendation and interaction diagnosis."""
    rga = np.array(ident["rga_matrix"], dtype=float) if ident.get("rga_matrix") else np.zeros((0, 0))
    cvs, mvs = ident["cv_keys"], ident["mv_keys"]
    rows = []
    for i, cv in enumerate(cvs):
        if rga.size == 0:
            continue
        j = int(np.argmax(np.abs(rga[i])))
        lam = float(rga[i, j])
        quality = ("good" if 0.7 <= lam <= 1.4 else "workable" if 0.4 <= lam <= 2.5 else "poor")
        rows.append({"cv": cv, "cv_label": CV_BY_KEY[cv]["label"], "mv": mvs[j], "mv_label": MV_BY_KEY[mvs[j]]["label"],
                     "relative_gain": round(lam, 3), "pairing_quality": quality,
                     "gain": ident["gain_matrix"][i][j],
                     "interaction_index": round(float(np.sum(np.abs(rga[i])) - abs(lam)), 3)})
    cond = ident.get("condition_number", 0.0)
    return {"pairings": rows, "condition_number": cond,
            "conditioning": "well conditioned" if cond < 50 else ("moderately ill-conditioned" if cond < 500
                                                                  else "ill-conditioned — use MPC, not SISO loops"),
            "note": "Relative gains near 1 indicate a clean single-loop pairing; values far from 1 mean the "
                    "variables interact and should be handled by the multivariable controller."}


def readiness(tag_health: dict[str, str] | None = None, ident: dict | None = None) -> dict:
    """Is the plant ready for closed-loop supervisory control?

    A gravity plant is instrument-poor, so this gate matters more here than on a flotation
    circuit: without a working on-belt analyser and a jig bed-pressure transmitter the controller
    is steering on model output alone, which is an advisory duty and not a closed-loop one.
    """
    required = {
        "101_WIC_001": "ROM weightometer",
        "101_AI_002": "On-belt Fe / Al2O3 analyser (ROM)",
        "201_SIC_010": "Scrubber drum speed",
        "201_FIC_011": "Scrubber water flow",
        "201_JI_012": "Scrubber motor power",
        "301_DIC_020": "Lump jig bed pressure (cut-density proxy)",
        "301_FIC_021": "Lump jig hutch water",
        "302_AIC_024": "Lump product analyser (Fe)",
        "302_AIC_025": "Lump product analyser (Al2O3)",
        "401_FIC_030": "Classifier dilution water",
        "401_DI_032": "Classifier overflow density",
        "601_PIC_050": "Spiral cyclone manifold pressure",
        "601_DIC_051": "Spiral feed density",
        "701_AIC_064": "Sinter fines analyser",
        "801_JIC_071": "WHIMS field current",
        "801_DI_073": "WHIMS feed density",
        "901_LIC_083": "Tailings thickener bed level",
    }
    health = tag_health or {}
    items = []
    for tag, label in required.items():
        st = health.get(tag, "good")
        items.append({"tag": tag, "label": label, "status": st,
                      "ready": st in ("good", "fair"),
                      "impact": "blocks closed loop" if st == "bad" else "—"})
    ready = all(i["ready"] for i in items)
    score = 100.0 * sum(i["ready"] for i in items) / max(len(items), 1)
    return {"ready_for_closed_loop": ready, "readiness_score_pct": round(score, 1), "instruments": items,
            "model_condition_number": (ident or {}).get("condition_number"),
            "recommendation": ("Closed loop permitted." if ready else
                               "Run in advisory mode until the flagged instruments are repaired.")}


def operator_guidance(constraints: list[dict], kpis: dict, solution: dict | None = None) -> list[dict]:
    """Plain-language actions, ordered by constraint priority then benefit."""
    out: list[dict] = []
    for c in sorted(constraints, key=lambda x: (x["priority"], x.get("margin_pct") or 0)):
        if c.get("margin_pct") is None or c["margin_pct"] >= 8:
            continue
        action = _action_for(c["key"], c["status"])
        out.append({"priority": c["priority"], "constraint": c["label"], "status": c["status"],
                    "value": c["value"], "limit": c["limit"], "unit": c["unit"], "action": action})
    if solution:
        for mv, delta in solution["moves"].items():
            if abs(delta) > 1e-6:
                spec = MV_BY_KEY[mv]
                out.append({"priority": 6, "constraint": "MPC move", "status": "advisory",
                            "value": solution["u_next"][mv], "limit": spec["hi"], "unit": spec["unit"],
                            "action": f"{spec['label']}: move {delta:+.3g} {spec['unit']} "
                                      f"to {solution['u_next'][mv]:.4g} {spec['unit']}"})
    return out


def _action_for(key: str, status: str) -> str:
    table = {
        "lump_al2o3": "Lift scrubber duty — drum speed and water — and raise the trommel spray rate; "
                      "if that is exhausted, tighten the lump jig cut density.",
        "lump_fe": "Tighten the lump jig cut density (raise it) or deepen the bed; check the hutch-water balance.",
        "lump_sio2": "Raise the jig cut density; verify the trommel is not carrying fines into the lump.",
        "lump_yield": "Loosen the lump jig cut density or lower the trommel cut size.",
        "fines_fe": "Move the spiral concentrate splitter inward and check the table cut.",
        "fines_al2o3": "Increase spiral wash water and classifier dilution to reject slimes.",
        "pellet_fe": "Raise the WHIMS field or reduce the WHIMS loading; check the desliming cut.",
        "fe_recovery": "Loosen the jig cuts and move the spiral middling splitter outward; check the "
                       "shaking-table loading.",
        "primary_power": "Open the primary CSS or reduce ROM feed.",
        "secondary_power": "Open the secondary CSS or reduce the recirculating load.",
        "tertiary_power": "Open the tertiary CSS — the recrush loop is carrying too much.",
        "scrubber_power": "Reduce drum speed or feed rate; check for a packed charge.",
        "screen_loading": "Reduce ROM feed or open the secondary CSS to cut the circulating load.",
        "recrush_circulating_load": "Close the tertiary CSS below the trommel aperture so the recrush "
                                    "product reports forward instead of recirculating.",
        "spiral_load": "Bring more spiral starts online or divert feed; the band is widening.",
        "table_load": "Bring more decks online or reduce the spiral middling split.",
        "whims_load": "Reduce the desliming-cyclone underflow to the WHIMS, or bring another unit online.",
        "jig_bed_looseness": "Trim hutch water and stroke to bring the bed back into its stratifying window.",
        "lump_jig_loading": "Reduce ROM feed or raise the trommel cut size to lighten the jig.",
        "fines_jig_loading": "Reduce the fines-screen aperture so less coarse sand reports to the jig.",
        "classifier_loading": "Reduce dilution water or bring another classifier online.",
        "spiral_cyclone_pressure": "Open or close cyclones to bring the manifold pressure into range.",
        "deslime_cyclone_pressure": "Open or close desliming cyclones — the WHIMS cut size is drifting.",
        "scrubber_residence": "Reduce scrubber water or feed rate to lengthen the residence time.",
        "clay_removal": "Raise drum speed; check lifter wear and the charge level.",
        "fresh_water": "Raise the pond reclaim fraction and trim wash water at the spirals and tables.",
        "tails_overflow_tss": "Increase tailings flocculant; check the bed level.",
        "tails_uf_solids": "Reduce underflow pumping or raise flocculant.",
        "tails_rake_torque": "Drop the tailings bed: increase underflow pumping.",
        "slimes_loss": "Coarsen the desliming cut so more of the fine hematite reaches the WHIMS.",
        "energy": "Open the crusher settings where product size allows; the gravity circuit itself is cheap.",
        "mass_yield": "Loosen the jig cuts and the spiral middling splitter.",
        "tailings_fe": "Check the spiral splitter positions and the shaking-table cut — iron is "
                       "leaving in the middlings.",
    }
    base = table.get(key, "Review the unit and the associated regulatory loops.")
    return ("URGENT: " + base) if status == "alarm" else base
