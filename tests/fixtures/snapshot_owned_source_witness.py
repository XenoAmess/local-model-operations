"""Six pre-frozen DATA witnesses plus source guard and owner v2 pagination methods; Native execution only."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class ExplicitOwnedSourceSnapshotWitness(unittest.TestCase):
    def setUp(self):
        self.cli = Path(os.environ["OWNED_SOURCE_SNAPSHOT_CLI"]).resolve(strict=True)
        self.scratch = Path(os.environ["OWNED_SOURCE_SNAPSHOT_TEST_ROOT"]).resolve(strict=True)
        if self.scratch.drive.upper() != "D:":
            raise RuntimeError("Native must supply an owned D scratch root")
        self.temp = tempfile.TemporaryDirectory(prefix="owned-source-cut-", dir=self.scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, leaf, value):
        path = self.root / leaf
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        path.write_bytes(raw)
        return str(path)

    def ready_row(self, name):
        return {
            "id": "id-" + name, "owner": "owner-" + name,
            "spec_path": str(self.root / ("not-opened-" + name + ".SPEC.json")),
            "task_id": "task-" + name, "output_path": str(self.root / ("output-" + name)),
            "config_path": str(self.root / "not-opened-config.json"),
            "machine_id": "synthetic-machine", "lane": "source"}

    def events(self, row, start="2025-01-01T00:00:00Z", end="2025-01-01T00:00:01Z"):
        path = Path(row["output_path"]) / "EVENTS.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        common = {"attempt": 1, "task_id": row["task_id"],
                  "owner": row["owner"], "machine_id": row["machine_id"]}
        values = [
            dict(common, event="POST_BEGIN", at_utc=start, network_routing={"proxy_mode": "direct"}),
            dict(common, event="HEADERS", at_utc=start, http_status=200, http_headers_ms=1),
            dict(common, event="FIRST_CONTENT", at_utc=start, first_nonempty_content_delta_ms=2)]
        if end is not None:
            values.append(dict(common, event="ATTEMPT_END", at_utc=end, post_invoked=True,
                               finish_reason="stop", sse_done=True, candidate_complete=True,
                               total_ms=1000, json_syntax={"status": "VALID"}))
        path.write_bytes(b"".join((json.dumps(v) + "\n").encode() for v in values))

    def ticket(self, leaf, row, stage=None):
        metadata = self.put(leaf + ".ready.json", {"id": row["id"], "task_id": row["task_id"]})
        receipt = str(self.root / (leaf + ".receipt.json"))
        if stage is not None:
            self.put(leaf + ".receipt.json", {"stage": stage})
        return {"metadata_path": metadata, "receipt_path": receipt}

    def manifest(self, ready_lists, tickets):
        paths = [self.put("ready-" + str(i) + ".json", rows)
                 for i, rows in enumerate(ready_lists)]
        return {"schema": "owned-source-snapshot-input/v2", "ready_files": paths,
                "current_ready": paths[-1], "tickets": tickets}

    def run_cli(self, manifest=None, raw=None):
        if raw is None:
            raw = (json.dumps(manifest, ensure_ascii=False) + "\n").encode("utf-8")
        path = self.root / "input.json"
        path.write_bytes(raw)
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(self.cli), str(path)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, shell=False,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1"))
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "read-only CLI changed or created fixture files")
        return result

    def report(self, result):
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertEqual(result.stderr, b"")
        self.assertTrue(result.stdout.endswith(b"\n"))
        self.assertEqual(result.stdout.count(b"\n"), 1)
        value = json.loads(result.stdout)
        self.assertEqual(value["scope"], "EXPLICIT_READY_AND_TICKETS_ONLY_NOT_GLOBAL")
        self.assertIs(value["snapshot_atomic"], False)
        self.assertEqual(value["global_source_Runtime_cloud_backend"], "UNKNOWN_OR_SEPARATE")
        self.assertEqual(value["process_liveness"], "UNKNOWN")
        self.assertEqual(value["server_receipt"], "UNKNOWN")
        self.assertIs(value["metadata_or_receipt_is_POST_credit"], False)
        self.assertIs(value["candidate_CONTENT_or_DB_access"], False)
        self.assertIn("read_started_at_utc", value)
        self.assertIn("read_finished_at_utc", value)
        return value

    def test_deduplicates_generations_and_observes_revision_receipts(self):
        a, b, c = [self.ready_row(n) for n in ("a", "b", "c")]
        self.events(a)
        self.events(b, "2025-01-01T00:00:02Z", "2025-01-01T00:00:03Z")
        tickets = [self.ticket("a-old", a, "PREPARATION_FAILED_NO_AUTO_RETRY"),
                   self.ticket("a-revised", a, "READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT"),
                   self.ticket("b-ready", b, "READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT"),
                   self.ticket("c-pending", c)]
        value = self.report(self.run_cli(self.manifest([[a, b], [b]], tickets)))
        self.assertEqual(value["ready"]["registered_distinct_records"], 2)
        self.assertEqual(value["ready"]["current_READY_records"], 1)
        self.assertEqual(value["http"]["observed_POSTs"], 2)
        self.assertEqual(value["http"]["observed_ENDs"], 2)
        self.assertEqual(value["http"]["actual_unpaired_POST_attempts"], 0)
        intake = value["intake"]
        for key, expected in {
            "seen_intake_tickets": 4, "distinct_valid_logical_ids": 3,
            "tickets_with_known_receipt": 3, "tickets_awaiting_receipt": 1,
            "preparation_rejected_receipts": 1, "registered_valid_logical_ids": 2,
            "unregistered_valid_logical_ids": 1}.items():
            self.assertEqual(intake[key], expected, key)
        self.assertEqual(intake["unregistered_stage_counts"], {"ABSENT": 1})

    def test_missing_events_keep_unknown_and_no_observed_post_distinct(self):
        row = self.ready_row("missing")
        value = self.report(self.run_cli(self.manifest([[row], [row]], [])))
        self.assertEqual(value["http"]["evidence_status"], "UNKNOWN")
        self.assertIsNone(value["http"]["actual_unpaired_POST_attempts"])
        self.assertEqual(value["http"]["registered_no_observed_POST"], 1)
        self.assertEqual(value["http"]["current_generation_no_observed_POST"], 1)
        self.assertEqual(value["http"]["observed_POSTs"], 0)

    def test_cross_generation_changed_identity_is_fatal_quietly(self):
        row = self.ready_row("a")
        changed = dict(row, owner="changed-owner")
        result = self.run_cli(self.manifest([[row], [changed]], []))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIsInstance(json.loads(result.stderr), dict)

    def test_invalid_ticket_and_receipt_remain_visible(self):
        row = self.ready_row("pending")
        ticket = self.ticket("invalid", row)
        Path(ticket["metadata_path"]).write_bytes(b'{"id":')
        Path(ticket["receipt_path"]).write_bytes(b'{"stage":"a","stage":"b"}')
        value = self.report(self.run_cli(self.manifest([[]], [ticket])))
        intake = value["intake"]
        self.assertEqual(intake["seen_intake_tickets"], 1)
        self.assertEqual(intake["distinct_valid_logical_ids"], 0)
        self.assertEqual(intake["tickets_with_known_receipt"], 0)
        self.assertEqual(intake["tickets_awaiting_receipt"], 0)
        self.assertEqual(intake["invalid_or_unreadable_metadata_tickets"], 1)
        self.assertEqual(intake["invalid_or_unreadable_receipts"], 1)
        self.assertEqual(value["tickets"][0]["metadata_status"], "INVALID")
        self.assertEqual(value["tickets"][0]["receipt_status"], "INVALID")

    def test_strict_duplicate_json_and_manifest_byte_bound(self):
        result = self.run_cli(raw=b'{"schema":"x","schema":"y"}')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIsInstance(json.loads(result.stderr), dict)
        result = self.run_cli(raw=b" " * 1048577)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIsInstance(json.loads(result.stderr), dict)

    def test_known_empty_registry_and_unicode_ticket_identity(self):
        row = self.ready_row("empty")
        row["id"] = "unicode-\u7409\u7130"
        row["task_id"] = "task-\u6570\u636e"
        ticket = self.ticket("unicode", row, "READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT")
        value = self.report(self.run_cli(self.manifest([[]], [ticket])))
        self.assertEqual(value["ready"]["registered_distinct_records"], 0)
        self.assertEqual(value["http"]["observed_POSTs"], 0)
        self.assertEqual(value["http"]["observed_ENDs"], 0)
        self.assertEqual(value["http"]["actual_unpaired_POST_attempts"], 0)
        self.assertEqual(value["intake"]["unregistered_valid_logical_ids"], 1)
        self.assertEqual(value["tickets"][0]["id"], row["id"])
        self.assertEqual(value["tickets"][0]["task_id"], row["task_id"])

    def test_selected_source_guard_regressions_after_full_review(self):
        # These additional source-regression assertions follow native full review.
        row = self.ready_row("duplicate")
        result = self.run_cli(self.manifest([[row, row]], []))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        ticket = self.ticket("one-invalid-identity", row)
        Path(ticket["metadata_path"]).write_bytes(b'{"id":"only-an-id"}')
        value = self.report(self.run_cli(self.manifest([[]], [ticket])))
        self.assertEqual(value["intake"]["invalid_or_unreadable_metadata_tickets"], 1)
        self.assertEqual(value["intake"]["distinct_valid_logical_ids"], 0)
        receipt_ticket = self.ticket("lone-surrogate-stage", row)
        Path(receipt_ticket["receipt_path"]).write_bytes(b'{"stage":"\\ud800"}')
        value = self.report(self.run_cli(self.manifest([[]], [receipt_ticket])))
        self.assertEqual(value["intake"]["invalid_or_unreadable_receipts"], 1)
        self.assertEqual(value["tickets"][0]["receipt_status"], "INVALID")
        a = self.ready_row("unregistered")
        b = dict(a, task_id="another-task")
        value = self.report(self.run_cli(self.manifest(
            [[]], [self.ticket("conflict-a", a), self.ticket("conflict-b", b)])))
        self.assertEqual(value["intake"]["distinct_valid_logical_ids"], 2)
        self.assertEqual(value["intake"]["unregistered_valid_logical_ids"], 2)
        for item in value["tickets"]:
            self.assertIn("IDENTITY_CONFLICT", item["diagnostics"])
        rows = [self.ready_row("shared-" + str(i)) for i in range(17)]
        value = self.report(self.run_cli(self.manifest([rows for _ in range(16)], [])))
        self.assertEqual(value["ready"]["registered_distinct_records"], 17)
        self.assertEqual(value["ready"]["current_READY_records"], 17)
        self.assertEqual(len(value["ready"]["sources"]), 16)
        self.assertEqual(value["ready"]["maximum_READY_bytes"], 65536)
        self.assertEqual(value["http"]["current_generation_no_observed_POST"], 17)
        self.assertIsNone(value["http"]["actual_unpaired_POST_attempts"])

    def test_owner_v2_batches_combine_intervals_at_one_global_cutoff(self):
        rows = [self.ready_row("batch-" + str(i)) for i in range(257)]
        self.events(rows[0], "2025-01-01T00:00:00Z", "2025-01-01T00:00:02Z")
        self.events(rows[256], "2025-01-01T00:00:00Z", "2025-01-01T00:00:02Z")
        base = dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc)
        for i in range(1, 256):
            start = base + dt.timedelta(seconds=3 * i)
            end = start + dt.timedelta(seconds=1)
            self.events(rows[i], start.isoformat(), end.isoformat())
        manifest = self.manifest([rows[i:i+64] for i in range(0, len(rows), 64)], [])
        value = self.report(self.run_cli(manifest))
        self.assertEqual(value["ready"]["registered_distinct_records"], 257)
        self.assertEqual(value["http"]["observer_batches"], 2)
        self.assertEqual(value["http"]["observer_batch_max_streams"], 256)
        self.assertEqual(value["http"]["observed_POSTs"], 257)
        self.assertEqual(value["http"]["observed_ENDs"], 257)
        self.assertEqual(value["http"]["actual_unpaired_POST_attempts"], 0)
        self.assertEqual(value["http"]["peak_registered_POST_intervals"], 2)
        self.assertEqual(value["http"]["peak_seconds"], 2.0)
        (Path(rows[256]["output_path"]) / "EVENTS.jsonl").unlink()
        value = self.report(self.run_cli(manifest))
        self.assertEqual(value["http"]["evidence_status"], "UNKNOWN")
        self.assertIsNone(value["http"]["actual_unpaired_POST_attempts"])
        self.assertIsNone(value["http"]["peak_registered_POST_intervals"])

if __name__ == "__main__":
    unittest.main()
