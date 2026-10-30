"""Plant 3D model — scene graph, routing, clash detection and glTF-shaped export.

Everything here is derived from ``model.ASSETS``. The browser receives a scene graph of
primitives with transforms and builds meshes from it, so the plant layout lives in one place
and the viewer stays generic.
"""
from __future__ import annotations

import math
from typing import Any

from app.plant3d.model import (ARCHETYPES, AREAS, ASSETS, BOOKMARKS, LEVELS, OVERLAYS, STRUCTURES,
                               asset_index)

#: Stream families, used to colour and size the routes between assets.
STREAM_KIND = {
    "ore": {"colour": "#a1887f", "radius_m": 0.45, "style": "conveyor"},
    "slurry": {"colour": "#78909c", "radius_m": 0.32, "style": "pipe"},
    "product": {"colour": "#f9a825", "radius_m": 0.40, "style": "conveyor"},
    "tails": {"colour": "#6d4c41", "radius_m": 0.36, "style": "pipe"},
    "water": {"colour": "#29b6f6", "radius_m": 0.30, "style": "pipe"},
}

#: Which family each stream belongs to. Anything unlisted is treated as slurry.
STREAM_FAMILY = {
    "S01_rom": "ore", "S02_primary_product": "ore", "S03_screen_oversize": "ore",
    "S04_screen_undersize": "ore", "S05_scrubbed": "ore", "S06_lumps": "ore",
    "S08_lump_ore": "product", "S09a_lump_jig_floats": "ore", "S09b_fines_jig_floats": "ore",
    "S10_tertiary_product": "ore", "S10b_recrush_oversize": "ore", "S10c_recrush_fine": "slurry",
    "S19_ore_fines": "product", "S27_pellet_fines": "product",
    "S24_whims_tail": "tails", "S28_tailings": "tails", "S29_tails_underflow": "tails",
    "S30_tails_overflow": "water", "S18_spiral_tailing": "tails", "S21_table_tailing": "tails",
    "S23_deslime_of": "tails",
}


# ---------------------------------------------------------------------------------- footprints
def footprint(asset: dict[str, Any]) -> tuple[float, float, float]:
    """Axis-aligned extent (dx, dy, dz) in metres for an asset, from its archetype dimensions."""
    d, t = asset["dims"], asset["type"]
    if t in ("jaw_crusher",):
        return d["width_m"], d["height_m"], d["length_m"]
    if t in ("cone_crusher",):
        return d["diameter_m"], d["height_m"], d["diameter_m"]
    if t in ("screen_deck",):
        return d["length_m"], d["height_m"], d["width_m"]
    if t in ("scrubber_drum", "trommel"):
        return d["length_m"], d["diameter_m"], d["diameter_m"]
    if t == "jig_bank":
        return d["n_cells"] * d["cell_width_m"], d["height_m"], d["cell_length_m"]
    if t == "screw_classifier":
        return d["length_m"], d["length_m"] * math.sin(math.radians(d["incline_deg"])), d["width_m"]
    if t == "cyclone_cluster":
        return 2 * d["radius_m"] + 1.0, d["height_m"], 2 * d["radius_m"] + 1.0
    if t == "spiral_bank":
        rows = max(1, round(d["n_starts"] / 12))
        return rows * 1.6, d["height_m"], 12 * d["diameter_m"] * 0.55
    if t == "table_bank":
        cols = max(1, round(d["n_decks"] / 4))
        return cols * (d["deck_length_m"] + 0.6), 1.6, 4 * (d["deck_width_m"] + 0.5)
    if t == "whims_carousel":
        return d["n_units"] * (d["diameter_m"] + 1.2), d["height_m"], d["diameter_m"] + 1.2
    if t == "thickener":
        return d["diameter_m"], d["side_depth_m"] + 3.0, d["diameter_m"]
    if t == "tank":
        return d["diameter_m"], d["height_m"], d["diameter_m"]
    if t == "pump":
        return d["length_m"], d["height_m"], d["height_m"] * 0.9
    if t == "conveyor":
        return d["length_m"], 1.4, d["width_m"] + 0.8
    if t == "stockpile":
        return 2 * d["base_radius_m"], d["height_m"], 2 * d["base_radius_m"]
    if t == "bin":
        return d["top_m"], d["height_m"], d["top_m"]
    if t in ("building", "platform"):
        return d["length_m"], d.get("height_m", d.get("thickness_m", 0.4)), d["width_m"]
    return 3.0, 3.0, 3.0


def aabb(asset: dict[str, Any]) -> dict[str, list[float]]:
    dx, dy, dz = footprint(asset)
    p = asset["position"]
    base_at_y = asset["type"] in ("stockpile", "tank", "thickener", "building", "pump", "bin")
    y0 = p["y"] if base_at_y else p["y"] - dy / 2
    return {"min": [p["x"] - dx / 2, y0, p["z"] - dz / 2],
            "max": [p["x"] + dx / 2, y0 + dy, p["z"] + dz / 2]}


