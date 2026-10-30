#!/usr/bin/env bash
# Local / container start script. Render uses the startCommand in render.yaml.
set -euo pipefail
cd "$(dirname "$0")"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-1}" --timeout-keep-alive 120
