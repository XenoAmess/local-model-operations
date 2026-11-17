#!/usr/bin/env bash
set -euo pipefail
MINIMAX_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export VIDEO_MODEL_NAME=minimax-h3-ref2va
export VIDEO_MODEL_TITLE="MiniMax H3 Ref2VA · 完整 BF16"
export VIDEO_MODEL_STEPS=50
export VIDEO_JOB_TIMEOUT=43200
exec "$MINIMAX_ROOT/start-fasth3-omni-web.sh"
