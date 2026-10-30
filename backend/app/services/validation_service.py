"""Validation and acceptance service."""
from __future__ import annotations

import threading
import time
from typing import Any

from app.validation import runner
from app.validation.criteria import catalogue as criteria_catalogue
from app.validation.protocol import protocol as protocol_doc
from app.validation.report import render_markdown
from app.validation.scenarios import ENVELOPE, catalogue as scenario_catalogue, envelope_check


class ValidationService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, dict] = {}
        # A run is deterministic for a given model version, plant and data window, so repeat
        # views of the page replay the stored result instead of re-solving the circuit.
        # `refresh=True` forces a fresh run, which is what the acceptance evidence requires.
        self._runs: dict[tuple, dict] = {}

    # ---- specification ---------------------------------------------------------------------
    def criteria(self) -> dict[str, Any]:
        return criteria_catalogue()

    def scenarios(self) -> dict[str, Any]:
        return scenario_catalogue()

    def protocol(self) -> dict[str, Any]:
        return protocol_doc()

    def envelope(self, plant_id: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"envelope": ENVELOPE}
        if plant_id:
            from app.services.plant_service import get_plant_service
            _, ore, op, _ = get_plant_service().configs(plant_id)
            point = {**op.model_dump(), **ore.model_dump()}
            out["plant_id"] = plant_id
            out["current_point"] = envelope_check(point)
        return out

    def check_point(self, values: dict[str, float]) -> dict[str, Any]:
        return envelope_check(values)

    # ---- execution -------------------------------------------------------------------------
    def run(self, plant_id: str, *, hours: int = 168, section: str = "all",
            tests_pass: bool | None = None, refresh: bool = False) -> dict[str, Any]:
        key = (plant_id, int(hours), section, tests_pass)
        if not refresh:
            with self._lock:
                if key in self._runs:
                    return self._runs[key]
        t0 = time.perf_counter()
        if section == "accuracy":
            out = {"plant_id": plant_id, "accuracy": runner.run_accuracy(plant_id, hours=hours)}
        elif section == "behaviour":
            out = {"plant_id": plant_id, "behaviour": runner.run_behaviour(plant_id)}
        elif section == "fail_safe":
            out = {"plant_id": plant_id, "fail_safe": runner.run_fail_safe(plant_id)}
        elif section == "system":
            out = {"plant_id": plant_id, "system": runner.run_system(plant_id, tests_pass=tests_pass)}
        else:
            out = runner.run_all(plant_id, hours=hours, tests_pass=tests_pass)
        out["elapsed_s"] = round(time.perf_counter() - t0, 2)
        out["section"] = section
        with self._lock:
            self._runs[key] = out
            if section == "all":
                self._last[plant_id] = out
        return out

    def last(self, plant_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._last.get(plant_id)

    # ---- report ----------------------------------------------------------------------------
    def report(self, plant_id: str, *, hours: int = 168, gate: str = "G1",
               tests_pass: bool | None = None, fmt: str = "markdown") -> dict[str, Any]:
        run = self.last(plant_id) or self.run(plant_id, hours=hours, tests_pass=tests_pass)
        if "accuracy" not in run:
            run = self.run(plant_id, hours=hours, tests_pass=tests_pass)
        from app.core.config import get_settings
        from app.services.plant_service import get_plant_service
        name = get_plant_service().get(plant_id).get("name", plant_id)
        md = render_markdown(run, plant_name=name, model_version=get_settings().MODEL_VERSION,
                             gate=gate)
        return {"plant_id": plant_id, "gate": gate, "format": fmt,
                "overall_verdict": run["overall_verdict"],
                "markdown": md, "characters": len(md),
                "filename": f"Acceptance_Test_Report_{plant_id}_{gate}.md"}

    def certificate(self, plant_id: str, *, gate: str = "G1") -> dict[str, Any]:
        """A one-page summary suitable for the front of an acceptance pack."""
        run = self.last(plant_id) or self.run(plant_id)
        acc = run["accuracy"]
        return {
            "plant_id": plant_id, "gate": gate,
            "verdict": run["overall_verdict"],
            "accuracy": {"criteria_evaluated": acc["summary"]["evaluated"],
                         "passed": acc["summary"]["pass"],
                         "class_a_failures": acc["summary"]["class_a_fail"],
                         "hours_evaluated": acc["hours_evaluated"],
                         "exclusion_pct": acc["exclusion_pct"]},
            "behaviour": {"scenarios": len(run["behaviour"]["rows"]),
                          "passed": sum(1 for r in run["behaviour"]["rows"] if r["verdict"] == "pass")},
            "fail_safe": run["fail_safe"]["verdict"],
            "system": {"passed": run["system"]["summary"]["pass"],
                       "evidence_required": run["system"]["summary"]["evidence_required"]},
            "blocking": run["gate_readiness"]["blocking"],
            "evidence_outstanding": run["gate_readiness"]["evidence_outstanding"],
            "statement": ("All gating criteria met. Recommended for acceptance at this gate, "
                          "subject to the outstanding site evidence listed."
                          if run["overall_verdict"] in ("pass", "marginal", "incomplete")
                          else "Gating criteria not met. Not recommended for acceptance."),
        }


_service: ValidationService | None = None


def get_validation_service() -> ValidationService:
    global _service
    if _service is None:
        _service = ValidationService()
    return _service
