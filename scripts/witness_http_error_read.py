"""New synthetic witnesses for real call.dispatch; never open a socket or run preflight."""
import argparse
import ast
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = None
RESULT_ROOT = None
OBSERVATIONS = {}


class BrokenBody(io.BytesIO):
    def __init__(self, fault):
        super().__init__(b"")
        self.fault = fault

    def read(self, *args, **kwargs):
        raise self.fault()


class CompleteSSE:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        chunk = {"choices": [{"delta": {"content": '{"fresh":true}'},
                              "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
        yield ("data: " + json.dumps(chunk) + "\n\n").encode()
        yield b"data: [DONE]\n\n"


class HTTPErrorReadWitness(unittest.TestCase):
    def setUp(self):
        name = "offline_call_" + self._testMethodName
        spec = importlib.util.spec_from_file_location(name, SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.directory = RESULT_ROOT / self._testMethodName
        self.directory.mkdir(parents=True, exist_ok=False)
        self.request_path = self.directory / "synthetic-request.json"
        self.request_path.write_text(json.dumps({
            "messages": [{"role": "system", "content": "synthetic offline system"},
                         {"role": "user", "content": "synthetic source DATA"},
                         {"role": "user", "content": "synthetic task DATA"}],
            "max_tokens": 8}), encoding="utf-8")
        self.out = self.directory / "synthetic-evidence"
        self.config = {
            "model": "offline-synthetic-model", "base_url": "http://offline.invalid/v1",
            "defaults": {"max_tokens": 8},
            "prompting": {"system_template": "synthetic offline system"},
            "transient_retries": {"maximum_attempts": 6,
                "retry_http_statuses": [408, 429, 500, 502, 503, 504],
                "backoff_seconds": [1, 2, 4, 8, 16], "jitter_ratio": 0},
            "authentication": {"api_key_env": None, "required": False},
            "timeouts": {"read_seconds": 1, "total_seconds": 10}}
        self.requests = []
        self.stdout, self.stderr = io.StringIO(), io.StringIO()

    def error(self, status, fault=None):
        body = BrokenBody(fault) if fault else io.BytesIO(b"synthetic diagnostic body")
        return self.module.urllib.error.HTTPError(
            "http://offline.invalid/v1/chat/completions", status,
            "synthetic HTTP error", {}, body)

    def execute(self, response, *, fail_local_body_write=False):
        m = self.module
        def fake_open(request, timeout):
            self.requests.append(request.data)
            value = response(len(self.requests))
            if isinstance(value, BaseException):
                raise value
            return value
        original_write = Path.write_bytes
        def write_bytes(path, data):
            if fail_local_body_write and path.name == "ATTEMPT1-HTTP-ERROR.txt":
                raise OSError("synthetic local diagnostic sink unavailable")
            return original_write(path, data)
        try:
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(m, "network_transport", return_value=(
                    fake_open, {"proxy_mode": "SYNTHETIC_NO_NETWORK",
                                "actual_peer": "NOT_APPLICABLE"})))
                for target, attr in ((m.urllib.request, "urlopen"),
                                     (m.urllib.request, "build_opener"),
                                     (m.socket, "socket"), (subprocess, "Popen"),
                                     (m, "client_preflight")):
                    stack.enter_context(mock.patch.object(target, attr,
                        side_effect=AssertionError("forbidden network/process/maintenance call")))
                self.sleep = stack.enter_context(mock.patch.object(m.time, "sleep"))
                if fail_local_body_write:
                    stack.enter_context(mock.patch.object(Path, "write_bytes", new=write_bytes))
                stack.enter_context(redirect_stdout(self.stdout))
                stack.enter_context(redirect_stderr(self.stderr))
                return m.dispatch(self.request_path, self._testMethodName, self.out,
                                  self.config, "synthetic-no-network", "offline-witness", None)
        finally:
            (self.directory / "captured-stdout.txt").write_text(self.stdout.getvalue(), encoding="utf-8")
            (self.directory / "captured-stderr.txt").write_text(self.stderr.getvalue(), encoding="utf-8")
            events = self.events()
            OBSERVATIONS[self._testMethodName] = {
                "synthetic_opener_calls": len(self.requests), "actual_http_calls": 0,
                "synthetic_sleep_calls": self.sleep.call_count,
                "event_types": [event["event"] for event in events],
                "summary_exists": (self.out / "SUMMARY.json").exists(),
                "request_bodies_identical": all(value == self.requests[0] for value in self.requests),
                "preflight_executed": False, "directory": str(self.directory)}

    def events(self):
        path = self.out / "EVENTS.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def receipts(self, attempts, *, local=False, success=False):
        summary = json.loads((self.out / "SUMMARY.json").read_text(encoding="utf-8"))
        self.assertEqual(success, summary["success"])
        self.assertFalse(summary["adopted"])
        self.assertEqual(attempts, len(summary["attempts"]))
        ends = [row for row in self.events() if row["event"] == "ATTEMPT_END"]
        self.assertEqual(attempts, len(ends))
        saved_request = (self.out / "REQUEST.json").read_bytes()
        self.assertEqual([saved_request] * attempts, self.requests)
        for number, row in enumerate(summary["attempts"], 1):
            self.assertEqual(number, row["attempt"])
            self.assertEqual(local, row["local_evidence_io_failure"])
            self.assertFalse(row["adopted"])
            actual = json.loads((self.out / f"ATTEMPT{number}-RESULT.json").read_text(encoding="utf-8"))
            self.assertEqual(row, actual)
            self.assertEqual(row["failure"], ends[number - 1]["failure"])
        return summary["attempts"]

    def test_503_body_oserror_finalizes_six_full_attempts(self):
        code = self.execute(lambda _: self.error(503, lambda: OSError("synthetic body read failed")))
        self.assertEqual(1, code)
        rows = self.receipts(6)
        self.assertEqual(5, self.sleep.call_count)
        self.assertEqual([1, 2, 4, 8, 16], [call.args[0] for call in self.sleep.call_args_list])
        for number, row in enumerate(rows, 1):
            self.assertEqual(503, row["http_status"])
            self.assertIn("HTTPError", row["failure"])
            self.assertIn("synthetic body read failed", row["failure"])
            self.assertFalse(row["candidate_complete"])
            self.assertFalse(row["sse_done"])
            self.assertFalse((self.out / f"ATTEMPT{number}-HTTP-ERROR.txt").exists())
            self.assertEqual(b"", (self.out / f"ATTEMPT{number}-CONTENT.txt").read_bytes())

    def test_400_body_oserror_stops_after_one_finalized_attempt(self):
        code = self.execute(lambda _: self.error(400, lambda: OSError("synthetic body read failed")))
        self.assertEqual(1, code)
        row = self.receipts(1)[0]
        self.assertEqual(400, row["http_status"])
        self.assertIn("synthetic body read failed", row["failure"])
        self.sleep.assert_not_called()
        self.assertFalse((self.out / "ATTEMPT1-HTTP-ERROR.txt").exists())

    def test_reader_local_evidence_error_is_not_network_retry(self):
        fault = lambda: self.module.LocalEvidenceIOError("synthetic explicit local evidence failure")
        code = self.execute(lambda _: self.error(503, fault))
        self.assertEqual(1, code)
        row = self.receipts(1, local=True)[0]
        self.assertEqual(503, row["http_status"])
        self.assertIn("synthetic explicit local evidence failure", row["failure"])
        self.sleep.assert_not_called()

    def test_local_diagnostic_write_oserror_is_not_network_retry(self):
        code = self.execute(lambda _: self.error(503), fail_local_body_write=True)
        self.assertEqual(1, code)
        row = self.receipts(1, local=True)[0]
        self.assertIn("writing ATTEMPT1-HTTP-ERROR.txt", row["failure"])
        self.assertIn("synthetic local diagnostic sink unavailable", row["failure"])
        self.sleep.assert_not_called()

    def test_incomplete_error_body_then_success_uses_fresh_complete_candidate(self):
        def response(attempt):
            if attempt == 1:
                return self.error(503, lambda: http.client.IncompleteRead(b"UNADOPTED_PARTIAL", 20))
            return CompleteSSE()
        code = self.execute(response)
        self.assertEqual(0, code)
        first, second = self.receipts(2, success=True)
        self.assertEqual(503, first["http_status"])
        self.assertIn("IncompleteRead", first["failure"])
        self.assertFalse(first["candidate_complete"])
        self.assertEqual(b"", (self.out / "ATTEMPT1-CONTENT.txt").read_bytes())
        self.assertFalse((self.out / "ATTEMPT1-HTTP-ERROR.txt").exists())
        self.assertIsNone(second["failure"])
        self.assertTrue(second["candidate_complete"])
        self.assertEqual("VALID", second["json_syntax"]["status"])
        self.assertEqual('{"fresh":true}', (self.out / "ATTEMPT2-CONTENT.txt").read_text(encoding="utf-8"))
        self.assertEqual(1, self.sleep.call_count)


def main():
    global SOURCE, RESULT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("cases", nargs="*")
    args = parser.parse_args()
    SOURCE, RESULT_ROOT = Path(args.source).resolve(), Path(args.result_dir).resolve()
    for path in (SOURCE, RESULT_ROOT):
        if not path.is_relative_to(ROOT):
            raise ValueError("Offline witness paths must remain within the exclusive D root")
    RESULT_ROOT.mkdir(parents=True, exist_ok=False)
    raw = SOURCE.read_bytes()
    ast.parse(raw, filename=str(SOURCE))
    ast.parse(Path(__file__).read_bytes(), filename=__file__)
    names = args.cases or unittest.defaultTestLoader.getTestCaseNames(HTTPErrorReadWitness)
    suite = unittest.TestSuite(HTTPErrorReadWitness(name) for name in names)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    (RESULT_ROOT / "unittest.txt").write_text(output.getvalue(), encoding="utf-8")
    record = {"source": str(SOURCE), "source_sha256": hashlib.sha256(raw).hexdigest(),
              "python_version": sys.version, "ast_parse": "PASS",
              "tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "successful": result.wasSuccessful(),
              "cases": names, "synthetic_observations": OBSERVATIONS,
              "actual_http_calls": 0, "maintenance_calls": 0, "business_actions": 0,
              "tracebacks": [{"test": str(test), "traceback": text}
                             for test, text in result.failures + result.errors]}
    (RESULT_ROOT / "RESULT.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in record.items()
                      if key not in ("tracebacks", "synthetic_observations")}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
