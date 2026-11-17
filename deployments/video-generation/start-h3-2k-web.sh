#!/usr/bin/env bash
set -euo pipefail
H3_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export VIDEO_MODEL_NAME=minimax-h3-2k
export VIDEO_MODEL_TITLE="本地 H3 · 2K 视频生成"
export VIDEO_MODEL_STEPS=50 VIDEO_OUTPUT_2K=1 VIDEO_JOB_TIMEOUT=43200
exec "$H3_ROOT/start-fasth3-omni-web.sh"
