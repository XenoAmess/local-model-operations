#!/usr/bin/env bash
set -euo pipefail
VIDEO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
cd "$VIDEO_ROOT"
exec "$VIDEO_ROOT/.venv-h3-2k/bin/python" "$VIDEO_ROOT/tools/serve_video_http.py"