# ---------------------------------------------------------------------------------- routing
def _port(asset: dict[str, Any], out: bool) -> list[float]:
    """Connection point on an asset: discharge low on the east face, feed high on the west face."""
    dx, dy, dz = footprint(asset)
    p = asset["position"]
    base_at_y = asset["type"] in ("stockpile", "tank", "thickener", "building", "pump", "bin")
    y0 = p["y"] if base_at_y else p["y"] - dy / 2
    return [p["x"] + (dx / 2 if out else -dx / 2), y0 + (0.25 if out else 0.82) * dy, p["z"]]


def routes() -> list[dict[str, Any]]:
    """Build one route per stream that has both a source and a destination asset.

    The path is an L in plan with a vertical drop or lift, which is how material actually
    travels in a plant: along a conveyor or launder, then down a chute or up a pump column.
    """
    idx = asset_index()
    src: dict[str, str] = {}
    dst: dict[str, list[str]] = {}
    for a in ASSETS:
        for s in a["streams_out"]:
            src.setdefault(s, a["asset_id"])
        for s in a["streams_in"]:
            dst.setdefault(s, []).append(a["asset_id"])
    out: list[dict[str, Any]] = []
    for stream, s_id in sorted(src.items()):
        for d_id in dst.get(stream, []):
            if d_id == s_id:
                continue
            a, b = idx[s_id], idx[d_id]
            p0, p1 = _port(a, True), _port(b, False)
            lift = p1[1] > p0[1] + 1.0
            mid_y = max(p0[1], p1[1]) + 1.2 if lift else p0[1]
            path = [p0,
                    [p0[0] + (p1[0] - p0[0]) * 0.25, mid_y, p0[2]],
                    [p0[0] + (p1[0] - p0[0]) * 0.72, mid_y, p1[2]],
                    p1]
            fam = STREAM_FAMILY.get(stream, "slurry")
            out.append({"route_id": f"{stream}|{s_id}->{d_id}", "stream": stream,
                        "from_asset": s_id, "to_asset": d_id, "family": fam,
                        "colour": STREAM_KIND[fam]["colour"], "radius_m": STREAM_KIND[fam]["radius_m"],
                        "style": STREAM_KIND[fam]["style"], "pumped": bool(lift),
                        "path": [[round(v, 3) for v in pt] for pt in path],
                        "length_m": round(sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)), 2)})
    return out


# ---------------------------------------------------------------------------------- scene graph
def scene_graph() -> dict[str, Any]:
    """The complete, viewer-agnostic description of the plant model."""
    nodes = []
    for a in ASSETS:
        box = aabb(a)
        nodes.append({
            "node_id": a["asset_id"], "tag": a["tag"], "name": a["name"], "kind": "equipment",
            "archetype": a["type"], "primitive": ARCHETYPES[a["type"]]["primitive"],
            "area": a["area"], "area_name": AREAS[a["area"]]["name"], "level": a["level"],
            "colour": AREAS[a["area"]]["colour"], "criticality": a["criticality"],
            "position": a["position"], "rotation_deg": a["rotation_deg"], "dims": a["dims"],
            "aabb": box, "unit_key": a["unit_key"], "power_key": a["power_key"],
            "streams_in": a["streams_in"], "streams_out": a["streams_out"],
            "datasheet": a["datasheet"], "bindings": a["bindings"],
        })
    for s in STRUCTURES:
        nodes.append({
            "node_id": s["structure_id"], "tag": "", "name": s["name"], "kind": "structure",
            "archetype": s["type"], "primitive": ARCHETYPES[s["type"]]["primitive"],
            "area": s["area"], "area_name": AREAS[s["area"]]["name"],
            "level": "", "colour": "#546e7a", "criticality": "D",
            "position": s["position"], "rotation_deg": 0.0, "dims": s["dims"],
            "transparent": bool(s.get("transparent")), "aabb": None,
            "unit_key": None, "power_key": None, "streams_in": [], "streams_out": [],
            "datasheet": {}, "bindings": [],
        })
    rs = routes()
    eq = [n for n in nodes if n["kind"] == "equipment"]
    lo = [min(n["aabb"]["min"][i] for n in eq) for i in range(3)]
    hi = [max(n["aabb"]["max"][i] for n in eq) for i in range(3)]
    return {
        "schema": "obdt.plant3d/1.0",
        "units": "metres", "up_axis": "Y",
        "coordinate_note": "+x east along the process axis, +y up from plant datum, +z north.",
        "nodes": nodes, "routes": rs,
        "levels": LEVELS, "areas": AREAS, "bookmarks": BOOKMARKS, "overlays": OVERLAYS,
        "archetypes": ARCHETYPES,
        "bounds": {"min": [round(v, 2) for v in lo], "max": [round(v, 2) for v in hi],
                   "size": [round(hi[i] - lo[i], 2) for i in range(3)],
                   "centre": [round((hi[i] + lo[i]) / 2, 2) for i in range(3)]},
        "counts": {"equipment": len(eq), "structures": len(nodes) - len(eq), "routes": len(rs),
                   "tagged": sum(1 for n in eq if n["tag"]),
                   "bound_to_twin": sum(1 for n in eq if n["unit_key"])},
    }


