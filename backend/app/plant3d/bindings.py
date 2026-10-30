"""Plant 3D model — binding live twin state onto the geometry.

A 3-D model of a plant is a picture. A 3-D *digital twin* is a picture whose colour, fill,
rotation and labelling are driven by the current state of the process. This module does that
binding: it takes a solved twin result (or a live snapshot) and produces a **state frame** —
one entry per asset and one per route — that the viewer applies to the scene it already holds.

Model and state are deliberately separate calls. The model is large and changes when the plant
is modified; the state is small and changes every cycle.
"""
from __future__ import annotations

from typing import Any

from app.plant3d.geometry import routes, scene_graph
from app.plant3d.model import ASSETS, OVERLAYS

STATUS_RANK = {"normal": 0, "caution": 1, "alarm": 2, "offline": 3}


def _dig(result: dict[str, Any], source: str, key: str):
    """Resolve a binding key against a solved twin result. Returns None when absent."""
    try:
        if source == "unit":
            unit, field = key.split(".", 1)
            return result.get("units", {}).get(unit, {}).get(field)
        if source == "stream":
            stream, field = key.split(".", 1)
            return result.get("streams", {}).get(stream, {}).get(field)
        if source == "kpi":
            return result.get("kpis", {}).get(key)
        if source == "constraint":
            for c in result.get("constraints", []):
                if c.get("key") == key:
                    return c
            return None
    except Exception:  # noqa: BLE001 — a missing binding must never break the picture
        return None
    return None


def _norm(v, lo, hi):
    if v is None:
        return None
    try:
        f = (float(v) - float(lo)) / max(float(hi) - float(lo), 1e-9)
    except (TypeError, ValueError):
        return None
    return round(min(max(f, 0.0), 1.0), 4)


def _asset_throughput(a: dict[str, Any], result: dict[str, Any]) -> float | None:
    unit = result.get("units", {}).get(a["unit_key"] or "", {})
    if "feed_tph" in unit:
        return round(float(unit["feed_tph"]), 2)
    streams = result.get("streams", {})
    ins = [streams[s]["solids_tph"] for s in a["streams_in"] if s in streams]
    if ins:
        return round(float(sum(ins)), 2)
    outs = [streams[s]["solids_tph"] for s in a["streams_out"] if s in streams]
    return round(float(sum(outs)), 2) if outs else None


#: Fields that stand in for "how hard is this machine working", in order of preference.
DUTY_FIELDS = ("power_utilisation_pct", "loading_fraction", "load_fraction", "area_utilisation_pct",
               "rake_torque_pct", "screening_efficiency_pct", "bed_looseness")


def _shared_power(power_key: str | None) -> bool:
    """True when a power-balance entry covers several assets (pumps, screens), so dividing it
    by one machine's drive rating would be meaningless."""
    if not power_key:
        return True
    return sum(1 for a in ASSETS if a["power_key"] == power_key) > 1


def _duty_pct(a: dict[str, Any], result: dict[str, Any], chan: dict[str, Any]) -> float | None:
    """Equipment duty as a percentage of its limit, from whichever field the unit reports."""
    if chan.get("duty") is not None:
        return round(100 * chan["duty"], 1)
    unit = result.get("units", {}).get(a["unit_key"] or "", {})
    for f in DUTY_FIELDS:
        if f in unit:
            v = float(unit[f])
            return round(v if f.endswith("_pct") else 100 * v, 1)
    cap = result.get("power", {}).get(a["power_key"] or "")
    ds = a["datasheet"].get("installed_kw") or a["datasheet"].get("drive_kw")
    if cap is not None and ds and not _shared_power(a["power_key"]):
        return round(100 * float(cap) / float(ds), 1)
    return None


