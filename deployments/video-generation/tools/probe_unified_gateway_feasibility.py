#!/usr/bin/env python3
"""Probe the deployed Bifrost binary with CPU-only fake chat/video providers.

Own ports, databases, credentials and synthetic prices only. Never contacts a
production model, changes live routing, or writes to the production databases.
"""

import email.parser
import email.policy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    directory = ROOT / "outputs/unified-gateway-research-20261125"
    directory.mkdir(parents=True, exist_ok=True)
    data = directory / ("fixture-" + uuid.uuid4().hex[:8])
    data.mkdir(mode=0o700)
    output = ROOT / "deployment/video-queue/unified-gateway-feasibility-probe-20261125.json"
    report = {"status": "running", "scope": "Exact installed Bifrost binary with CPU loopback fake providers; no production migration or GPU/model test",
              "isolation": isolation, "production_settings_changed": False, "production_model_contacted": False,
              "production_database_written": False, "checks": [], "mock_prices_are_not_production_prices": True}

    def save():
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(output)

    save()
    seen, jobs = [], {}
    chat_release = threading.Event()

    class Backend(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def respond(self, body, code=200, content_type="application/json"):
            body = json.dumps(body).encode() if not isinstance(body, bytes) else body
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if "multipart/form-data" in self.headers.get("Content-Type", ""):
                msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                    ("Content-Type: " + self.headers["Content-Type"] + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body)
                payload = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True).decode()
                           for p in msg.iter_parts()}
            else:
                payload = json.loads(body)
            seen.append({"path": self.path, "fields": payload})
            if self.path == "/v1/videos":
                job = "video_cpu_" + uuid.uuid4().hex
                jobs[job] = {"model": payload["model"], "created": int(time.time()), "polls": 0,
                             "fail": payload.get("prompt") == "cpu-failure",
                             "reported_cost": payload.get("prompt") == "cpu-reported-cost"}
                self.respond({"id": job, "object": "video", "model": payload["model"], "created_at": int(time.time()),
                              "status": "queued", "progress": 0, "seconds": "5", "size": payload.get("size")})
            elif self.path == "/v1/chat/completions":
                if payload["messages"][-1]["content"] == "async-cpu":
                    if not chat_release.wait(15):
                        self.respond({"error": {"message": "CPU async fixture timed out"}}, 500)
                        return
                self.respond({"id": "chatcmpl-cpu", "object": "chat.completion", "created": int(time.time()), "model": payload["model"],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "CPU fixture only"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}})
            else:
                self.respond({"error": {"message": "unsupported fixture route"}}, 404)

        def do_GET(self):
            if self.path.startswith("/v1/videos/") and not self.path.endswith("/content"):
                job = self.path.rsplit("/", 1)[-1]
                if job not in jobs:
                    self.respond({"error": {"message": "unknown fixture job"}}, 404)
                    return
                state = jobs[job]
                state["polls"] += 1
                # Keep this queued long enough to inspect the unbilled submission.
                terminal = state.get("release", False)
                status = ("failed" if state["fail"] else "completed") if terminal else "in_progress"
                response = {"id": job, "object": "video", "model": state["model"], "created_at": state["created"],
                            "status": status, "progress": 100 if terminal else 10, "seconds": "5", "size": "3840x2160"}
                if status == "failed": response["error"] = {"code": "fixture_failure", "message": "CPU fixture failure"}
                if status == "completed": response["completed_at"] = int(time.time())
                if status == "completed" and state["reported_cost"]:
                    response["usage"] = {"cost": {"input_cost": 0.0, "output_cost": 0.123, "total_cost": 0.123}}
                self.respond(response)
            elif self.path.endswith("/content"):
                self.respond(b"CPU_FIXTURE_NOT_REAL_VIDEO", content_type="video/mp4")
            elif self.path == "/v1/models":
                self.respond({"object": "list", "data": [{"id": name, "object": "model"} for name in ("probe-chat", "probe-video")]})
            else:
                self.respond({"status": "ok"})

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    backend.daemon_threads = True
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    port = free_port()
    assert port not in {8000, 8001, 8002, 8003, 8004, 8080, 8081, 8090}
    credentials = {"username": "cpu-feasibility", "password": uuid.uuid4().hex}
    auth = {"is_enabled": True, "admin_username": credentials["username"], "admin_password": credentials["password"]}
    config = {"client": {"initial_pool_size": 4, "drop_excess_requests": False, "enable_logging": True,
                         "disable_content_logging": False, "enforce_auth_on_inference": False},
              "providers": {"openai": {"keys": [{"id": str(uuid.uuid4()), "name": "CPU-only fake provider", "value": "not-a-real-key", "models": ["*"], "weight": 1.0}],
                "network_config": {"base_url": f"http://127.0.0.1:{backend.server_port}", "default_request_timeout_in_seconds": 30,
                                   "stream_idle_timeout_in_seconds": 30, "max_retries": 0},
                "concurrency_and_buffer_size": {"concurrency": 4, "buffer_size": 16}}},
              "auth_config": auth, "governance": {"auth_config": auth, "pricing_overrides": [
                {"id": str(uuid.uuid4()), "name": "Synthetic video rate for CPU test only", "scope_kind": "global", "match_type": "exact", "pattern": "probe-video",
                 "request_types": ["video_generation"], "pricing_patch": json.dumps({"output_cost_per_video_per_second": 0.01, "output_cost_per_video_per_second_4k": 0.02})}]},
              "logs_store": {"enabled": True, "type": "sqlite", "config": {"path": str(data / "logs.db")}}, "source_of_truth": "config.json"}
    (data / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (data / "config.json").chmod(0o600)
    binary = ROOT / "llm-lab/deployment/bifrost-lan/bin/bifrost-http-v2.3.2"
    report["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    session = requests.Session(); session.trust_env = False
    base = f"http://127.0.0.1:{port}"
    log = (data / "bifrost.log").open("wb")
    proc = subprocess.Popen([str(binary), "-host", "127.0.0.1", "-port", str(port), "-app-dir", str(data), "-log-level", "warn"],
                            stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "GOMAXPROCS": "2", "GOMEMLIMIT": "384MiB"})

    def wait_until(fn, seconds=40):
        deadline, error = time.monotonic() + seconds, None
        while time.monotonic() < deadline:
            assert proc.poll() is None, "Fixture Bifrost exited"
            try:
                value = fn()
                if value: return value
            except (requests.RequestException, sqlite3.Error, ValueError) as caught: error = repr(caught)
            time.sleep(0.2)
        raise TimeoutError(error)

    def rows():
        with sqlite3.connect(f"file:{data / 'logs.db'}?mode=ro", uri=True, timeout=3) as db:
            return [{"object_type": kind, "cost": cost, "video_debug": json.loads(debug) if debug else None}
                    for kind, cost, debug in db.execute("SELECT object_type,cost,video_debug FROM logs WHERE model='probe-video'")]

    def settlements():
        return [r for r in rows() if (r["video_debug"] or {}).get("accounting") is not None]

    try:
        wait_until(lambda: session.get(base + "/health", timeout=1).status_code == 200)
        response = session.post(base + "/api/session/login", json=credentials, timeout=5); response.raise_for_status()
        response = session.post(base + "/v1/chat/completions", json={"model": "openai/probe-chat", "messages": [{"role": "user", "content": "CPU protocol fixture"}], "max_tokens": 8}, timeout=10)
        response.raise_for_status(); assert response.json()["usage"]["total_tokens"] == 13
        report["checks"].append({"name": "chat_and_video_share_same_installed_gateway", "passed": True})
        response = session.post(base + "/v1/async/chat/completions", json={"model": "openai/probe-chat", "messages": [{"role": "user", "content": "async-cpu"}], "max_tokens": 8}, timeout=10)
        assert response.status_code == 202, response.text
        async_id = response.json()["id"]
        response = session.get(base + "/v1/async/chat/completions/" + async_id, timeout=5)
        assert response.status_code == 202 and response.json()["status"] in {"pending", "processing"}
        chat_release.set()
        def async_finished():
            r = session.get(base + "/v1/async/chat/completions/" + async_id, timeout=5)
            return r.json() if r.status_code == 200 and r.json().get("status") == "completed" else None
        async_result = wait_until(async_finished)
        assert async_result["result"]["choices"][0]["message"]["content"] == "CPU fixture only"
        assert len([r for r in seen if r["path"] == "/v1/chat/completions" and r["fields"]["messages"][-1]["content"] == "async-cpu"]) == 1
        report["checks"].append({"name": "native_async_chat_returns_202_and_result_without_duplicate_model_call", "passed": True})
        for number, label in enumerate(("cpu-success", "cpu-failure", "cpu-reported-cost"), 1):
            fail = label == "cpu-failure"
            response = session.post(base + "/v1/videos", json={"model": "openai/probe-video", "prompt": label,
                "seconds": "5", "size": "3840x2160", "image_reference": [{"file_id": "synthetic_image"}],
                "input_video": {"file_id": "synthetic_video"}, "sampler": "up3"}, headers={"x-bf-passthrough-extra-params": "true"}, timeout=10)
            response.raise_for_status(); submitted = response.json(); video_id = submitted["id"]
            job = next(reversed(jobs)); assert job in video_id
            actual = [r for r in seen if r["path"] == "/v1/videos"][-1]["fields"]
            if number == 1:
                report["video_adapter_observation"] = {"requested_size": "3840x2160", "actual_provider_size": actual.get("size"),
                    "provider_fields": sorted(actual), "references_preserved": "image_reference" in actual,
                    "input_video_preserved": "input_video" in actual, "sampler_preserved": "sampler" in actual,
                    "native_id_has_provider_suffix": video_id.endswith(":openai")}
                wait_until(lambda: len(rows()) > 0)
                assert not settlements(), "Queued submission was billed"
                report["checks"].append({"name": "queued_video_submission_unbilled", "passed": True})
            jobs[job]["release"] = True
            for _ in range(3):
                response = session.get(base + "/v1/videos/" + video_id, timeout=10);response.raise_for_status()
                assert response.json()["status"] == ("failed" if fail else "completed")
            wait_until(lambda: len(settlements()) == number)
            save()
        final_rows = settlements()
        assert len(final_rows) == 3
        costs = sorted(r["cost"] for r in final_rows)
        assert abs(costs[0]) < 1e-10 and abs(costs[1] - 0.1) < 1e-8 and abs(costs[2] - 0.123) < 1e-8, costs
        report["checks"].append({"name": "terminal_resolution_4k_rate_and_failed_zero_cost", "passed": True,
                                  "synthetic_success_cost": costs[1], "synthetic_failure_cost": costs[0]})
        report["checks"].append({"name": "provider_reported_video_cost_can_override_catalog", "passed": True, "synthetic_reported_cost": costs[2]})
        time.sleep(1)
        assert len(settlements()) == 3
        report["checks"].append({"name": "repeated_terminal_polls_do_not_duplicate_settlement", "passed": True})
        response = session.get(base + "/api/logs?limit=20", timeout=10);response.raise_for_status()
        assert "video_retrieve" in response.text and "probe-video" in response.text
        report["checks"].append({"name": "dashboard_log_api_can_read_non_chat_rows", "passed": True})
        report.update(status="passed_cpu_protocol_probe_production_unchanged", settlement_rows=final_rows,
                      completed_at=time.time(), real_video_generated=False,
                      limitations=["Mock jobs and synthetic rates only, no actual GPU queue integration or long-duration timeout validation", "No front-end browser visual acceptance", "No production model or billing configuration changed"])
        save();print(json.dumps({"status": report["status"], "checks": report["checks"], "adapter": report["video_adapter_observation"]}), flush=True)
    except BaseException as error:
        report.update(status="failed_cpu_fixture_evidence_retained", error=type(error).__name__ + ": " + str(error));save();raise
    finally:
        chat_release.set()
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill();proc.wait()
        backend.shutdown();backend.server_close();log.close();session.close()


if __name__ == "__main__":
    main()