# ---------------------------------------------------------------------------------- clash check
def clash_check(clearance_m: float = 0.5, include_structures: bool = False) -> dict[str, Any]:
    """Axis-aligned overlap test between assets, with a required clearance.

    This is a layout sanity check, not a substitute for a CAD clash run on real geometry. Its
    purpose is to catch the case where a model has been edited and two items now occupy the
    same space, which otherwise shows up as a confusing picture rather than as an error.
    """
    items = [{"id": a["asset_id"], "name": a["name"], "tag": a["tag"], "box": aabb(a)} for a in ASSETS]
    if include_structures:
        for s in STRUCTURES:
            fake = {"type": s["type"], "dims": s["dims"], "position": s["position"]}
            items.append({"id": s["structure_id"], "name": s["name"], "tag": "", "box": aabb(fake)})
    hits = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i]["box"], items[j]["box"]
            ov = [min(a["max"][k], b["max"][k]) - max(a["min"][k], b["min"][k]) + clearance_m
                  for k in range(3)]
            if all(v > 0 for v in ov):
                hits.append({"a": items[i]["id"], "a_name": items[i]["name"], "a_tag": items[i]["tag"],
                             "b": items[j]["id"], "b_name": items[j]["name"], "b_tag": items[j]["tag"],
                             "overlap_m": [round(v - clearance_m, 3) for v in ov],
                             "severity": "clash" if min(ov) > clearance_m else "clearance"})
    return {"clearance_m": clearance_m, "checked": len(items),
            "pairs_tested": len(items) * (len(items) - 1) // 2,
            "clashes": [h for h in hits if h["severity"] == "clash"],
            "clearance_warnings": [h for h in hits if h["severity"] == "clearance"],
            "clean": not hits,
            "method": "Axis-aligned bounding-box overlap with a required clearance envelope."}


# ---------------------------------------------------------------------------------- glTF export
_PRIM_TO_GLTF = {"shell": "BOX", "slab": "BOX", "wedge": "BOX", "inclined_box": "BOX",
                 "cone_body": "CONE", "cone_pile": "CONE", "hopper": "CONE", "tank_cone": "CONE",
                 "drum": "CYLINDER", "cylinder": "CYLINDER", "carousel": "CYLINDER",
                 "cyclone_ring": "GROUP", "cell_bank": "GROUP", "deck_bank": "GROUP",
                 "helix_bank": "GROUP", "pump_set": "GROUP", "belt": "BOX", "inclined_trough": "BOX"}


def gltf_manifest() -> dict[str, Any]:
    """A glTF 2.0-shaped node hierarchy carrying the plant tags in ``extras``.

    This is the interchange format for round-tripping the asset register to and from a CAD or
    BIM package: the node names and ``extras.tag`` values are what a site's 3-D model is matched
    against. It deliberately carries no mesh buffers — the geometry of a real plant comes from
    the site's own model, not from us. A viewer that wants renderable geometry reads
    ``scene_graph`` instead, or loads the site's .glb alongside it.
    """
    nodes, names = [], []
    for a in ASSETS:
        p, (dx, dy, dz) = a["position"], footprint(a)
        nodes.append({
            "name": a["tag"] or a["asset_id"],
            "translation": [round(p["x"], 3), round(p["y"], 3), round(p["z"], 3)],
            "rotation_euler_deg": [0.0, a["rotation_deg"], 0.0],
            "scale": [round(dx, 3), round(dy, 3), round(dz, 3)],
            "extras": {"asset_id": a["asset_id"], "tag": a["tag"], "name": a["name"],
                       "area": a["area"], "level": a["level"], "archetype": a["type"],
                       "placeholder": _PRIM_TO_GLTF.get(ARCHETYPES[a["type"]]["primitive"], "BOX"),
                       "unit_key": a["unit_key"], "criticality": a["criticality"],
                       "datasheet": a["datasheet"]},
        })
        names.append(a["tag"] or a["asset_id"])
    return {
        "asset": {"version": "2.0", "generator": "OBDT plant3d manifest",
                  "copyright": "Extractmet Private Limited"},
        "scene": 0,
        "scenes": [{"name": "Industry-X ore beneficiation plant", "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": [], "buffers": [], "bufferViews": [], "accessors": [],
        "extras": {"schema": "obdt.plant3d.gltf-manifest/1.0", "units": "metres", "up_axis": "Y",
                   "node_names": names,
                   "note": "Node hierarchy and tag metadata only. Mesh buffers are intentionally "
                           "empty: real geometry is supplied by the site's own CAD or scan model "
                           "and matched to these nodes by name or tag."},
    }
