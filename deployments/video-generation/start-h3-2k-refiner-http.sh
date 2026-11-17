#!/usr/bin/env bash
set -euo pipefail
VIDEO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export VIDEO_HTTP_MODEL=open-h3-2k VIDEO_HTTP_PORT=8002
exec "$VIDEO_ROOT/start-video-http.sh"
