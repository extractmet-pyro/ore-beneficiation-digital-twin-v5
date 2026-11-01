"""Saving and restoring the trained layers so a cold start does not retrain them.

What is cached: the hybrid design of experiments, the four hybrid models with their residual and
data-only estimators and domain-of-validity fits, the two memoised studies per target, the ML
registry with its anomaly detector, and the 168 h replay nodes for every plant. Together these
are about three minutes of CPU on a full core, and half an hour on a tenth of one.

What is not cached: anything derived from a request, and any twin solve made in answering one.
Those are tens of milliseconds and belong on the request path.

**On the format.** This is a pickle, written by our own build step and read back by the same
image. That is a deliberate and bounded use: the file never leaves the container, is never
supplied by a user, and is never fetched over a network. It is rejected unless its fingerprint
matches the running code's version and parameters, so an upgrade cannot silently serve a stale
model. If the file is missing, unreadable or mismatched, the service builds lazily exactly as it
did before — the cache is an optimisation and nothing depends on it.
"""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("app")

CACHE_VERSION = 6       # bump when the cached object graph changes shape


def cache_dir() -> Path:
    d = os.environ.get("WARM_CACHE_DIR")
    return Path(d) if d else Path(__file__).resolve().parents[2] / ".cache"


def fingerprint() -> str:
    """Identifies the code and parameters the cache was built from.

    A cache whose fingerprint does not match the running service is ignored. This is what stops
    a model trained before an upgrade being served afterwards as though it were current.
    """
    from app.core.config import get_settings
    from app.hybrid.builder import HYBRID_TARGETS
    from app.ml.registry import DEFAULT_TARGETS

    s = get_settings()
    from app.services.historian_service import REPLAY_HOURS

    parts = [
        f"cache={CACHE_VERSION}",
        f"model={s.MODEL_VERSION}",
        f"replay={REPLAY_HOURS}@{s.REPLAY_ANCHOR_UTC}",
        f"hybrid_samples={s.HYBRID_SAMPLES}",
        f"replay_grid={s.REPLAY_STEPS_PER_HOUR}/h",
        f"hybrid_targets={','.join(sorted(HYBRID_TARGETS))}",
        f"ml_targets={','.join(sorted(DEFAULT_TARGETS))}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def cache_path() -> Path:
    return cache_dir() / f"warm-{fingerprint()}.pkl"


def _mpc_identifications() -> dict:
    """Identify the step-response model for every plant.

    This is 2.8 s per plant on a full core and is identical every time, so it is the last thing
    left that a user would wait on. The MPC page is the one a client is most likely to open.
    """
    from app.services.mpc_service import get_mpc_service
    from app.services.plant_service import get_plant_service
    ms = get_mpc_service()
    for pid in get_plant_service().ids():
        ms.identification(pid)
    return ms._ident


def _validation_runs() -> dict:
    """Pre-run the acceptance suite for every plant, exactly as the operator desk asks for it."""
    from app.services.plant_service import get_plant_service
    from app.services.validation_service import get_validation_service
    vs = get_validation_service()
    for pid in get_plant_service().ids():
        vs.run(pid, section="all", tests_pass=True)
    return {"runs": vs._runs, "last": vs._last}


# ------------------------------------------------------------------------------- save
def save_cache() -> Path:
    from app.hybrid.builder import get_builder
    from app.ml.registry import get_registry
    from app.services.historian_service import REPLAY_HOURS, get_historian
    from app.services.plant_service import get_plant_service

    # The replay nodes are deterministic for a given anchor, so they belong in the cache:
    # recomputing them costs minutes on a full core and the better part of an hour on free.
    #
    # The grid is quarter-hourly, not hourly. Every page but one samples on whole hours, but the
    # Live page's instrument board plots a 24 h trace at step_h=0.25 — off the hourly grid, so an
    # hourly cache misses on three samples in four and the page solves ~70 snapshots live. A
    # quarter-hourly grid is four times the nodes and about three times the file; it is the
    # difference between that page opening at once and it taking half a minute on free.
    from app.core.config import get_settings
    steps = get_settings().REPLAY_STEPS_PER_HOUR
    h, ps = get_historian(), get_plant_service()
    for pid in ps.ids():
        ps.tags(pid)
        for i in range(REPLAY_HOURS * steps):
            t = i / steps
            h.truth(pid, t)
            h.model(pid, t)

    b, r = get_builder(), get_registry()
    blob = {
        "fingerprint": fingerprint(),
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hybrid": {"n": b.n, "seed": b.seed, "ds": b._ds, "cache": b._cache, "studies": b._studies},
        "ml": {"n_samples": r.n_samples, "seed": r.seed, "dataset": r.dataset,
               "models": r.models, "detector": r.detector,
               "reference_dataset": r.reference_dataset, "history": r.history},
        "replay": {"truth": h._truth, "model": h._model},
        "mpc": _mpc_identifications(),
        "validation": _validation_runs(),
    }
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(blob, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(p)                      # atomic, so a half-written cache is never loaded
    return p


# ------------------------------------------------------------------------------- load
def load_cache() -> bool:
    """Restore the trained layers. Returns True when the service is fully warm."""
    p = cache_path()
    if not p.exists():
        log.info(f"no warm cache at {p} — layers will be built on demand")
        return False
    try:
        t0 = time.time()
        with open(p, "rb") as fh:
            blob = pickle.load(fh)
        if blob.get("fingerprint") != fingerprint():
            log.warning(f"warm cache {p.name} does not match this build — ignoring it")
            return False

        from app.hybrid.builder import get_builder
        from app.ml.registry import get_registry

        b, r = get_builder(), get_registry()
        h = blob["hybrid"]
        with b._lock:
            b.n, b.seed = h["n"], h["seed"]
            b._ds, b._cache, b._studies = h["ds"], h["cache"], h["studies"]
        rp = blob.get("replay")
        if rp:
            from app.services.historian_service import get_historian
            hist = get_historian()
            hist._truth.update(rp["truth"])
            hist._model.update(rp["model"])

        mp = blob.get("mpc")
        if mp:
            from app.services.mpc_service import get_mpc_service
            ms = get_mpc_service()
            with ms._lock:
                ms._ident.update(mp)

        v = blob.get("validation")
        if v:
            from app.services.validation_service import get_validation_service
            vs = get_validation_service()
            with vs._lock:
                vs._runs.update(v["runs"])
                vs._last.update(v["last"])

        m = blob["ml"]
        with r._lock:
            r.n_samples, r.seed = m["n_samples"], m["seed"]
            r.dataset, r.models, r.detector = m["dataset"], m["models"], m["detector"]
            r.reference_dataset, r.history = m["reference_dataset"], m["history"]

        log.info(f"warm cache loaded in {time.time() - t0:.2f}s "
                 f"({p.stat().st_size / 1e6:.1f} MB, built {blob.get('written_utc')}): "
                 f"{len(h['cache'])} hybrid models, {len(m['models'])} ML models, "
                 f"{len(rp['truth']) if rp else 0} replay nodes, "
                 f"{len(mp) if mp else 0} MPC identifications, "
                 f"{len(v['runs']) if v else 0} validation runs")
        return True
    except Exception:  # noqa: BLE001 — a bad cache must never stop the service
        log.exception(f"warm cache {p.name} could not be loaded — building on demand instead")
        return False


def cache_status() -> dict[str, Any]:
    p = cache_path()
    return {"path": str(p), "exists": p.exists(), "fingerprint": fingerprint(),
            "size_mb": round(p.stat().st_size / 1e6, 2) if p.exists() else None,
            "note": "Built by scripts/precompute.py during the deploy. Absent, the hybrid and "
                    "ML layers build on first use instead, which is slow on a small instance."}
