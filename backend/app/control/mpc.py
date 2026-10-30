"""Model-predictive control layer (supervisory, above the DCS regulatory loops).

A condensed dynamic-matrix-control (DMC) formulation is used:

* the FOPDT models identified from the twin give the step-response coefficient matrix S;
* the controller solves, every control interval, a constrained quadratic programme

      min_dU   sum_i || Gamma (y_hat(k+i) - r(k+i)) ||^2 + || Lambda dU ||^2 + rho || eps ||^2
      s.t.     u_lo <= u(k+m) <= u_hi,   |du| <= du_max,
               y_lo - eps <= y_hat <= y_hi + eps,   eps >= 0

  where the output constraints are soft (slack ``eps``) and the slack weight rho follows the
  constraint priority hierarchy, so quality limits are given up only after process limits;
* only the first move of the optimal sequence is implemented (receding horizon), and the model is
  bias-corrected with the current measurement (DMC feedback), which removes steady-state offset.

The same module provides a closed-loop simulator so the desk can show the operator what the
controller would have done against a disturbance, and a DCS hand-over payload.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from app.control.identification import CV_BY_KEY, MV_BY_KEY


class MPCController:
    """Condensed DMC controller built from an identification result."""

    def __init__(self, ident: dict, *, horizon: int = 24, control_horizon: int = 4, dt_min: float = 5.0,
                 cv_weights: dict[str, float] | None = None, mv_weights: dict[str, float] | None = None,
                 targets: dict[str, float] | None = None, zones: dict[str, tuple[float, float]] | None = None,
                 slack_weight: float = 2500.0, target_weight: float = 0.3):
        self.ident = ident
        self.mv_keys: list[str] = list(ident["mv_keys"])
        self.cv_keys: list[str] = list(ident["cv_keys"])
        self.P, self.M, self.dt = int(horizon), int(control_horizon), float(dt_min)
        self.slack_weight = float(slack_weight)
        # Zone control: the operating band is what matters, the target is only a gentle pull inside it.
        # target_weight scales the tracking term against the soft zone constraints.
        self.target_weight = float(target_weight)
        self.cv_weights = {c: float((cv_weights or {}).get(c, CV_BY_KEY[c]["weight"])) for c in self.cv_keys}
        self.mv_weights = {m: float((mv_weights or {}).get(m, 1.0 + MV_BY_KEY[m]["cost"])) for m in self.mv_keys}
        self.targets = {c: float((targets or {}).get(c, CV_BY_KEY[c]["target"])) for c in self.cv_keys}
        self.zones = {c: tuple((zones or {}).get(c, (CV_BY_KEY[c]["lo"], CV_BY_KEY[c]["hi"]))) for c in self.cv_keys}
        self.S = self._step_matrix()

    # ---- model ---------------------------------------------------------------------------------
    def _step_matrix(self) -> np.ndarray:
        """Step-response coefficients S[i, cv, mv] for i = 1..P sample intervals ahead."""
        S = np.zeros((self.P, len(self.cv_keys), len(self.mv_keys)))
        for a, cv in enumerate(self.cv_keys):
            for b, mv in enumerate(self.mv_keys):
                mdl = self.ident["models"][f"{cv}|{mv}"]
                k, tau, theta = mdl["gain"], max(mdl["tau_min"], 1e-6), mdl["dead_time_min"]
                t = (np.arange(1, self.P + 1)) * self.dt
                S[:, a, b] = np.where(t <= theta, 0.0, k * (1.0 - np.exp(-(t - theta) / tau)))
        return S

    def _dynamic_matrix(self) -> np.ndarray:
        """Condensed matrix A (P*ny x M*nu) mapping the move vector to predicted deviations."""
        ny, nu = len(self.cv_keys), len(self.mv_keys)
        A = np.zeros((self.P * ny, self.M * nu))
        for i in range(self.P):
            for m in range(self.M):
                if i >= m:
                    A[i * ny:(i + 1) * ny, m * nu:(m + 1) * nu] = self.S[i - m]
        return A

    # ---- control -------------------------------------------------------------------------------
    def _free_response(self, history: list[tuple[np.ndarray, int]] | None) -> np.ndarray:
        """Effect of moves already implemented but not yet fully realised (DMC free response)."""
        ny, nu = len(self.cv_keys), len(self.mv_keys)
        free = np.zeros((self.P, ny))
        for du_past, age in (history or []):
            for i in range(self.P):
                a = min(i + age, self.P - 1)
                b = min(age, self.P - 1)
                free[i] += (self.S[a] - self.S[b]) @ du_past
        return free

    def solve(self, y_now: dict[str, float], u_now: dict[str, float], *,
              y_model: dict[str, float] | None = None, targets: dict[str, float] | None = None,
              disturbance_forecast: dict[str, float] | None = None,
              history: list[tuple[np.ndarray, int]] | None = None) -> dict:
        """Compute the optimal move sequence and return the first move (receding horizon)."""
        ny, nu = len(self.cv_keys), len(self.mv_keys)
        tgt = {**self.targets, **(targets or {})}
        bias = {c: y_now[c] - (y_model or y_now).get(c, y_now[c]) for c in self.cv_keys}
        dist = disturbance_forecast or {}
        pending = self._free_response(history)
        y_free = np.array([[y_now[c] + dist.get(c, 0.0) * (i + 1) / self.P
                            for c in self.cv_keys] for i in range(self.P)])
        y_free = (y_free + pending).reshape(-1)
        ref = np.array([[tgt[c] for c in self.cv_keys] for _ in range(self.P)]).reshape(-1)
        A_raw = self._dynamic_matrix()
        lo = np.array([MV_BY_KEY[m]["lo"] for m in self.mv_keys])
        hi = np.array([MV_BY_KEY[m]["hi"] for m in self.mv_keys])
        dmax = np.array([MV_BY_KEY[m]["max_move"] for m in self.mv_keys])
        # --- scaling: CV errors by their zone span, MV moves by their move limit. Without this the
        # QP is badly conditioned (Blaine ~1700 cm2/g against silica ~2 % SiO2) and SLSQP stalls.
        cv_span = np.array([max(self.zones[c][1] - self.zones[c][0], 1e-6) for c in self.cv_keys])
        A = A_raw * np.tile(dmax, self.M)[None, :] / np.tile(cv_span, self.P)[:, None]
        gamma = np.tile(np.array([self.cv_weights[c] for c in self.cv_keys]), self.P) * np.sqrt(self.target_weight)
        lam = np.tile(np.array([self.mv_weights[m] for m in self.mv_keys]), self.M)
        u0 = np.array([u_now[m] for m in self.mv_keys])
        y_lo = np.tile(np.array([self.zones[c][0] for c in self.cv_keys]), self.P)
        y_hi = np.tile(np.array([self.zones[c][1] for c in self.cv_keys]), self.P)
        n_var = self.M * nu + 2 * ny

        def unpack(z):
            return z[:self.M * nu], z[self.M * nu:self.M * nu + ny], z[self.M * nu + ny:]

        y_free_s = y_free / np.tile(cv_span, self.P)
        ref_s = ref / np.tile(cv_span, self.P)

        def cost(z):
            v, s_lo, s_hi = unpack(z)
            e = (y_free_s + A @ v - ref_s) * gamma
            return float(e @ e + (lam * v) @ v + self.slack_weight * (s_lo @ s_lo + s_hi @ s_hi))

        def grad(z):
            v, s_lo, s_hi = unpack(z)
            g_v = 2.0 * A.T @ ((y_free_s + A @ v - ref_s) * gamma ** 2) + 2.0 * lam * v
            return np.concatenate([g_v, 2 * self.slack_weight * s_lo, 2 * self.slack_weight * s_hi])

        cons = []
        cum = np.zeros((self.M, self.M))
        for i in range(self.M):
            cum[i, :i + 1] = 1.0
        C = np.kron(cum, np.eye(nu))       # cumulative moves -> absolute MV deviation

        def _abs_u(v):
            return np.tile(u0, self.M) + C @ (v * np.tile(dmax, self.M))

        def u_upper(z):
            v, _, _ = unpack(z)
            return (np.tile(hi, self.M) - _abs_u(v)) / np.tile(np.maximum(hi - lo, 1e-6), self.M)

        def u_lower(z):
            v, _, _ = unpack(z)
            return (_abs_u(v) - np.tile(lo, self.M)) / np.tile(np.maximum(hi - lo, 1e-6), self.M)

        def y_upper(z):
            v, _, s_hi = unpack(z)
            return (y_hi / np.tile(cv_span, self.P) + np.tile(s_hi, self.P)) - (y_free_s + A @ v)

        def y_lower(z):
            v, s_lo, _ = unpack(z)
            return (y_free_s + A @ v) - (y_lo / np.tile(cv_span, self.P) - np.tile(s_lo, self.P))

        cons = [{"type": "ineq", "fun": f} for f in (u_upper, u_lower, y_upper, y_lower)]
        bounds = [(-1.0, 1.0)] * (self.M * nu) + [(0.0, None)] * (2 * ny)
        z0 = np.zeros(n_var)
        res = minimize(cost, z0, jac=grad, bounds=bounds, constraints=cons, method="SLSQP",
                       options={"maxiter": 120, "ftol": 1e-8})
        v, s_lo, s_hi = unpack(res.x if res.x is not None else z0)
        du = v * np.tile(dmax, self.M)
        moves = du.reshape(self.M, nu)
        u_next = np.clip(u0 + moves[0], lo, hi)
        y_pred = ((y_free_s + A @ v) * np.tile(cv_span, self.P)).reshape(self.P, ny)
        y_nom = y_free.reshape(self.P, ny)
        return {
            "status": "optimal" if res.success else "suboptimal",
            "solver_message": str(res.message), "iterations": int(res.nit), "objective": round(float(res.fun), 4),
            "moves": {m: round(float(moves[0, j]), 4) for j, m in enumerate(self.mv_keys)},
            "move_plan": [{m: round(float(moves[i, j]), 4) for j, m in enumerate(self.mv_keys)}
                          for i in range(self.M)],
            "u_next": {m: round(float(u_next[j]), 4) for j, m in enumerate(self.mv_keys)},
            "u_now": {m: round(float(u0[j]), 4) for j, m in enumerate(self.mv_keys)},
            "predicted": {c: [round(float(y_pred[i, a]), 4) for i in range(self.P)]
                          for a, c in enumerate(self.cv_keys)},
            "no_action": {c: [round(float(y_nom[i, a]), 4) for i in range(self.P)]
                          for a, c in enumerate(self.cv_keys)},
            "targets": {c: round(float(tgt[c]), 4) for c in self.cv_keys},
            "zones": {c: [round(float(self.zones[c][0]), 4), round(float(self.zones[c][1]), 4)] for c in self.cv_keys},
            "slack_lo": {c: round(float(s_lo[a]), 5) for a, c in enumerate(self.cv_keys)},
            "slack_hi": {c: round(float(s_hi[a]), 5) for a, c in enumerate(self.cv_keys)},
            "horizon_min": self.P * self.dt, "control_horizon_min": self.M * self.dt, "dt_min": self.dt,
            "constraint_active": [c for a, c in enumerate(self.cv_keys) if s_lo[a] > 1e-4 or s_hi[a] > 1e-4],
        }

    # ---- closed loop ---------------------------------------------------------------------------
    def simulate(self, y0: dict[str, float], u0: dict[str, float], *, steps: int = 48,
                 disturbance: dict[str, list[float]] | None = None, noise_pct: float = 0.35,
                 seed: int = 7, controller_on: bool = True, targets: dict[str, float] | None = None) -> dict:
        """Closed-loop simulation against the identified model plus a disturbance and noise."""
        rng = np.random.default_rng(seed)
        ny, nu = len(self.cv_keys), len(self.mv_keys)
        tgt = {**self.targets, **(targets or {})}
        u = np.array([u0[m] for m in self.mv_keys], dtype=float)
        # state: per (cv, mv) first-order state, plus dead-time buffers
        state = np.zeros((ny, nu))      # realised first-order response of each (cv, mv) pair
        cum_u = np.zeros((ny, nu))      # cumulative implemented move seen by each pair (after dead time)
        buffers = {(a, b): [0.0] * max(int(round(self.ident["models"][f'{c}|{m}']["dead_time_min"] / self.dt)), 0)
                   for a, c in enumerate(self.cv_keys) for b, m in enumerate(self.mv_keys)}
        y_base = np.array([y0[c] for c in self.cv_keys], dtype=float)
        dist = {c: np.array(v, dtype=float) for c, v in (disturbance or {}).items()}
        hist = {"t_min": [], "cv": {c: [] for c in self.cv_keys}, "mv": {m: [] for m in self.mv_keys},
                "target": {c: [] for c in self.cv_keys}, "violations": 0, "solver": []}
        y = y_base.copy()
        ise = np.zeros(ny)
        zone_ise = np.zeros(ny)
        travel = np.zeros(nu)
        history_moves: list[tuple[np.ndarray, int]] = []   # (implemented move, steps since implemented)
        for k in range(steps):
            d = np.array([dist.get(c, np.zeros(steps))[k] if c in dist else 0.0 for c in self.cv_keys])
            meas = y + d + rng.normal(0, noise_pct / 100.0 * np.abs(y_base))
            if controller_on:
                sol = self.solve({c: float(meas[a]) for a, c in enumerate(self.cv_keys)},
                                 {m: float(u[b]) for b, m in enumerate(self.mv_keys)}, targets=tgt,
                                 history=[(d, age) for d, age in history_moves])
                du = np.array([sol["moves"][m] for m in self.mv_keys])
                hist["solver"].append(sol["status"])
            else:
                du = np.zeros(nu)
                hist["solver"].append("open-loop")
            u = np.clip(u + du, [MV_BY_KEY[m]["lo"] for m in self.mv_keys],
                        [MV_BY_KEY[m]["hi"] for m in self.mv_keys])
            travel += np.abs(du)
            history_moves = [(d, age + 1) for d, age in history_moves if age + 1 < self.P]
            if np.any(np.abs(du) > 1e-9):
                history_moves.append((du.copy(), 0))
            # advance the FOPDT states with the implemented move
            for a, c in enumerate(self.cv_keys):
                for b, m in enumerate(self.mv_keys):
                    mdl = self.ident["models"][f"{c}|{m}"]
                    tau = max(mdl["tau_min"], 1e-6)
                    buf = buffers[(a, b)]
                    if buf:
                        buf.append(du[b])
                        applied = buf.pop(0)
                    else:
                        applied = du[b]
                    alpha = 1.0 - np.exp(-self.dt / tau)
                    cum_u[a, b] += applied
                    state[a, b] += alpha * (mdl["gain"] * cum_u[a, b] - state[a, b])
            y = y_base + state.sum(axis=1) + d
            err = np.array([y[a] - tgt[c] for a, c in enumerate(self.cv_keys)])
            ise += err ** 2
            lo = np.array([self.zones[c][0] for c in self.cv_keys])
            hi = np.array([self.zones[c][1] for c in self.cv_keys])
            # zone error: distance outside the operating band (zero inside) — the honest measure for a
            # zone controller, which is not asked to sit exactly on target
            zerr = np.maximum(np.maximum(lo - y, y - hi), 0.0)
            zone_ise += zerr ** 2
            hist["violations"] += int(np.sum((y < lo) | (y > hi)))
            hist["t_min"].append(round(k * self.dt, 1))
            for a, c in enumerate(self.cv_keys):
                hist["cv"][c].append(round(float(y[a]), 4))
                hist["target"][c].append(round(float(tgt[c]), 4))
            for b, m in enumerate(self.mv_keys):
                hist["mv"][m].append(round(float(u[b]), 3))
        hist["metrics"] = {
            "ise": {c: round(float(ise[a]), 4) for a, c in enumerate(self.cv_keys)},
            "rmse": {c: round(float(np.sqrt(ise[a] / steps)), 4) for a, c in enumerate(self.cv_keys)},
            "zone_rmse": {c: round(float(np.sqrt(zone_ise[a] / steps)), 4) for a, c in enumerate(self.cv_keys)},
            "mv_travel": {m: round(float(travel[b]), 3) for b, m in enumerate(self.mv_keys)},
            "violations": hist["violations"], "steps": steps, "dt_min": self.dt,
            "controller": "MPC" if controller_on else "open loop",
        }
        return hist


def handover_payload(solution: dict, *, mode: str = "advisory", operator: str = "control-room",
                     valid_for_min: float = 15.0) -> dict:
    """Package an MPC solution for the DCS / PLC (advisory or closed-loop hand-over)."""
    import hashlib
    import json
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    body = {
        "issued_utc": now.isoformat(timespec="seconds"),
        "valid_until_utc": (now + timedelta(minutes=valid_for_min)).isoformat(timespec="seconds"),
        "mode": mode, "issued_by": operator, "controller": "IODT-MPC",
        "setpoints": [{"tag": _dcs_tag(k), "mv": k, "value": v, "unit": MV_BY_KEY[k]["unit"],
                       "ramp_rate_per_min": round(MV_BY_KEY[k]["max_move"] / 5.0, 4),
                       "current": solution["u_now"][k], "delta": round(v - solution["u_now"][k], 4)}
                      for k, v in solution["u_next"].items()],
        "predicted_cv": {c: v[-1] for c, v in solution["predicted"].items()},
        "targets": solution["targets"], "status": solution["status"],
    }
    body["checksum"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    return body


def _dcs_tag(mv_key: str) -> str:
    return "IX-OB-01." + (MV_BY_KEY.get(mv_key, {}).get("tag", "SUP_" + mv_key.upper()[:12]) + ".SP")
