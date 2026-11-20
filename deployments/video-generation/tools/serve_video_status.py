#!/usr/bin/env python3
"""Always-readable LAN status on port 8004; never loads or migrates a model."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from video_service_state import status_from_database

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("VIDEO_QUEUE_DATA", ROOT / "outputs/video-queue"))


def snapshot():
    value = status_from_database(DATA)
    endpoints = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in (8001, 8002):
        try:
            with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                health = json.load(response)
            endpoints.append({"port": port, "http_available": True, "model": health.get("model")})
        except (OSError, ValueError, urllib.error.URLError):
            endpoints.append({"port": port, "http_available": False})
    value["endpoints"] = endpoints
    if not all(item["http_available"] for item in endpoints):
        value.update(ready=False, accepting_jobs=False, retry_after_seconds=30)
        if value["status"] not in {"draining", "upgrading"}:
            value["status"] = "degraded"
    return value


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] not in {"/health", "/ready", "/v1/service/status"}:
            self.send_error(404)
            return
        value = snapshot()
        code = 503 if self.path.split("?", 1)[0] == "/ready" and not value["ready"] else 200
        data = (json.dumps(value, ensure_ascii=False) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if code == 503:
            self.send_header("Retry-After", "30")
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("VIDEO_STATUS_PORT", "8004"))), Handler).serve_forever()
