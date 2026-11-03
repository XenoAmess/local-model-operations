"""Windows output-byte regressions; in-memory SSE only, every socket forbidden."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CALL = load("call_content_bytes_fixture", "scripts/call.py")
AUDIT = load("content_byte_audit_fixture", "scripts/audit_http_evidence.py")
FIXTURE = json.loads((ROOT / "tests/fixtures/call_content_bytes.json").read_bytes())


class Response(io.BytesIO):
    status = 200
    headers = {"Content-Type": "text/event-stream; charset=utf-8"}


def stream(text, finish="stop", done=True):
    def event(value):
        return b"data: " + json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n\n"
    # Each character is a separate delta: CR and LF can cross delta boundaries.
    raw = b"".join(event({"choices": [{"delta": {"content": char}, "finish_reason": None}]})
                   for char in text)
    if finish is not None:
        raw += event({"choices": [{"delta": {}, "finish_reason": finish}]})
    return raw + (b"data: [DONE]\n\n" if done else b"")


class ContentBytesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = copy.deepcopy(CALL.read_json(CALL.DEFAULT_CONFIG))
        self.config["network"] = {"proxy_mode": "environment"}  # Mocked urlopen fixture.
        self.config["base_url"] = "http://offline.invalid/v1"
        self.config["transient_retries"].update(maximum_attempts=2, backoff_seconds=[0], jitter_ratio=0)
        self.spec = self.root / "spec.json"
        self.spec.write_text(json.dumps({"max_tokens": 128, "messages": [
            {"role": "system", "content": "synthetic system"},
            {"role": "user", "content": "synthetic source"},
            {"role": "user", "content": "synthetic task"}]}), encoding="utf-8", newline="\n")
        self.addCleanup(mock.patch.stopall)
        self.network = mock.patch("socket.socket", side_effect=AssertionError("No network allowed")).start()
        mock.patch.dict("os.environ", {"LOCAL_MODEL_API_KEY": ""}).start()

    def dispatch(self, name, responses):
        out = self.root / name
        with mock.patch.object(CALL.urllib.request, "urlopen", side_effect=[Response(r) for r in responses]) as transport, \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = CALL.dispatch(self.spec, name, out, self.config, "synthetic", "synthetic", None)
        self.assertEqual(0, self.network.call_count)
        return code, out, transport

    def events(self, out):
        return [json.loads(line) for line in (out / "EVENTS.jsonl").read_bytes().splitlines()]

    def test_frozen_lf_crlf_unicode_bytes_and_strict_audit_match(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["id"]):
                expected = bytes.fromhex(case["expected_utf8_hex"])
                self.assertEqual(case["bytes"], len(expected))
                self.assertEqual(case["sha256"], hashlib.sha256(expected).hexdigest())
                raw = stream(case["content"])
                code, out, transport = self.dispatch(case["id"], [raw])
                self.assertEqual(0, code)
                self.assertEqual(1, transport.call_count)
                self.assertEqual(raw, (out / "ATTEMPT1-RESPONSE.sse").read_bytes())
                self.assertEqual(expected, (out / "ATTEMPT1-CONTENT.txt").read_bytes())
                report = AUDIT.audit_http(out)
                self.assertEqual([], report["errors"])
                attempt = report["attempts"][0]
                self.assertTrue(attempt["candidate"]["saved_content_matches_stream"])
                self.assertEqual("REVIEW_ELIGIBLE", attempt["candidate"]["eligibility"])
                self.assertEqual("OWNER_REVIEW_REQUIRED", attempt["candidate"]["semantic_review"])

    def test_length_keeps_exact_fragment_without_retry(self):
        fragment = '{"unfinished":\r\n'
        code, out, transport = self.dispatch("length", [stream(fragment, finish="length")])
        self.assertEqual(1, code)
        self.assertEqual(1, transport.call_count)
        self.assertEqual(b'{"unfinished":\r\n', (out / "ATTEMPT1-CONTENT.txt").read_bytes())
        self.assertFalse((out / "ATTEMPT2-RESPONSE.sse").exists())
        self.assertFalse(any(r["event"] == "RETRY_BACKOFF" for r in self.events(out)))
        self.assertEqual("DISCARD_LENGTH", AUDIT.audit_http(out)["attempts"][0]["candidate"]["eligibility"])

    def test_incomplete_retry_retains_unjoined_byte_exact_attempts(self):
        first = '{"discarded":\r\n'
        case = FIXTURE["cases"][2]
        code, out, transport = self.dispatch("retry", [stream(first, finish=None, done=False), stream(case["content"])])
        self.assertEqual(0, code)
        self.assertEqual(2, transport.call_count)
        self.assertEqual(transport.call_args_list[0].args[0].data, transport.call_args_list[1].args[0].data)
        self.assertEqual(b'{"discarded":\r\n', (out / "ATTEMPT1-CONTENT.txt").read_bytes())
        self.assertEqual(bytes.fromhex(case["expected_utf8_hex"]), (out / "ATTEMPT2-CONTENT.txt").read_bytes())
        summary = CALL.read_json(out / "SUMMARY.json")
        self.assertEqual(2, len(summary["attempts"]))
        self.assertFalse(summary["attempts"][0]["sse_done"])
        self.assertTrue(summary["attempts"][1]["candidate_complete"])
        self.assertEqual(1, sum(r["event"] == "RETRY_BACKOFF" for r in self.events(out)))

    def test_content_local_write_error_does_not_retry_transport(self):
        out = self.root / "local-error"
        original = Path.open
        def fail_content(path, *args, **kwargs):
            if path.name == "ATTEMPT1-CONTENT.txt":
                raise PermissionError("Synthetic local evidence fault")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "open", fail_content), \
                mock.patch.object(CALL.urllib.request, "urlopen", return_value=Response(stream('{}\n'))) as transport, \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(CALL.LocalEvidenceIOError):
                CALL.dispatch(self.spec, "local-error", out, self.config, "synthetic", "synthetic", None)
        self.assertEqual(0, self.network.call_count)
        self.assertEqual(1, transport.call_count)
        self.assertFalse((out / "ATTEMPT2-RESPONSE.sse").exists())
        self.assertFalse((out / "SUMMARY.json").exists())
        self.assertFalse(any(r["event"] == "RETRY_BACKOFF" for r in self.events(out)))


if __name__ == "__main__":
    unittest.main()
