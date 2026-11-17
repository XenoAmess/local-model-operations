#!/usr/bin/env bash
set -euo pipefail
H3_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
cd "$H3_ROOT"
exec "$H3_ROOT/.venv-h3-2k/bin/python" "$H3_ROOT/tools/serve_h3_2k_http.py"
