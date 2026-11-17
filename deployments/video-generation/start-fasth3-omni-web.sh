#!/usr/bin/env bash
set -euo pipefail
FASTH3_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export GRADIO_ANALYTICS_ENABLED=False
export GRADIO_TEMP_DIR="$FASTH3_ROOT/omni-web/cache"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2
if [[ "${VIDEO_OUTPUT_2K:-0}" != "1" ]]; then
  export VIDEO_DEFAULT_SIZE="${VIDEO_DEFAULT_SIZE:-1344x768}"
fi
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
cd "$FASTH3_ROOT"
exec "$FASTH3_ROOT/FastVideo/.venv/bin/python" "$FASTH3_ROOT/omni-web/app.py"
