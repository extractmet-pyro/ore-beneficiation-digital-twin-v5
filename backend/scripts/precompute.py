"""Build-time precomputation of everything that is otherwise trained on first use.

The hybrid layer and the ML registry cost roughly three minutes of solid CPU to build: 320
first-principles twin solves for the design of experiments, eight gradient-boosted models, a
260-sample ML dataset and an anomaly detector. On a full core that is tolerable at start-up. On
a fractional-CPU host — a Render free instance is about a tenth of a core — it is half an hour
of saturated CPU during which every interactive request is starved. Warming at start-up is the
wrong answer there; it makes the service slower, not faster.

So the work moves to the build, which happens once per deploy on the build machine rather than
once per wake on the runtime instance. This script runs during `pip install && python
scripts/precompute.py`, trains everything, and writes it to a cache file inside the image. At
start-up the service loads that file in well under a second and does no training at all.

The cache is keyed by model version and by the parameters that determine its contents, so a
stale cache is ignored rather than silently served. If the file is missing or does not match,
the service falls back to building lazily exactly as before — the cache is an optimisation, and
nothing depends on it existing.

Run it by hand after changing the twin, the hybrid layer or the sample counts:

    cd backend && python scripts/precompute.py

Budget roughly nine minutes on a build machine at the default quarter-hourly replay grid. If
your build times out, set REPLAY_STEPS_PER_HOUR=1: the build drops to about two minutes and only
the Live page's instrument board gets slower.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from app.core.config import get_settings
    from app.ml.registry import get_registry
    from app.hybrid.builder import HYBRID_TARGETS, get_builder
    from app.services.warm_cache import cache_path, save_cache

    s = get_settings()
    t0 = time.time()
    print(f"precompute: model {s.MODEL_VERSION}, HYBRID_SAMPLES={s.HYBRID_SAMPLES}, "
          f"replay grid {s.REPLAY_STEPS_PER_HOUR}/h", flush=True)

    b = get_builder()
    t = time.time()
    b.dataset()
    print(f"  design of experiments  {b.n} rows   {time.time() - t:6.1f}s", flush=True)

    for target in HYBRID_TARGETS:
        t = time.time()
        b.build(target)
        print(f"  hybrid model           {target:<20}{time.time() - t:6.1f}s", flush=True)

    for target in HYBRID_TARGETS:
        t = time.time()
        b.compare(target)
        b.extrapolation_test(target)
        print(f"  studies                {target:<20}{time.time() - t:6.1f}s", flush=True)

    t = time.time()
    get_registry().ensure()
    print(f"  ML registry                                {time.time() - t:6.1f}s", flush=True)

    # the replay grid dominates: 168 h x REPLAY_STEPS_PER_HOUR x plants, truth and model each
    t = time.time()
    path = save_cache()
    size_mb = path.stat().st_size / 1e6
    print(f"  written                {path.name:<20}{time.time() - t:6.1f}s  ({size_mb:.1f} MB)",
          flush=True)
    print(f"precompute complete in {time.time() - t0:.1f}s -> {cache_path()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
