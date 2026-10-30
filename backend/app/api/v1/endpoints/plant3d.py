"""Plant 3-D model endpoints.

The model is served separately from its state, because the model is large and static while the
state is small and changes every cycle. A viewer fetches ``/model`` once and ``/state`` on a
timer.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.plant3d.bindings import asset_detail, state_frame
from app.plant3d.geometry import clash_check, gltf_manifest, scene_graph
from app.plant3d.importers import IMPORT_FORMATS, import_spec, match_nodes, solve_registration
from app.plant3d.model import BOOKMARKS, LEVELS, OVERLAYS
from app.services.plant_service import get_plant_service
from app.services.simulation_service import get_simulation_service

router = APIRouter()


def _check(plant_id: str) -> None:
    if plant_id not in get_plant_service().ids():
        raise HTTPException(status_code=404, detail=f"Unknown plant '{plant_id}'")


@router.get("/model", summary="Full 3-D scene graph of the plant")
def model(plant_id: str = Query("IX-OB-01"),
          level: str | None = Query(None, description="Filter to one level, e.g. L02"),
          area: str | None = Query(None, description="Filter to one area, e.g. A500"),
          include_structures: bool = Query(True)) -> dict[str, Any]:
    _check(plant_id)
    sg = scene_graph()
    nodes = sg["nodes"]
    if not include_structures:
        nodes = [n for n in nodes if n["kind"] == "equipment"]
    if level:
        nodes = [n for n in nodes if n["kind"] != "equipment" or n["level"] == level]
    if area:
        nodes = [n for n in nodes if n["area"] == area]
    keep = {n["node_id"] for n in nodes}
    sg = {**sg, "nodes": nodes,
          "routes": [r for r in sg["routes"] if r["from_asset"] in keep and r["to_asset"] in keep],
          "filter": {"level": level, "area": area, "include_structures": include_structures}}
    sg["plant_id"] = plant_id
    return sg


@router.get("/state", summary="Live visual state for the 3-D model")
def state(plant_id: str = Query("IX-OB-01"),
          overlay: str = Query("status", description="status | duty | power | throughput | fe | solids | none"),
          operating: str | None = Query(None, description="Reserved; set-point overrides use POST /simulation/run")
          ) -> dict[str, Any]:
    _check(plant_id)
    if overlay not in {o["id"] for o in OVERLAYS}:
        raise HTTPException(status_code=400, detail=f"Unknown overlay '{overlay}'")
    res = get_simulation_service().run_plant(plant_id)
    out = state_frame(res, overlay=overlay)
    out["plant_id"] = plant_id
    out["runtime_ms"] = res.get("runtime_ms")
    return out


@router.get("/asset/{asset_id}", summary="Drill-down on one piece of equipment")
def asset(asset_id: str, plant_id: str = Query("IX-OB-01")) -> dict[str, Any]:
    _check(plant_id)
    res = get_simulation_service().run_plant(plant_id)
    d = asset_detail(asset_id, res)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset '{asset_id}'")
    d["plant_id"] = plant_id
    return d


@router.get("/levels", summary="Elevation bands, areas, bookmarks and overlays")
def levels() -> dict[str, Any]:
    sg = scene_graph()
    counts: dict[str, int] = {}
    for n in sg["nodes"]:
        if n["kind"] == "equipment":
            counts[n["level"]] = counts.get(n["level"], 0) + 1
    return {"levels": [{**lv, "equipment": counts.get(lv["level_id"], 0)} for lv in LEVELS],
            "areas": sg["areas"], "bookmarks": BOOKMARKS, "overlays": OVERLAYS,
            "bounds": sg["bounds"], "counts": sg["counts"]}


@router.get("/clash", summary="Layout clash and clearance check")
def clash(clearance_m: float = Query(0.5, ge=0.0, le=5.0),
          include_structures: bool = Query(False)) -> dict[str, Any]:
    return clash_check(clearance_m=clearance_m, include_structures=include_structures)


@router.get("/gltf-manifest", summary="glTF 2.0-shaped node manifest for CAD/BIM round-tripping")
def gltf() -> dict[str, Any]:
    return gltf_manifest()


@router.get("/import-spec", summary="What the site must supply to use its own 3-D model")
def spec() -> dict[str, Any]:
    return import_spec()


@router.get("/import-formats", summary="Supported 3-D geometry formats")
def formats() -> dict[str, Any]:
    return {"formats": IMPORT_FORMATS}


@router.post("/import/match", summary="Match imported geometry node names to plant tags")
def match(payload: dict = Body(..., examples=[{"node_names": ["301-JG-001", "SCRUBBER_DRUM", "602-MS-001"]}])
          ) -> dict[str, Any]:
    names = payload.get("node_names") or []
    if not isinstance(names, list) or not names:
        raise HTTPException(status_code=400, detail="Supply a non-empty 'node_names' list.")
    return match_nodes([str(n) for n in names][:5000],
                       min_score=float(payload.get("min_score", 0.34)))


@router.post("/import/register", summary="Solve the CAD-to-plant-grid transform from control points")
def register(payload: dict = Body(..., examples=[{"pairs": [
        {"source": [0, 0, 0], "target": [10, 0, 5]},
        {"source": [10, 0, 0], "target": [20, 0, 5]},
        {"source": [0, 0, 10], "target": [10, 0, 15]}]}])) -> dict[str, Any]:
    pairs = payload.get("pairs") or []
    out = solve_registration(pairs)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "Registration failed."))
    return out
