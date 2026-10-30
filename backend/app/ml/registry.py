"""In-process model registry: trains lazily, versions models and records their metrics."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np

from app.core.logging import get_logger
from app.ml.anomaly import AnomalyDetector, drift_report
from app.ml.dataset import FEATURES, TARGETS, build_dataset
from app.ml.models import TrainedModel, learning_curve, partial_dependence, train_model

log = get_logger("ml")

DEFAULT_TARGETS = ["lump_al2o3_pct", "lump_fe_pct", "fines_fe_pct", "fe_recovery_pct", "margin_usd_h"]


class ModelRegistry:
    """Holds the trained models, their datasets and the training history."""

    def __init__(self, n_samples: int = 260, seed: int = 11):
        self._lock = threading.Lock()
        self.n_samples, self.seed = n_samples, seed
        self.dataset: dict | None = None
        self.reference_dataset: dict | None = None
        self.models: dict[str, TrainedModel] = {}
        self.detector: AnomalyDetector | None = None
        self.history: list[dict] = []

    # ---- lifecycle -----------------------------------------------------------------------------
    def ensure(self, targets: list[str] | None = None, algorithm: str = "gradient_boosting") -> None:
        with self._lock:
            if self.dataset is None:
                log.info(f"building ML dataset ({self.n_samples} twin samples)")
                self.dataset = build_dataset(n=self.n_samples, seed=self.seed, noise_pct=0.6)
                self.reference_dataset = self.dataset
            for t in (targets or DEFAULT_TARGETS):
                key = f"{t}:{algorithm}"
                if key not in self.models:
                    self.models[key] = train_model(self.dataset, t, algorithm=algorithm)
                    self._record(self.models[key])
            if self.detector is None:
                self.detector = AnomalyDetector().fit(np.asarray(self.dataset["X"]), self.dataset["feature_names"])

    def retrain(self, targets: list[str] | None = None, *, algorithm: str = "gradient_boosting",
                n_samples: int | None = None, seed: int | None = None, noise_pct: float = 0.6) -> dict:
        """Rebuild the dataset and refit the models — the endpoint behind the desk's Retrain button."""
        with self._lock:
            self.n_samples = n_samples or self.n_samples
            self.seed = seed if seed is not None else self.seed + 1
            self.dataset = build_dataset(n=self.n_samples, seed=self.seed, noise_pct=noise_pct)
            trained = []
            for t in (targets or DEFAULT_TARGETS):
                m = train_model(self.dataset, t, algorithm=algorithm)
                self.models[f"{t}:{algorithm}"] = m
                self._record(m)
                trained.append(m.as_dict())
            self.detector = AnomalyDetector().fit(np.asarray(self.dataset["X"]), self.dataset["feature_names"])
            return {"trained": trained, "n_samples": self.dataset["n"], "seed": self.seed,
                    "algorithm": algorithm, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def train_hybrid(self, target: str, twin_values: np.ndarray, algorithm: str = "gradient_boosting") -> TrainedModel:
        self.ensure([target])
        m = train_model(self.dataset, target, algorithm=algorithm, hybrid_baseline=twin_values)
        self.models[m.key] = m
        self._record(m)
        return m

    # ---- queries -------------------------------------------------------------------------------
    def get(self, target: str, algorithm: str = "gradient_boosting") -> TrainedModel:
        self.ensure([target], algorithm)
        return self.models[f"{target}:{algorithm}"]

    def list_models(self) -> list[dict]:
        self.ensure()
        return [m.as_dict() for m in self.models.values()]

    def importance(self, target: str) -> list[dict]:
        return self.get(target).importance

    def learning_curve(self, target: str) -> list[dict]:
        self.ensure([target])
        return learning_curve(self.dataset, target)

    def partial_dependence(self, target: str, feature: str) -> dict:
        return partial_dependence(self.get(target), self.dataset, feature)

    def score_anomaly(self, features: dict[str, float]) -> dict:
        self.ensure()
        return self.detector.score(features)

    def drift(self, current: dict | None = None) -> dict:
        self.ensure()
        cur = current or build_dataset(n=90, seed=self.seed + 77, noise_pct=1.2)
        return drift_report(self.reference_dataset or self.dataset, cur)

    def _record(self, m: TrainedModel) -> None:
        self.history.append({"key": m.key, "target": m.target, "algorithm": m.algorithm,
                             "metrics": m.metrics, "trained_utc": m.trained_utc,
                             "version": str(len([h for h in self.history if h["key"] == m.key]) + 1)})
        m.version = self.history[-1]["version"]


_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
