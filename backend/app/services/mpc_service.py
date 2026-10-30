"""Supervisory MPC service: identification cache, solve, closed-loop study and hand-over."""
from __future__ import annotations

import threading
import time

from app.control.advisory import operator_guidance, pairing_analysis, readiness
from app.control.identification import CVS, MVS, identify, step_response
from app.control.mpc import MPCController, handover_payload
from app.models.domain import OperatingConfig
from app.services.historian_service import get_historian
from app.services.live_service import current_hour
from app.services.plant_service import get_plant_service
from app.services.simulation_service import get_simulation_service
from app.twin.constraints import evaluate_all


class MPCService:
    def __init__(self) -> None:
        self._ident: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ---- model ---------------------------------------------------------------------------------
    def identification(self, plant_id: str, *, refresh: bool = False, mv_keys: list[str] | None = None,
                       cv_keys: list[str] | None = None) -> dict:
        key = f"{plant_id}|{','.join(mv_keys or [])}|{','.join(cv_keys or [])}"
        with self._lock:
            if refresh or key not in self._ident:
                fs, ore, op, ec = get_plant_service().configs(plant_id)
                t0 = time.perf_counter()
                ident = identify(fs, ore, op, ec, mv_keys=mv_keys, cv_keys=cv_keys)
                ident["identified_s"] = round(time.perf_counter() - t0, 2)
                ident["plant_id"] = plant_id
                self._ident[key] = ident
            return self._ident[key]

    def config(self) -> dict:
        return {"mvs": MVS, "cvs": CVS,
                "defaults": {"horizon": 24, "control_horizon": 4, "dt_min": 5.0, "slack_weight": 2500.0},
                "formulation": "Condensed DMC with soft output constraints, move limits and priority-weighted slacks."}

    def step_responses(self, plant_id: str, cv: str, mvs: list[str] | None = None,
                       horizon_min: float = 120.0) -> dict:
        ident = self.identification(plant_id)
        keys = mvs or ident["mv_keys"]
        out = {}
        for m in keys:
            mdl = ident["models"].get(f"{cv}|{m}")
            if mdl is None:
                continue
            out[m] = {"gain": mdl["gain"], "tau_min": mdl["tau_min"], "dead_time_min": mdl["dead_time_min"],
                      "response": step_response(mdl["gain"], mdl["tau_min"], mdl["dead_time_min"], horizon_min)}
        return {"plant_id": plant_id, "cv": cv, "horizon_min": horizon_min, "dt_min": 2.0, "models": out}

    # ---- control -------------------------------------------------------------------------------
    def _controller(self, plant_id: str, tuning: dict | None = None) -> MPCController:
        ident = self.identification(plant_id)
        t = tuning or {}
        return MPCController(ident, horizon=int(t.get("horizon", 24)),
                             control_horizon=int(t.get("control_horizon", 4)),
                             dt_min=float(t.get("dt_min", 5.0)),
                             cv_weights=t.get("cv_weights"), mv_weights=t.get("mv_weights"),
                             targets=t.get("targets"), zones=t.get("zones"),
                             slack_weight=float(t.get("slack_weight", 2500.0)))

    def solve(self, plant_id: str, *, hour: float | None = None, tuning: dict | None = None,
              targets: dict | None = None, mode: str = "advisory") -> dict:
        h = current_hour() if hour is None else float(hour)
        hist = get_historian()
        truth, model = hist.truth(plant_id, h), hist.model(plant_id, h)
        ctrl = self._controller(plant_id, tuning)
        y_now = {c: float(truth["kpis"][c]) for c in ctrl.cv_keys}
        y_model = {c: float(model["kpis"][c]) for c in ctrl.cv_keys}
        u_now = {m: float(truth["mvs"][m]) for m in ctrl.mv_keys}
        t0 = time.perf_counter()
        sol = ctrl.solve(y_now, u_now, y_model=y_model, targets=targets)
        sol["solve_ms"] = round(1000 * (time.perf_counter() - t0), 1)
        sol["plant_id"] = plant_id
        sol["hour"] = round(h, 3)
        sol["measured"] = y_now
        sol["model"] = y_model
        sol["bias"] = {c: round(y_now[c] - y_model[c], 4) for c in ctrl.cv_keys}
        sol["handover"] = handover_payload(sol, mode=mode)
        # what the twin says the proposed move actually delivers at steady state
        sim = get_simulation_service()
        op_over = {"operating": sol["u_next"]}
        verify = sim.run_plant(plant_id, op_over, include_streams=False)
        sol["twin_verification"] = {"kpis": verify["kpis"], "constraint_penalty": verify["constraint_penalty"],
                                    "violations": [c["label"] for c in verify["constraints"] if c["violated"]]}
        base = sim.run_plant(plant_id, include_streams=False)
        sol["benefit"] = {k: round(verify["kpis"][k] - base["kpis"][k], 4)
                          for k in ("margin_usd_h", "lump_al2o3_pct", "lump_fe_pct", "fines_fe_pct", "fe_recovery_pct",
                                    "energy_kwh_t")}
        sol["guidance"] = operator_guidance(base["constraints"], base["kpis"], sol)
        return sol

    def simulate(self, plant_id: str, *, steps: int = 48, disturbance: dict | None = None,
                 tuning: dict | None = None, controller_on: bool = True, compare: bool = True,
                 noise_pct: float = 0.35) -> dict:
        ctrl = self._controller(plant_id, tuning)
        h = current_hour()
        truth = get_historian().truth(plant_id, h)
        y0 = {c: float(truth["kpis"][c]) for c in ctrl.cv_keys}
        u0 = {m: float(truth["mvs"][m]) for m in ctrl.mv_keys}
        # default scenario: a silica-rich ore band arrives after the sixth interval and pushes the
        # product out of its quality zone unless the controller responds
        dist = disturbance or {"lump_al2o3_pct": [0.0] * 6 + [0.62] * max(steps - 6, 1)}
        run = ctrl.simulate(y0, u0, steps=steps, disturbance=dist, noise_pct=noise_pct,
                            controller_on=controller_on, targets=(tuning or {}).get("targets"))
        out = {"plant_id": plant_id, "closed_loop": run, "disturbance": dist,
               "disturbance_note": "Clay-rich ore band from interval 6 (+0.62 % Al2O3 on the lump product) "
                                   "unless a disturbance was supplied.",
               "tuning": {"horizon": ctrl.P, "control_horizon": ctrl.M, "dt_min": ctrl.dt,
                          "cv_weights": ctrl.cv_weights, "mv_weights": ctrl.mv_weights}}
        if compare and controller_on:
            base = ctrl.simulate(y0, u0, steps=steps, disturbance=dist, noise_pct=noise_pct,
                                 controller_on=False, targets=(tuning or {}).get("targets"))
            out["open_loop"] = base
            out["comparison"] = {c: {"mpc_rmse": run["metrics"]["zone_rmse"][c],
                                     "open_loop_rmse": base["metrics"]["zone_rmse"][c],
                                     "mpc_target_rmse": run["metrics"]["rmse"][c],
                                     "open_loop_target_rmse": base["metrics"]["rmse"][c],
                                     "improvement_pct": (None if base["metrics"]["zone_rmse"][c] < 1e-9
                                                         else round(100 * (1 - run["metrics"]["zone_rmse"][c]
                                                                           / base["metrics"]["zone_rmse"][c]), 1))}
                                 for c in ctrl.cv_keys}
        return out

    def advisory(self, plant_id: str, tag_health: dict | None = None) -> dict:
        ident = self.identification(plant_id)
        sim = get_simulation_service().run_plant(plant_id, include_streams=False)
        return {"plant_id": plant_id, "pairing": pairing_analysis(ident),
                "readiness": readiness(tag_health, ident),
                "guidance": operator_guidance(sim["constraints"], sim["kpis"]),
                "gain_matrix": ident["gain_matrix"], "mv_keys": ident["mv_keys"], "cv_keys": ident["cv_keys"],
                "condition_number": ident["condition_number"]}


_service: MPCService | None = None


def get_mpc_service() -> MPCService:
    global _service
    if _service is None:
        _service = MPCService()
    return _service
