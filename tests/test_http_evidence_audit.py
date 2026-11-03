"""Synthetic offline oracle: no service, business material, or model execution."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "http_audit", Path(__file__).parents[1] / "scripts/audit_http_evidence.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
SECRET = "C:/PRIVATE_CANARY_ROOT/SECRET_TOOL_OUTPUT"


def dump(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def data(value):
    # No space after colon is legal and handled by the current caller.
    return b"data:" + dump(value) + b"\n\n"


def sse(content, finish="stop", done=True):
    raw = data({"choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]})
    raw += data({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    raw += data({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 4}})
    return raw + (b"data:[DONE]\n\n" if done else b"")


def request():
    return {"model": "qwen38-coder", "temperature": 0, "max_tokens": 250,
            "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SECRET},
                         {"role": "user", "content": "source " + SECRET},
                         {"role": "user", "content": "task " + SECRET}]}


def write_case(root, content='{"ok":true}', finish="stop", done=True,
               events=True, result=True, stream=True, saved=None, attempt=1):
    (root / "REQUEST.json").write_bytes(dump(request()))
    prefix = f"ATTEMPT{attempt}"
    if stream:
        (root / (prefix + "-RESPONSE.sse")).write_bytes(sse(content, finish, done))
    (root / (prefix + "-CONTENT.txt")).write_bytes((content if saved is None else saved).encode("utf-8"))
    measured = {"attempt": attempt, "http_status": 200, "http_headers_ms": 5,
                "first_nonempty_content_delta_ms": 9, "total_ms": 23,
                "finish_reason": finish, "sse_done": done, "failure": None,
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
                "content_path": SECRET, "task_id": SECRET}
    if result:
        (root / (prefix + "-RESULT.json")).write_bytes(dump(measured))
    if events:
        rows = [{"event": "POST_BEGIN", "attempt": attempt, "at_utc": "2026-01-01T00:00:00Z", "request_path": SECRET},
                {"event": "HEADERS", "attempt": attempt, "http_headers_ms": 5},
                {"event": "FIRST_CONTENT", "attempt": attempt, "first_nonempty_content_delta_ms": 9},
                dict(measured, event="ATTEMPT_END", at_utc="2026-01-01T00:00:01Z")]
        (root / "EVENTS.jsonl").write_bytes(b"\n".join(map(dump, rows)) + b"\n")


def pins(root):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.iterdir() if p.is_file() and not p.is_symlink()}


class HttpEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def audit(self, **limits):
        before = pins(self.root)
        report = AUDIT.audit_http(self.root, **limits)
        self.assertEqual(before, pins(self.root), "audit must not modify original evidence")
        encoded = json.dumps(report, allow_nan=False)
        self.assertNotIn(SECRET, encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertEqual("OWNER_REVIEW_REQUIRED", report["semantic_review"])
        return report

    def test_valid_wrong_analysis_is_syntax_only(self):
        text = '{"findings":["invented edge"],"limits":[]}'
        write_case(self.root, text)
        report = self.audit()
        self.assertEqual([], report["errors"])
        self.assertTrue(report["request"]["fixed_three_messages"])
        self.assertEqual(hashlib.sha256(("source " + SECRET).encode()).hexdigest(), report["request"]["source_message_sha256"])
        attempt = report["attempts"][0]
        self.assertEqual("VALID", attempt["candidate"]["syntax"])
        self.assertEqual("REVIEW_ELIGIBLE", attempt["candidate"]["eligibility"])
        self.assertEqual("OWNER_REVIEW_REQUIRED", attempt["candidate"]["semantic_review"])
        self.assertNotIn("invented edge", json.dumps(report))
        self.assertEqual(9, attempt["recorded_metrics"]["result"]["first_nonempty_content_delta_ms"])
        self.assertIsNone(attempt["recorded_metrics"]["result"]["usage"]["cached_tokens"])

    def test_length_and_outer_syntax_are_independent(self):
        for content, syntax in [('{"findings":[', "INVALID"), ('{"ok":true}', "VALID")]:
            with self.subTest(content=content):
                write_case(self.root, content, finish="length")
                attempt = self.audit()["attempts"][0]
                self.assertEqual(syntax, attempt["candidate"]["syntax"])
                self.assertEqual("DISCARD_LENGTH", attempt["candidate"]["eligibility"])
                self.assertTrue(attempt["stream"]["complete"])

    def test_valid_final_json_without_result_is_checked(self):
        write_case(self.root, '{"ok":true,"count":2}', result=False)
        attempt = self.audit()["attempts"][0]
        self.assertEqual("VALID", attempt["candidate"]["syntax"])
        self.assertEqual("object", attempt["candidate"]["type"])
        self.assertEqual("UNKNOWN", attempt["recorded_metrics"]["result"]["total_ms"])
        self.assertEqual(23, attempt["recorded_metrics"]["events"]["total_ms"])
        self.assertEqual(12, attempt["stream"]["usage"]["prompt_tokens"])

    def test_missing_events_and_result_do_not_invent_timing(self):
        write_case(self.root, events=False, result=False)
        report = self.audit()
        self.assertEqual("UNKNOWN", report["events"]["parse_complete"])
        attempt = report["attempts"][0]
        self.assertEqual("VALID", attempt["candidate"]["syntax"])
        for source in ("result", "events"):
            self.assertEqual("UNKNOWN", attempt["recorded_metrics"][source]["first_nonempty_content_delta_ms"])
            self.assertEqual("UNKNOWN", attempt["recorded_metrics"][source]["total_ms"])

    def test_content_only_and_empty_present_content(self):
        write_case(self.root, stream=False, result=False, events=False)
        attempt = self.audit()["attempts"][0]
        self.assertEqual("VALID", attempt["candidate"]["syntax"])
        self.assertEqual("UNKNOWN", attempt["candidate"]["eligibility"])
        self.assertEqual("UNKNOWN", attempt["stream"]["complete"])
        (self.root / "ATTEMPT1-CONTENT.txt").write_bytes(b"")
        self.assertEqual("INVALID", self.audit()["attempts"][0]["candidate"]["syntax"])

    def test_missing_done_and_content_conflict_block_eligibility(self):
        write_case(self.root, done=False)
        attempt = self.audit()["attempts"][0]
        self.assertEqual("VALID", attempt["candidate"]["syntax"])
        self.assertFalse(attempt["stream"]["complete"])
        self.assertEqual("NOT_REVIEW_ELIGIBLE", attempt["candidate"]["eligibility"])

    def test_windows_content_projection_is_separate_from_exact_bytes(self):
        text = '{\n  "ok": true\n}'
        write_case(self.root, text, saved=text.replace("\n", "\r\n"))
        attempt = self.audit()["attempts"][0]
        self.assertFalse(attempt["candidate"]["saved_content_matches_stream"])
        self.assertTrue(attempt["candidate"]["saved_content_lf_normalized_matches_stream"])
        self.assertEqual("VALID", attempt["candidate"]["syntax"])
        # A format projection is explicit; it does not erase the raw mismatch.
        self.assertEqual("NOT_REVIEW_ELIGIBLE", attempt["candidate"]["eligibility"])
        write_case(self.root, saved='{"ok":false}')
        attempt = self.audit()["attempts"][0]
        self.assertFalse(attempt["candidate"]["saved_content_matches_stream"])
        self.assertIn("content_stream_mismatch", attempt["discrepancies"])
        self.assertEqual("NOT_REVIEW_ELIGIBLE", attempt["candidate"]["eligibility"])

    def test_corrupt_stream_never_salvages_complete_candidate(self):
        write_case(self.root)
        path = self.root / "ATTEMPT1-RESPONSE.sse"
        valid = path.read_bytes()
        for corruption in [b"data:{bad}\n\n", b"data:\xff\n\n", b"data:[]\n\n"]:
            with self.subTest(corruption=corruption):
                path.write_bytes(corruption + valid)
                attempt = self.audit()["attempts"][0]
                self.assertFalse(attempt["stream"]["complete"])
                self.assertEqual("content", attempt["candidate"]["source"])
                self.assertEqual("NOT_REVIEW_ELIGIBLE", attempt["candidate"]["eligibility"])
        path.write_bytes(valid + data({"choices": []}))
        self.assertIn("data_after_done", self.audit()["attempts"][0]["stream"]["anomalies"])

    def test_metrics_and_finish_conflicts_are_visible(self):
        write_case(self.root)
        path = self.root / "ATTEMPT1-RESULT.json"
        result = json.loads(path.read_bytes())
        result.update(total_ms=99, finish_reason="length", sse_done=False)
        path.write_bytes(dump(result))
        attempt = self.audit()["attempts"][0]
        self.assertEqual(99, attempt["recorded_metrics"]["result"]["total_ms"])
        self.assertEqual(23, attempt["recorded_metrics"]["events"]["total_ms"])
        self.assertIn("result_end_total_ms_conflict", attempt["discrepancies"])
        self.assertIn("stream_result_finish_reason_conflict", attempt["discrepancies"])
        self.assertEqual("DISCARD_LENGTH", attempt["candidate"]["eligibility"])

    def test_json_scalars_nonstandard_constants_and_private_parameters(self):
        for content, syntax, kind in [("null", "VALID", "null"), ("[1,2]", "VALID", "array"),
                                      ('"literal"', "VALID", "string"), ("NaN", "INVALID", "UNKNOWN")]:
            write_case(self.root, content)
            report = self.audit()
            self.assertEqual(syntax, report["attempts"][0]["candidate"]["syntax"])
            self.assertEqual(kind, report["attempts"][0]["candidate"]["type"])
        req = request()
        req.update(model=SECRET, temperature=True, max_tokens=False, response_format={"type": SECRET})
        req["messages"][0]["role"] = SECRET
        (self.root / "REQUEST.json").write_bytes(dump(req))
        params = self.audit()["request"]["parameters"]
        self.assertEqual("UNKNOWN", params["model"])
        self.assertEqual("UNKNOWN", params["temperature"])
        self.assertEqual("UNKNOWN", params["max_tokens"])
        self.assertEqual("UNKNOWN", params["response_format_type"])

    def test_partial_event_log_and_duplicate_lifecycle_stay_unknown(self):
        write_case(self.root)
        path = self.root / "EVENTS.jsonl"
        raw = path.read_bytes()
        path.write_bytes(raw + b'{"event":')
        report = self.audit()
        self.assertFalse(report["events"]["parse_complete"])
        self.assertEqual("UNKNOWN", report["attempts"][0]["recorded_metrics"]["events"]["lifecycle_complete"])
        path.write_bytes(raw + raw.splitlines()[0] + b"\n")
        report = self.audit()
        self.assertEqual(2, report["attempts"][0]["recorded_metrics"]["events"]["event_counts"]["POST_BEGIN"])
        self.assertEqual("UNKNOWN", report["attempts"][0]["recorded_metrics"]["events"]["lifecycle_complete"])

    def test_retries_are_separate_and_never_join_fragments(self):
        write_case(self.root, '{"ok":', done=False, attempt=1)
        write_case(self.root, 'true}', attempt=2)
        report = self.audit()
        self.assertEqual([1, 2], [a["attempt"] for a in report["attempts"]])
        self.assertEqual(["INVALID", "INVALID"], [a["candidate"]["syntax"] for a in report["attempts"]])

    def test_limits_are_explicit_and_never_partial_parse_success(self):
        write_case(self.root)
        for limits, code in [({"max_artifact_bytes": 1}, "artifact_limit"),
                             ({"max_total_bytes": 1}, "total_byte_limit"),
                             ({"max_events": 1}, "event_limit"),
                             ({"max_directory_entries": 1}, "directory_entry_limit"),
                             ({"max_attempts": 0}, "invalid_limit")]:
            with self.subTest(limits=limits):
                report = self.audit(**limits)
                self.assertIn(code, [error["code"] for error in report["errors"]])
        (self.root / "ATTEMPT2-CONTENT.txt").write_bytes(b"{}")
        self.assertIn("attempt_limit", [e["code"] for e in self.audit(max_attempts=1)["errors"]])

    def test_reparse_attribute_is_rejected_before_content_read(self):
        write_case(self.root)
        path = self.root / "ATTEMPT1-CONTENT.txt"
        original = Path.lstat
        def reparse(p):
            info = original(p)
            return SimpleNamespace(st_file_attributes=0x400, st_mode=info.st_mode,
                                   st_size=info.st_size) if p == path else info
        # The host denies symlink creation; inject the Windows reparse metadata
        # boundary without claiming an actual linked-file integration test.
        with mock.patch.object(Path, "lstat", reparse):
            report = self.audit()
        self.assertIn("symlink_or_reparse_ignored", [e["code"] for e in report["errors"]])

    def test_cli_output_is_sanitized(self):
        write_case(self.root)
        output = io.StringIO()
        with redirect_stdout(output):
            code = AUDIT.main([str(self.root), "--max-events", "0"])
        self.assertEqual(1, code)
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())
        json.loads(output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            code = AUDIT.main([str(self.root)])
        self.assertEqual(0, code)
        self.assertEqual("VALID", json.loads(output.getvalue())["attempts"][0]["candidate"]["syntax"])


if __name__ == "__main__":
    unittest.main()
