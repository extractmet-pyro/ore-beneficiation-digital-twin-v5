"""Plant 3D model — bringing in the site's own geometry.

The asset register in ``model.py`` is a *schematic* plant: positions and dimensions good
enough to navigate, reason about and bind live data to, built from the flowsheet and the
equipment list. Most sites that ask for a 3-D digital twin already have something better —
a 3-D CAD model from the EPC, an as-built laser scan, or a BIM/IFC model — and the honest
answer is that we should use theirs rather than redraw it.

This module is the bridge. It does three things, and is explicit about what it does not do:

1. **Declares what we can ingest** and what each format gives us (``IMPORT_FORMATS``).
2. **Matches** the imported model's node or object names to plant tags, so that geometry the
   site already owns becomes clickable, live equipment in the twin (``match_nodes``).
3. **Registers** the imported coordinate system onto the plant grid from control points
   (``solve_registration``), because every CAD model arrives on its own origin and units.

It does not author geometry, repair a broken CAD model, or convert between native CAD
formats. Those are the site's or its EPC's job, and pretending otherwise is how 3-D twin
projects fail.
"""
from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

IMPORT_FORMATS: list[dict[str, Any]] = [
    {"format": "glTF 2.0 / GLB", "extensions": [".gltf", ".glb"], "support": "native",
     "carries": "Meshes, materials, node hierarchy, node names, extras metadata",
     "note": "The preferred delivery format. Renders directly in the operator desk with no "
             "conversion step. Most CAD and BIM tools export it, directly or through Blender."},
    {"format": "IFC 2x3 / IFC 4", "extensions": [".ifc"], "support": "metadata + converted mesh",
     "carries": "Object hierarchy, GUIDs, type and property sets, placement",
     "note": "Property sets usually hold the plant tag, which makes tag matching reliable. "
             "Geometry is converted to glTF for display; the IFC stays the source of truth."},
    {"format": "RVM / ATTRIB (AVEVA PDMS, E3D)", "extensions": [".rvm", ".att", ".attrib"],
     "support": "converted", "carries": "Primitive solids, hierarchy, attributes including tags",
     "note": "Common on Indian EPC projects. Converted to glTF; attributes are preserved as "
             "node extras and are the best tag source we see in practice."},
    {"format": "STEP / IGES", "extensions": [".step", ".stp", ".iges"], "support": "converted",
     "carries": "Exact B-rep solids, assembly tree",
     "note": "Accurate but heavy and usually untagged. Tessellated and decimated on import; "
             "expect to map tags by assembly path rather than by name."},
    {"format": "E57 / LAS / LAZ point cloud", "extensions": [".e57", ".las", ".laz"],
     "support": "reference layer",
     "carries": "As-built point geometry, intensity, scan positions",
     "note": "Shown as a reference layer behind the model: this is what the plant actually "
             "looks like today, including every undocumented modification. Not clickable "
             "equipment unless segmented first."},
    {"format": "OBJ / FBX", "extensions": [".obj", ".fbx"], "support": "converted",
     "carries": "Meshes, materials, object names",
     "note": "Accepted, but object names are often meaningless after an export chain, so "
             "budget for manual tag mapping."},
    {"format": "DWG / DXF (2-D)", "extensions": [".dwg", ".dxf"], "support": "reference only",
     "carries": "General arrangement drawings, plan grids, elevations",
     "note": "Used to place and check the schematic model when no 3-D model exists. Not a "
             "3-D source."},
]

#: What the site has to provide for an imported model to become a working twin layer.
IMPORT_REQUIREMENTS: list[str] = [
    "A 3-D model or scan in one of the formats above, with the site's plant grid origin stated.",
    "Units and up-axis declared (metres and +Z up is the usual CAD convention; the twin uses "
    "metres and +Y up and converts on import).",
    "At least three control points whose coordinates are known in both the CAD model and the "
    "plant survey grid, for registration.",
    "A tag list for the equipment that is to be live, and ideally the tag written into the node "
    "name or an IFC property set.",
    "Confirmation of which model revision is as-built, because an EPC design model and the "
    "plant as it stands are rarely the same thing.",
]

