"""Hybrid mechanistic + data-driven model.

The client asked for a twin that is *both* mechanistic and data driven. That is not a slogan;
it is a specific architectural choice with specific trade-offs, and there are several ways to
make it. This module implements the recognised compositions and makes the choice explicit and
auditable:

* ``mechanistic_only`` — the first-principles twin alone. The reference case, and what the
  hybrid must never be worse than.
* ``data_only`` — a supervised model on plant data alone. Accurate where it has seen data,
  unreliable the moment it has not, and incapable of answering a question about an operating
  point the plant has never run. Carried here so the comparison can be made honestly.
* ``parallel_residual`` — the twin predicts, a learned model predicts the twin's *residual*,
  and the two are added. The physics sets the shape of the response; the learner absorbs the
  site-specific effects the physics does not contain.
* ``serial_parameter`` — the learner estimates a *parameter* of the mechanistic model (a
  breakage constant, an entrainment factor, an Ep), and the physics is then solved with it.
  Slower, but every prediction remains a physically consistent solution.
* ``gated_residual`` — ``parallel_residual`` with the correction gated on the domain of
  validity and bounded in magnitude. **This is the default**, because it is the only one of
  them that fails safe.
* ``ensemble_weighted`` — a fixed blend. Simple, and included because sites ask for it; it is
  dominated by ``gated_residual`` in every test we run.

The outputs carry an **attribution**: how much of the number came from the physics and how
much from the learner. An operator who cannot see that will not trust either.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from app.hybrid.domain import DomainOfValidity

MODES: list[dict[str, Any]] = [
    {"id": "mechanistic_only", "name": "Mechanistic only", "learned": False,
     "summary": "First-principles twin alone.",
     "strength": "Extrapolates. Every answer is a consistent solution of the physics.",
     "weakness": "Carries the site-specific bias the physics does not model."},
    {"id": "data_only", "name": "Data driven only", "learned": True,
     "summary": "Supervised model on plant history alone.",
     "strength": "Most accurate inside the range it was trained on.",
     "weakness": "No extrapolation, no mass balance, no answer for an untried set-point."},
    {"id": "parallel_residual", "name": "Parallel residual", "learned": True,
     "summary": "Twin prediction plus a learned correction on the twin's residual.",
     "strength": "Keeps the physics response shape, removes systematic bias.",
     "weakness": "The correction is unbounded and ungated, so it can misbehave off-domain."},
    {"id": "serial_parameter", "name": "Serial parameter estimation", "learned": True,
     "summary": "Learner estimates a mechanistic parameter; the physics is then solved with it.",
     "strength": "Every prediction stays a physically consistent solution.",
     "weakness": "Needs a full twin solve per evaluation, so it is the slowest."},
    {"id": "gated_residual", "name": "Gated residual (default)", "learned": True,
     "summary": "Parallel residual, bounded in magnitude and tapered to zero outside the "
                "learner's domain of validity.",
     "strength": "Degrades to the mechanistic model instead of guessing. Demonstrable in an "
                 "acceptance test.",
     "weakness": "Gives up some accuracy at the edge of the envelope, on purpose."},
    {"id": "ensemble_weighted", "name": "Fixed-weight ensemble", "learned": True,
     "summary": "Fixed blend of mechanistic and data-driven predictions.",
     "strength": "Trivial to explain.",
     "weakness": "The weight is right in one operating region and wrong everywhere else."},
]

DEFAULT_MODE = "gated_residual"


class HybridModel:
    """One target variable, one mechanistic baseline, one learned correction, one gate."""

    def __init__(self, target: str, residual_model, domain: DomainOfValidity, *,
                 mode: str = DEFAULT_MODE, max_correction_sigma: float = 3.0,
                 max_correction_frac: float = 0.25, data_only_model=None,
                 parameter_solver: Callable[[dict, float], float] | None = None) -> None:
        self.target = target
        self.residual_model = residual_model
        self.data_only_model = data_only_model
        self.domain = domain
        self.mode = mode if mode in {m["id"] for m in MODES} else DEFAULT_MODE
        self.max_correction_sigma = float(max_correction_sigma)
        self.max_correction_frac = float(max_correction_frac)
        self.parameter_solver = parameter_solver

    # ---------------------------------------------------------------- bounding
    def _bound(self, correction: float, mech: float) -> tuple[float, str | None]:
        sigma = max(float(getattr(self.residual_model, "residual_sigma", 0.0)), 1e-9)
        cap_sigma = self.max_correction_sigma * sigma
        cap_frac = self.max_correction_frac * abs(mech) if mech else cap_sigma
        cap = min(cap_sigma, cap_frac) if mech else cap_sigma
        if abs(correction) <= cap:
            return correction, None
        return float(np.sign(correction) * cap), (
            f"correction clamped to {cap:.4g} "
            f"({'relative' if cap_frac < cap_sigma else 'sigma'} limit)")

    # ---------------------------------------------------------------- prediction
    def predict(self, features: dict[str, float], mechanistic: float, *,
                mode: str | None = None) -> dict[str, Any]:
        m = mode or self.mode
        dom = self.domain.score(features)
        raw = float(self.residual_model.predict(features)["value"]) if self.residual_model else 0.0
        data_only = (float(self.data_only_model.predict(features)["value"])
                     if self.data_only_model is not None else None)
        sigma = float(getattr(self.residual_model, "residual_sigma", 0.0) or 0.0)
        gate, clamp_note, note = 1.0, None, ""

        if m == "mechanistic_only":
            applied, gate = 0.0, 0.0
            note = "Learned correction disabled."
        elif m == "data_only":
            if data_only is None:
                raise ValueError("No data-only model is available for this target.")
            return {
                "target": self.target, "mode": m, "value": round(data_only, 4),
                "mechanistic": round(mechanistic, 4), "correction": None,
                "attribution": {"mechanistic_pct": 0.0, "learned_pct": 100.0},
                "domain": dom, "gate": 1.0, "clamped": None,
                "interval_95": [round(data_only - 1.96 * sigma, 4), round(data_only + 1.96 * sigma, 4)],
                "note": "Supervised model only. Shown for comparison; not used in service, "
                        "because it has no defined behaviour outside its training range.",
            }
        elif m == "serial_parameter":
            if self.parameter_solver is None:
                raise ValueError("No parameter solver is configured for this target.")
            est = self.parameter_solver(features, raw)
            return {
                "target": self.target, "mode": m, "value": round(float(est), 4),
                "mechanistic": round(mechanistic, 4), "correction": None,
                "estimated_parameter": round(float(raw), 6),
                "attribution": {"mechanistic_pct": 100.0, "learned_pct": 0.0,
                                "note": "The learner set a parameter; the number itself is a "
                                        "solution of the physics."},
                "domain": dom, "gate": 1.0, "clamped": None,
                "interval_95": None,
                "note": "Learner estimated a mechanistic parameter; the twin was then solved with it.",
            }
        elif m == "ensemble_weighted":
            w = 0.5
            val = w * mechanistic + (1 - w) * (data_only if data_only is not None else mechanistic)
            return {
                "target": self.target, "mode": m, "value": round(val, 4),
                "mechanistic": round(mechanistic, 4), "correction": round(val - mechanistic, 4),
                "attribution": {"mechanistic_pct": 50.0, "learned_pct": 50.0},
                "domain": dom, "gate": 1.0, "clamped": None,
                "interval_95": [round(val - 1.96 * sigma, 4), round(val + 1.96 * sigma, 4)],
                "note": "Fixed 50/50 blend. Included for comparison only.",
            }
        else:  # parallel_residual and gated_residual
            applied = raw
            if m == "gated_residual":
                gate = float(dom["confidence"])
                applied, clamp_note = self._bound(raw, mechanistic)
                applied *= gate
                if gate == 0.0:
                    note = ("Operating point is outside the learned model's domain; the "
                            "correction is switched off and the mechanistic twin answers alone.")
                elif gate < 1.0:
                    note = (f"Operating point is at the edge of the learned domain "
                            f"({dom['binding_check']}); correction tapered to {gate:.0%}.")
                else:
                    note = "Operating point is inside the learned domain; full correction applied."
            else:
                note = "Correction applied without gating or bounding (comparison mode)."

        value = mechanistic + applied
        tot = abs(mechanistic) + abs(applied)
        return {
            "target": self.target, "mode": m, "value": round(value, 4),
            "mechanistic": round(mechanistic, 4),
            "correction": round(applied, 4), "correction_unbounded": round(raw, 4),
            "attribution": {
                "mechanistic_pct": round(100 * abs(mechanistic) / tot, 2) if tot else 100.0,
                "learned_pct": round(100 * abs(applied) / tot, 2) if tot else 0.0,
                "correction_as_pct_of_value": round(100 * abs(applied) / max(abs(value), 1e-9), 2),
            },
            "domain": dom, "gate": round(gate, 4), "clamped": clamp_note,
            "interval_95": [round(value - 1.96 * sigma, 4), round(value + 1.96 * sigma, 4)],
            "sigma": round(sigma, 4),
            "note": note,
        }

    def config(self) -> dict[str, Any]:
        return {
            "target": self.target, "mode": self.mode, "modes": MODES,
            "bounds": {"max_correction_sigma": self.max_correction_sigma,
                       "max_correction_frac": self.max_correction_frac},
            "gate": {"taper_from": self.domain.taper_from, "cutoff": self.domain.cutoff,
                     "basis": "max of box excess, Mahalanobis ratio and nearest-neighbour ratio"},
            "residual_model": (self.residual_model.as_dict() if self.residual_model else None),
            "envelope": self.domain.envelope(),
            "guarantee": "In gated mode the hybrid prediction converges to the mechanistic "
                         "prediction as the operating point leaves the learned domain, and the "
                         "correction can never exceed the configured bound. Both properties are "
                         "demonstrated in the acceptance test suite.",
        }
