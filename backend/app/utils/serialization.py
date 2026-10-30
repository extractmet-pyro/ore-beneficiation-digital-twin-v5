"""JSON serialisation helpers: numpy-aware responses.

The twin returns numpy scalars in many places (recoveries, tonnages, boolean flags). Rather than
casting at every call site, the API uses a response class that knows how to encode them.
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
from fastapi.responses import JSONResponse


def to_native(obj: Any) -> Any:
    """Recursively convert numpy / non-finite values into JSON-native Python types."""
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, np.ndarray):
        return [to_native(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_native(v) for v in obj]
    return obj


class NumpyJSONResponse(JSONResponse):
    """JSON response that encodes numpy scalars, arrays and NaN/Inf safely."""

    def render(self, content: Any) -> bytes:  # noqa: ANN401
        return json.dumps(to_native(content), ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