#: Tag patterns seen in practice. Matching is tried in order, most specific first.
TAG_PATTERNS = [
    re.compile(r"\b(\d{3})[-_ ]?([A-Z]{2})[-_ ]?(\d{3,4})\b"),   # 301-JG-001
    re.compile(r"\b([A-Z]{2,4})[-_ ]?(\d{3,5})\b"),               # JG-0301
]


def _candidates(name: str) -> list[str]:
    s = (name or "").upper().replace(".", "-")
    out = []
    for pat in TAG_PATTERNS:
        for m in pat.finditer(s):
            out.append("-".join(g for g in m.groups() if g))
    return out


def _similar(a: str, b: str) -> float:
    """Cheap token overlap score, used when no tag can be parsed from a node name."""
    ta = set(re.split(r"[^A-Z0-9]+", (a or "").upper())) - {""}
    tb = set(re.split(r"[^A-Z0-9]+", (b or "").upper())) - {""}
    return 0.0 if not ta or not tb else len(ta & tb) / len(ta | tb)


def match_nodes(node_names: list[str], *, assets: list[dict[str, Any]] | None = None,
                min_score: float = 0.34) -> dict[str, Any]:
    """Attach imported geometry node names to plant assets.

    Returns an explicit three-way split — matched, ambiguous and unmatched — because the one
    thing an import must never do is silently bind the wrong pump to the wrong motor.
    """
    from app.plant3d.model import ASSETS
    ast = assets or ASSETS
    by_tag = {a["tag"].upper(): a for a in ast if a["tag"]}
    matched, ambiguous, unmatched = [], [], []
    used: dict[str, list[str]] = {}
    for n in node_names:
        hits = [by_tag[c] for c in _candidates(n) if c in by_tag]
        if len(hits) == 1:
            a = hits[0]
            matched.append({"node": n, "asset_id": a["asset_id"], "tag": a["tag"],
                            "name": a["name"], "method": "tag", "score": 1.0})
            used.setdefault(a["asset_id"], []).append(n)
            continue
        if len(hits) > 1:
            ambiguous.append({"node": n, "candidates": [a["asset_id"] for a in hits], "method": "tag"})
            continue
        scored = sorted(((_similar(n, a["name"]), a) for a in ast), key=lambda t: -t[0])
        best, second = scored[0], (scored[1] if len(scored) > 1 else (0.0, None))
        if best[0] >= min_score and best[0] - second[0] >= 0.08:
            matched.append({"node": n, "asset_id": best[1]["asset_id"], "tag": best[1]["tag"],
                            "name": best[1]["name"], "method": "name", "score": round(best[0], 3)})
            used.setdefault(best[1]["asset_id"], []).append(n)
        elif best[0] >= min_score:
            ambiguous.append({"node": n, "candidates": [best[1]["asset_id"], second[1]["asset_id"]],
                              "method": "name"})
        else:
            unmatched.append({"node": n, "best_guess": best[1]["asset_id"],
                              "score": round(best[0], 3)})
    duplicates = {k: v for k, v in used.items() if len(v) > 1}
    covered = len(used)
    return {
        "nodes_in": len(node_names), "matched": matched, "ambiguous": ambiguous,
        "unmatched": unmatched, "duplicate_bindings": duplicates,
        "assets_total": len(ast), "assets_covered": covered,
        "coverage_pct": round(100 * covered / max(len(ast), 1), 1),
        "assets_missing": [a["asset_id"] for a in ast if a["asset_id"] not in used],
        "ready": not ambiguous and not duplicates and covered >= 0.8 * len(ast),
        "note": "Ambiguous and unmatched nodes are listed for an engineer to resolve. Nothing is "
                "bound on a guess; an unresolved node stays as inert geometry.",
    }


