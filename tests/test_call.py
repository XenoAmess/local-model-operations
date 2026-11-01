"""Offline contract tests: local HTTP/SSE only, no model service or business data."""
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "call.py"
spec = importlib.util.spec_from_file_location("portable_call", SCRIPT)
call = importlib.util.module_from_spec(spec)
spec.loader.exec_module(call)


def data(value):
    return b"data: " + json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n\n"


def delta(value):
    return data({"choices": [{"delta": value, "finish_reason": None}]})


def complete(content='{"ok":true}', usage=None, finish="stop"):
    result = delta({"content": content})
    result += data({"choices": [{"delta": {}, "finish_reason": finish}]})
    if usage is not None:
        result += data({"choices": [], "usage": usage})
    return result + b"data: [DONE]\n\n"


@contextmanager
def server(responses):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
            response = responses[min(len(requests) - 1, len(responses) - 1)]
            parts = response.get("parts", [response.get("body", complete())])
            self.send_response(response.get("status", 200))
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(sum(len(p) for p in parts) + response.get("missing", 0)))
            self.send_header("Connection", "close")
            self.end_headers()
            for part in parts:
                try:
                    self.wfile.write(part)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(response.get("delay", 0))
            self.close_connection = True

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(httpd.server_port) + "/v1", requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


class CallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = copy.deepcopy(call.read_json(call.DEFAULT_CONFIG))
        self.config["transient_retries"]["backoff_seconds"] = [0] * 5
        self.config["transient_retries"]["jitter_ratio"] = 0
        self.config["timeouts"] = {"read_seconds": 2, "total_seconds": 5}
        source = self.root / "materials"
        source.mkdir()
        (source / "source.txt").write_text("public class Sample { }\n", encoding="utf-8")
        (source / "task.txt").write_text("Return a JSON review; do not run code.\n", encoding="utf-8")
        self.request = source / "task.json"
        call.save_json(self.request, {"source_files": ["source.txt"], "task_path": "task.txt", "max_tokens": 100})

    def dispatch(self, base_url, name="one", stop=None):
        self.config["base_url"] = base_url
        out = self.root / name
        with mock.patch.dict(os.environ, {"LOCAL_MODEL_API_KEY": ""}), redirect_stdout(io.StringIO()):
            code = call.dispatch(self.request, name, out, self.config, "test-machine", "test-owner", stop)
        return code, out

    def test_tcp_split_utf8_nonempty_content_ttft_and_null_usage(self):
        content = '{"answer":"你好"}'
        token = delta({"content": content})
        split = token.index("你".encode("utf-8")) + 1
        prefix = delta({"role": "assistant"}) + delta({"reasoning_content": "thinking"}) + delta({"content": ""})
        suffix = data({"choices": [{"delta": {}, "finish_reason": "stop"}]}) + b"data: [DONE]\n\n"
        parts = [prefix, token[:split], token[split:], suffix]
        with server([{"parts": parts, "delay": 0.01}]) as (url, requests):
            code, out = self.dispatch(url)
        self.assertEqual(code, 0)
        result = call.read_json(out / "ATTEMPT1-RESULT.json")
        self.assertEqual((out / "ATTEMPT1-CONTENT.txt").read_text(encoding="utf-8"), content)
        self.assertEqual((out / "ATTEMPT1-RESPONSE.sse").read_bytes(), b"".join(parts))
        self.assertIsNone(result["usage"])
        self.assertIsNone(result["cached_prompt_tokens_if_reported"])
        self.assertLess(result["http_headers_ms"], result["first_nonempty_content_delta_ms"])
        self.assertLess(result["first_nonempty_reasoning_delta_ms"], result["first_nonempty_content_delta_ms"])
        self.assertGreaterEqual(result["total_ms"], result["first_nonempty_content_delta_ms"])
        self.assertEqual(requests[0]["path"], "/v1/chat/completions")
        events = [json.loads(line) for line in (out / "EVENTS.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(e["event"] == "FIRST_CONTENT" for e in events), 1)

    def test_reported_usage_and_cached_tokens(self):
        usage = {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12,
                 "prompt_tokens_details": {"cached_tokens": 7}}
        with server([{"body": complete(usage=usage)}]) as (url, _):
            code, out = self.dispatch(url)
        self.assertEqual(code, 0)
        result = call.read_json(out / "ATTEMPT1-RESULT.json")
        self.assertEqual(result["usage"], usage)
        self.assertEqual(result["cached_prompt_tokens_if_reported"], 7)

    def test_usage_details_missing_or_null_remain_unknown(self):
        for name, usage in [("missing-details", {"prompt_tokens": 9}),
                            ("null-details", {"prompt_tokens_details": None})]:
            with self.subTest(name=name), server([{"body": complete(usage=usage)}]) as (url, _):
                code, out = self.dispatch(url, name=name)
            self.assertEqual(code, 0)
            self.assertEqual(call.read_json(out / "ATTEMPT1-RESULT.json")["usage"], usage)
            self.assertIsNone(call.read_json(out / "ATTEMPT1-RESULT.json")["cached_prompt_tokens_if_reported"])

    def test_partial_reset_retries_whole_request_without_splicing(self):
        partial = delta({"content": '{"discarded":'})
        final = '{"second":2}'
        with server([{"body": partial, "missing": 20}, {"body": complete(final)}]) as (url, requests):
            code, out = self.dispatch(url)
        self.assertEqual(code, 0)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["body"], requests[1]["body"])
        self.assertEqual((out / "ATTEMPT1-CONTENT.txt").read_text(), '{"discarded":')
        self.assertEqual((out / "ATTEMPT2-CONTENT.txt").read_text(), final)
        first = call.read_json(out / "ATTEMPT1-RESULT.json")
        self.assertFalse(first["candidate_complete"])
        self.assertFalse(first["sse_done"])
        self.assertIsNotNone(first["failure"])
        self.assertFalse(first["adopted"])
        self.assertEqual(len(call.read_json(out / "SUMMARY.json")["attempts"]), 2)

    def test_truncated_json_or_utf8_tail_without_lf_retries_whole_stream(self):
        tails = {
            "json-tail": b'data: {"choices":[{"delta":{"content":"unfinished',
            "utf8-tail": b'data: {"choices":[{"delta":{"content":"' + "你".encode("utf-8")[:2],
        }
        for name, tail in tails.items():
            with self.subTest(name=name):
                partial = delta({"content": '{"discarded":'}) + tail
                final = json.dumps({"second": name})
                with server([{"body": partial, "missing": 17},
                             {"body": complete(final)}]) as (url, requests):
                    code, out = self.dispatch(url, name=name)
                self.assertEqual(code, 0)
                self.assertEqual(len(requests), 2)
                self.assertEqual(requests[0]["body"], requests[1]["body"])
                self.assertEqual((out / "ATTEMPT1-RESPONSE.sse").read_bytes(), partial)
                self.assertEqual((out / "ATTEMPT1-CONTENT.txt").read_text(), '{"discarded":')
                self.assertEqual((out / "ATTEMPT2-CONTENT.txt").read_text(), final)
                first = call.read_json(out / "ATTEMPT1-RESULT.json")
                self.assertIn("IncompleteRead", first["failure"])
                self.assertFalse(first["candidate_complete"])
                self.assertFalse(first["sse_done"])

    def test_complete_malformed_json_event_does_not_retry(self):
        body = delta({"content": '{"discarded":'}) + b'data: {"choices":}\n\n'
        with server([{"body": body}, {"body": complete()}]) as (url, requests):
            code, out = self.dispatch(url)
        self.assertEqual(code, 1)
        self.assertEqual(len(requests), 1)
        first = call.read_json(out / "ATTEMPT1-RESULT.json")
        self.assertIn("JSONDecodeError", first["failure"])
        self.assertNotIn("IncompleteRead", first["failure"])
        self.assertFalse(first["candidate_complete"])

    def test_transient_http_error_retries(self):
        with server([{"status": 503, "body": b"busy"}, {"body": complete()}]) as (url, requests):
            code, out = self.dispatch(url)
        self.assertEqual(code, 0)
        self.assertEqual(len(requests), 2)
        self.assertEqual((out / "ATTEMPT1-HTTP-ERROR.txt").read_bytes(), b"busy")

    def test_sixth_failure_stops_before_nonexistent_sixth_backoff(self):
        with server([{"status": 503, "body": b"busy"}]) as (url, requests):
            code, out = self.dispatch(url)
        self.assertEqual(code, 1)
        self.assertEqual(len(requests), 6)
        summary = call.read_json(out / "SUMMARY.json")
        self.assertEqual(len(summary["attempts"]), 6)
        events = [json.loads(line) for line in (out / "EVENTS.jsonl").read_text().splitlines()]
        self.assertEqual(sum(e["event"] == "RETRY_BACKOFF" for e in events), 5)

    def test_permanent_http_error_does_not_retry(self):
        with server([{"status": 401, "body": b"denied"}]) as (url, requests):
            code, _ = self.dispatch(url)
        self.assertEqual(code, 1)
        self.assertEqual(len(requests), 1)

    def test_length_finish_is_failure_without_transport_retry(self):
        with server([{"body": complete('{"ok":true}', finish="length")}]) as (url, requests):
            code, out = self.dispatch(url)
        self.assertEqual(code, 1)
        self.assertEqual(len(requests), 1)
        self.assertEqual(call.read_json(out / "ATTEMPT1-RESULT.json")["failure"], "finish_reason_length")

    def test_cli_config_override_environment_and_spec_relative_paths(self):
        with server([{"body": complete()}]) as (url, requests):
            self.config["base_url"] = url
            config = self.root / "explicit-config.json"
            call.save_json(config, self.config)
            evidence = self.root / "machine-evidence"
            env = dict(os.environ, LOCAL_MODEL_CONFIG=str(self.root / "nonexistent.json"),
                       LOCAL_MODEL_OUTPUT_ROOT=str(evidence), LOCAL_MODEL_MACHINE_ID="env-machine",
                       LOCAL_MODEL_OWNER="env-owner", LOCAL_MODEL_API_KEY="")
            result = subprocess.run([sys.executable, str(SCRIPT), str(self.request), "cli",
                                     "--config", str(config), "--machine-id", "cli-machine"],
                                    cwd=self.root, env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        out = evidence / "cli"
        self.assertEqual(call.read_json(out / "SUMMARY.json")["machine_id"], "cli-machine")
        self.assertEqual(call.read_json(out / "SUMMARY.json")["owner"], "env-owner")
        actual = json.loads(requests[0]["body"])
        self.assertEqual([m["role"] for m in actual["messages"]], ["system", "user", "user"])
        self.assertEqual(actual["messages"][0]["content"], self.config["prompting"]["system_template"])
        self.assertIn("public class Sample", actual["messages"][1]["content"])
        self.assertEqual(actual["messages"][2]["content"], "Return a JSON review; do not run code.\n")
        self.assertTrue(actual["stream_options"]["include_usage"])

    def test_environment_config_without_flag_and_legacy_output_owner(self):
        with server([{"body": complete()}]) as (url, _):
            self.config["base_url"] = url
            config = self.root / "env-config.json"
            call.save_json(config, self.config)
            out = self.root / "legacy"
            env = dict(os.environ, LOCAL_MODEL_CONFIG=str(config), LOCAL_MODEL_API_KEY="")
            env.pop("LOCAL_MODEL_OWNER", None)
            result = subprocess.run([sys.executable, str(SCRIPT), str(self.request), "legacy",
                                     str(out), "positional-worker"], cwd=self.root, env=env,
                                    capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(call.read_json(out / "SUMMARY.json")["owner"], "positional-worker")

    def test_examples_default_config_and_invalid_budget_without_http(self):
        self.assertEqual(call.DEFAULT_CONFIG, ROOT / "config" / "executor.json")
        request, _ = call.prepare_request(ROOT / "examples" / "task.json", self.config)
        self.assertIn("public final class Greeting", request["messages"][1]["content"])
        for value in (0, 16001, True):
            call.save_json(self.request, {"source_files": ["source.txt"], "task_path": "task.txt", "max_tokens": value})
            with self.assertRaises(ValueError):
                call.prepare_request(self.request, self.config)

    def test_claim_and_existing_events_prevent_request_overwrite(self):
        with server([{"body": complete()}]) as (url, requests):
            code, out = self.dispatch(url)
            original = (out / "REQUEST.json").read_bytes()
            with self.assertRaises(ValueError):
                self.dispatch(url)
        self.assertEqual(code, 0)
        self.assertEqual(len(requests), 1)
        self.assertEqual((out / "REQUEST.json").read_bytes(), original)
        claimed = self.root / "claimed"
        claimed.mkdir()
        (claimed / "DISPATCH.claim").write_text("another owner")
        with self.assertRaises(ValueError):
            call.dispatch(self.request, "claimed", claimed, self.config, "m", "o", None)
        self.assertFalse((claimed / "REQUEST.json").exists())

    def test_stop_file_prevents_post(self):
        stop = self.root / "STOP-NEW-HTTP.json"
        stop.write_text("{}")
        with server([{"body": complete()}]) as (url, requests):
            code, out = self.dispatch(url, stop=stop)
        self.assertEqual(code, 1)
        self.assertEqual(requests, [])
        self.assertEqual(call.read_json(out / "SUMMARY.json")["attempts"], [])


if __name__ == "__main__":
    unittest.main()