def state_frame(result: dict[str, Any], *, overlay: str = "status") -> dict[str, Any]:
    """Build the per-asset and per-route visual state from a solved twin result."""
    power = result.get("power", {})
    streams = result.get("streams", {})
    kpis = result.get("kpis", {})
    cons = {c.get("key"): c for c in result.get("constraints", [])}

    assets_out: list[dict[str, Any]] = []
    for a in ASSETS:
        chan: dict[str, Any] = {}
        status, status_from = "normal", None
        labels: list[dict[str, Any]] = []
        for b in a["bindings"]:
            val = _dig(result, b["source"], b["key"])
            if b["channel"] == "status":
                if isinstance(val, dict):
                    st = val.get("status", "normal")
                    if STATUS_RANK.get(st, 0) > STATUS_RANK.get(status, 0):
                        status, status_from = st, val.get("label")
                continue
            if val is None:
                continue
            if b["channel"] in ("fill", "duty", "rotation"):
                chan[b["channel"]] = _norm(val, b.get("lo", 0), b.get("hi", 1))
            if b["channel"] in ("value", "duty", "fill"):
                labels.append({"key": b["key"].split(".")[-1], "value": round(float(val), 3)})

        kw = power.get(a["power_key"] or "", None)
        tph = _asset_throughput(a, result)
        unit = result.get("units", {}).get(a["unit_key"] or "", {})
        fe = None
        for s in a["streams_out"] or a["streams_in"]:
            if s in streams:
                fe = streams[s].get("fe_pct")
                break
        solids = unit.get("solids_pct") or unit.get("feed_solids_pct")
        duty = _duty_pct(a, result, chan)

        overlay_value = {"none": None, "status": STATUS_RANK.get(status, 0),
                         "duty": duty, "power": kw, "throughput": tph, "fe": fe,
                         "solids": solids}.get(overlay)

        assets_out.append({
            "asset_id": a["asset_id"], "tag": a["tag"], "status": status, "status_from": status_from,
            "channels": chan, "labels": labels[:3], "duty_pct": duty,
            "power_kw": None if kw is None else round(float(kw), 1),
            "throughput_tph": tph, "fe_pct": fe, "solids_pct": solids,
            "overlay_value": overlay_value,
            "in_service": bool(tph is None or tph > 0.01),
        })

    routes_out = []
    for r in routes():
        s = streams.get(r["stream"], {})
        tph = s.get("solids_tph")
        routes_out.append({
            "route_id": r["route_id"], "stream": r["stream"],
            "solids_tph": tph, "fe_pct": s.get("fe_pct"), "solids_pct": s.get("solids_pct"),
            "water_m3_h": s.get("water_m3_h"),
            "flow": _norm(tph, 0, 650) if tph is not None else None,
            "active": bool(tph is not None and tph > 0.01),
        })

    spec = next((o for o in OVERLAYS if o["id"] == overlay), OVERLAYS[0])
    vals = [a["overlay_value"] for a in assets_out if isinstance(a["overlay_value"], (int, float))]
    return {
        "overlay": overlay, "overlay_spec": spec,
        "overlay_range": {"lo": round(min(vals), 3), "hi": round(max(vals), 3)} if vals else None,
        "assets": assets_out, "routes": routes_out,
        "summary": {
            "alarms": [a["asset_id"] for a in assets_out if a["status"] == "alarm"],
            "cautions": [a["asset_id"] for a in assets_out if a["status"] == "caution"],
            "total_power_kw": round(sum(v for v in power.values() if isinstance(v, (int, float))), 1),
            "throughput_tph": kpis.get("throughput_tph"),
            "violated_constraints": [c["label"] for c in cons.values() if c.get("violated")],
        },
    }


def asset_detail(asset_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """Everything the viewer shows when an operator clicks a piece of equipment."""
    a = next((x for x in ASSETS if x["asset_id"] == asset_id), None)
    if a is None:
        return None
    streams = result.get("streams", {})
    node = next(n for n in scene_graph()["nodes"] if n["node_id"] == asset_id)
    frame = next(f for f in state_frame(result)["assets"] if f["asset_id"] == asset_id)
    rel = [{"stream": s, "direction": d, **{k: streams[s].get(k) for k in
            ("solids_tph", "water_m3_h", "solids_pct", "fe_pct", "sio2_pct", "al2o3_pct", "p80_um")}}
           for d, lst in (("in", a["streams_in"]), ("out", a["streams_out"])) for s in lst if s in streams]
    return {
        "asset": {k: a[k] for k in ("asset_id", "tag", "name", "type", "area", "level",
                                    "position", "dims", "datasheet", "criticality")},
        "aabb": node["aabb"], "state": frame,
        "unit_result": result.get("units", {}).get(a["unit_key"] or "", {}),
        "power_kw": frame["power_kw"], "streams": rel,
        "constraints": [c for c in result.get("constraints", [])
                        if c.get("key") in {b["key"] for b in a["bindings"] if b["channel"] == "status"}],
    }