def solve_registration(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Least-squares similarity transform (uniform scale, rotation, translation) from control points.

    ``pairs`` is a list of ``{"source": [x,y,z], "target": [x,y,z]}`` — the same physical point
    in the imported model's coordinates and in the plant grid. Three non-collinear points are
    the minimum; more points reduce the residual and expose a bad pick.

    Implemented as the closed-form Umeyama solution, which is what every survey package uses.
    """
    if len(pairs) < 3:
        return {"ok": False, "error": "At least three control-point pairs are required."}
    P = np.array([p["source"] for p in pairs], dtype=float)
    Q = np.array([p["target"] for p in pairs], dtype=float)
    if P.shape != Q.shape or P.shape[1] != 3:
        return {"ok": False, "error": "Each control point needs three source and three target coordinates."}
    mp, mq = P.mean(axis=0), Q.mean(axis=0)
    X, Y = P - mp, Q - mq
    S = X.T @ Y / len(P)
    U, D, Vt = np.linalg.svd(S)
    d = np.sign(np.linalg.det(U @ Vt))
    W = np.diag([1.0, 1.0, d])
    R = (U @ W @ Vt).T
    var = (X ** 2).sum() / len(P)
    scale = float((D * np.array([1.0, 1.0, d])).sum() / max(var, 1e-12))
    t = mq - scale * (R @ mp)
    fitted = (scale * (R @ P.T).T) + t
    res = np.linalg.norm(fitted - Q, axis=1)
    yaw = math.degrees(math.atan2(R[0, 2], R[0, 0]))
    return {
        "ok": True, "scale": round(scale, 6),
        "rotation_matrix": [[round(v, 6) for v in row] for row in R.tolist()],
        "translation_m": [round(v, 4) for v in t.tolist()],
        "yaw_deg": round(yaw, 3),
        "residual_m": {"rms": round(float(np.sqrt((res ** 2).mean())), 4),
                       "max": round(float(res.max()), 4),
                       "per_point": [round(float(v), 4) for v in res.tolist()]},
        "quality": ("good" if float(res.max()) < 0.25 else
                    "acceptable" if float(res.max()) < 1.0 else "poor"),
        "method": "Umeyama closed-form similarity transform (uniform scale, rotation, translation).",
        "note": "A maximum residual above about one metre usually means a mis-picked control "
                "point or a model on a different grid, not a bad solve.",
    }


def import_spec() -> dict[str, Any]:
    """The whole answer to 'can you do this on our real 3-D model?', in one payload."""
    return {
        "answer": "Yes. The twin is built so that the site's own 3-D model carries the geometry "
                  "and the twin carries the behaviour. Where no 3-D model exists, the schematic "
                  "model shipped with the twin is used until one does.",
        "formats": IMPORT_FORMATS,
        "requirements": IMPORT_REQUIREMENTS,
        "workflow": [
            "Site supplies the model and three or more control points on the plant grid.",
            "Model is converted to glTF where needed, decimated for browser delivery, and split "
            "by area and level so a single floor can be loaded on its own.",
            "Registration is solved from the control points and the residual is reported; "
            "anything above about a metre is referred back before the model is accepted.",
            "Node names and property sets are matched to plant tags; ambiguous and unmatched "
            "nodes are listed for an engineer to resolve rather than bound on a guess.",
            "Matched nodes inherit the live bindings already defined for that asset, so the "
            "imported geometry becomes clickable equipment with live state.",
            "Coverage is reported as a percentage of tagged assets bound. Below eighty per cent "
            "the model is treated as a backdrop rather than as the twin surface.",
        ],
        "limits": [
            "A scan or CAD model is a snapshot. It does not update itself when the plant changes, "
            "and the twin cannot tell you that it has gone stale.",
            "Point clouds are not equipment. They are a reference layer unless the site has had "
            "them segmented and tagged.",
            "Very large models have to be decimated for a browser. Visual fidelity below about "
            "25 mm is lost; that is a display limit, not a modelling one.",
            "Geometry does not make a twin. An untagged model with no live bindings is a "
            "viewer, and should be bought as one.",
        ],
    }
