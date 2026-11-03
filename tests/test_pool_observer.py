"""Offline independent event histories: no HTTP, caller import or business data."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).parent / "pool_observer.py"
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).parents[1] / "scripts/pool_observer.py"
SPEC = importlib.util.spec_from_file_location("pool_observer_under_test", MODULE_PATH)
POOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POOL)
SECRET = "PRIVATE_CANARY_SOURCE_CONTENT_AND_TASK"


def event(kind, second, attempt=1, **fields):
    return dict(event=kind, at_utc=f"2026-01-01T00:00:{second:02d}Z", attempt=attempt,
                task_id=SECRET, machine_id=SECRET, owner=SECRET, **fields)


def completed(start, end, attempt=1):
    return [event("POST_BEGIN", start, attempt, request_path=SECRET,
                  network_routing={"proxy_mode": "direct", "actual_peer": SECRET}),
            event("ATTEMPT_END", end, attempt, finish_reason="stop", sse_done=True,
                  json_syntax={"status": "VALID"}, candidate_complete=True,
                  content_path=SECRET, failure=SECRET)]


class PoolObserverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, rows):
        path = self.root / name
        path.write_bytes(b"".join(json.dumps(row, ensure_ascii=False).encode() + b"\n" for row in rows))
        return path

    def observe(self, path, **limits):
        before = path.read_bytes()
        report = POOL.observe_stream(path, **limits)
        self.assertEqual(before, path.read_bytes(), "observer must never alter originals")
        rendered = json.dumps(report, allow_nan=False)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn(str(self.root), rendered)
        return report

    def test_closed_intervals_peak_excludes_retry_backoff_and_ties(self):
        a = self.write("a.jsonl", completed(0, 2) + [event("RETRY_BACKOFF", 2, delay_seconds=2)] + completed(4, 6, 2))
        b = self.write("b.jsonl", completed(1, 5))
        report = POOL.observe_registry([{"id": "a", "events_path": str(a)}, {"id": "b", "events_path": str(b)}])
        self.assertEqual("KNOWN", report["evidence_status"])
        self.assertEqual(0, report["unended_at_cutoff"])
        self.assertEqual(2, report["peak_registered_POST_intervals"])
        self.assertEqual(2, report["peak_seconds"])
        self.assertEqual(6, report["observed_union_seconds"])
        # At equal END/BEGIN the half-open intervals do not double count.
        c = self.write("c.jsonl", completed(2, 4))
        tie = POOL.observe_registry([{"id": "a", "events_path": str(a)}, {"id": "c", "events_path": str(c)}])
        self.assertEqual(1, tie["peak_registered_POST_intervals"])
        self.assertEqual(6, tie["peak_seconds"])

    def test_first_content_is_separate_from_stop_and_semantic_review(self):
        path = self.write("content.jsonl", [event("POST_BEGIN", 0),
            event("HEADERS", 1, http_status=200, http_headers_ms=999),
            event("FIRST_CONTENT", 2, first_nonempty_content_delta_ms=1999),
            event("ATTEMPT_END", 3, finish_reason="length", sse_done=True, candidate_complete=False,
                  json_syntax={"status": "UNKNOWN"}, failure=SECRET)])
        report = self.observe(path)
        self.assertEqual("KNOWN", report["evidence_status"])
        self.assertTrue(report["intervals"][0]["valid_content_delta_observed"])
        self.assertEqual(999, report["intervals"][0]["http_headers_ms"])
        self.assertEqual(1999, report["intervals"][0]["first_nonempty_content_delta_ms"])
        self.assertEqual("length", report["intervals"][0]["finish_reason"])
        self.assertEqual("OWNER_REVIEW_REQUIRED", report["semantic_review"])

    def test_nonfinite_or_giant_measurements_cannot_leak_as_numbers(self):
        for value in [True, -1, float("inf"), 10 ** 1000]:
            with self.subTest(kind=type(value).__name__):
                path = self.write("bad-number.jsonl", [event("POST_BEGIN", 0),
                    event("HEADERS", 1, http_status=200, http_headers_ms=value)])
                report = self.observe(path)
                self.assertEqual("UNKNOWN", report["evidence_status"])
                self.assertIsNone(report["intervals"][0]["http_headers_ms"])

    def test_missing_end_never_becomes_process_alive_or_server_running(self):
        path = self.write("unended.jsonl", [event("POST_BEGIN", 0)])
        report = self.observe(path)
        self.assertEqual(1, report["unended_attempts"])
        self.assertEqual("UNPAIRED_POST", report["last_state"])
        self.assertEqual("UNKNOWN", report["process_liveness"])
        self.assertEqual("UNKNOWN", report["server_receipt"])

    def test_backoff_and_before_post_cancel_are_not_http(self):
        path = self.write("backoff.jsonl", completed(0, 1) + [event("RETRY_BACKOFF", 1, delay_seconds=30)])
        self.assertEqual("BACKOFF", self.observe(path)["last_state"])
        cancel = self.write("cancel.jsonl", [event("CANCELLED_BEFORE_POST", 0)])
        report = self.observe(cancel)
        self.assertEqual("KNOWN", report["evidence_status"])
        self.assertEqual(0, report["observed_POSTs"])
        self.assertEqual(0, report["unended_attempts"])

    def test_local_failure_before_post_is_not_a_post_interval(self):
        path = self.write("local.jsonl", [event("ATTEMPT_END", 1, post_invoked=False)])
        report = self.observe(path)
        self.assertEqual("KNOWN", report["evidence_status"])
        self.assertEqual(1, report["observed_ENDs"])
        self.assertEqual(0, report["observed_paired_POST_ENDs"])
        self.assertEqual(0, report["observed_POSTs"])

    def test_duplicate_or_orphan_events_make_global_totals_unknown(self):
        for name, rows in [("duplicate", completed(0, 1) + [event("ATTEMPT_END", 1)]),
                           ("orphan", [event("ATTEMPT_END", 1)]),
                           ("overlap", [event("POST_BEGIN", 0), event("POST_BEGIN", 1, 2)]),
                           ("order", [event("POST_BEGIN", 2), event("ATTEMPT_END", 1)]),
                           ("gap", completed(0, 1, 2))]:
            with self.subTest(name=name):
                path = self.write(name + ".jsonl", rows)
                self.assertEqual("UNKNOWN", self.observe(path)["evidence_status"])
                report = POOL.observe_registry([{"id": name, "events_path": str(path)}])
                self.assertIsNone(report["peak_registered_POST_intervals"])
                self.assertIsNone(report["unended_at_cutoff"])

    def test_partial_final_line_is_not_completed_even_when_json_parses(self):
        path = self.write("partial.jsonl", [event("POST_BEGIN", 0)])
        path.write_bytes(path.read_bytes() + json.dumps(event("ATTEMPT_END", 1)).encode())
        report = self.observe(path)
        self.assertEqual("UNKNOWN", report["evidence_status"])
        self.assertEqual(0, report["observed_ENDs"])
        self.assertIsNone(report["unended_attempts"])

    def test_malformed_schema_nonfinite_duplicate_keys_and_naive_time(self):
        raws = [b'{"event": []}\n', b'{"event":"POST_BEGIN","attempt":NaN}\n',
                b'{"event":"POST_BEGIN","event":"ATTEMPT_END"}\n', b'[]\n', b'\xff\n',
                json.dumps(event("POST_BEGIN", 0) | {"at_utc": "2026-01-01T00:00:00"}).encode() + b"\n"]
        for index, raw in enumerate(raws):
            with self.subTest(index=index):
                path = self.root / str(index)
                path.write_bytes(raw)
                self.assertEqual("UNKNOWN", self.observe(path)["evidence_status"])

    def test_missing_bounded_and_duplicate_registry_inputs(self):
        self.assertEqual("UNKNOWN", POOL.observe_stream(self.root / "absent")["evidence_status"])
        path = self.write("bounded.jsonl", completed(0, 1))
        self.assertEqual("BYTE_LIMIT_EXCEEDED", self.observe(path, max_bytes=10)["issues"][0])
        self.assertEqual("EVENT_LIMIT_EXCEEDED", self.observe(path, max_events=1)["issues"][0])
        with self.assertRaises(ValueError):
            POOL.observe_stream(path, max_bytes=True)
        with self.assertRaises(ValueError):
            POOL.observe_registry([{"id": "a", "events_path": str(path)}, {"id": "b", "events_path": str(path)}])

    def test_cli_outputs_only_metadata_and_keeps_all_named_originals(self):
        path = self.write("cli.jsonl", completed(0, 1))
        registry = self.root / "registry.json"
        registry.write_text(json.dumps([{"id": SECRET, "events_path": str(path)}]), encoding="utf-8")
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, registry)}
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(0, POOL.main([str(registry)]))
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, registry)})
        self.assertNotIn(SECRET, out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())


if __name__ == "__main__":
    unittest.main()
