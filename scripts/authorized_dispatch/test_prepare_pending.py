"""Portable five-case source projection. SYNTHETIC NOT_AUTHORIZATION; future first required."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

import prepare_pending as builder
from authorized_dispatch_plan import PlanError, plan_dispatch


NOW = "2026-11-03T20:00:30Z"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def example():
    snapshot = {"schema": "xar.authorized-dispatch-snapshot/v1", "snapshot_id": "builder-test",
                "observed_at_utc": "2026-11-03T20:00:00Z", "complete": True, "agent_count": 1,
                "agents": [{"agent_id": "/root/builder_case", "status": "COMPLETED",
                            "error": None, "same_task": None}]}
    curation = {"schema": "xar.authorized-dispatch-curation/v1", "bundle_id": "builder-data",
                "prepared_at_utc": "2026-11-03T20:00:00Z", "entries": [{
                    "grant_id": "explicit-grant", "task_id": "explicit-task",
                    "owner": "/root/builder_case", "body": "Explicit synthetic DATA task.",
                    "scope": "Synthetic test only; no real authorization or collaboration",
                    "write_roots": ["D:/builder-test/first", "D:/builder-test/second"],
                    "state": "ACTIVE", "evidence": "Synthetic test grant, not a real operator grant",
                    "not_before_utc": "2026-11-03T19:59:00Z", "expires_at_utc": "2026-11-03T20:30:00Z",
                    "allowed_actions": ["FOLLOWUP", "SEND"]}]}
    return snapshot, curation


class PreparePendingDataTests(unittest.TestCase):
    def build(self, snapshot, curation):
        return builder.build_pending(encoded(snapshot), encoded(curation), now_utc=NOW,
                                     max_age_seconds=60, max_plan_items=65)

    def test_utf8_crlf_digest_and_explicit_negative_authority_preserved(self):
        snapshot, curation = example()
        entry = curation["entries"][0]
        entry["body"] = "\u5e74\u5ea6 \U0001f9ea\r\nline two\r\n"
        entry["state"] = "REVOKED"
        before = encoded(snapshot), encoded(curation)
        pending = self.build(snapshot, curation)
        grant, task = pending["grants"][0], pending["tasks"][0]
        digest = hashlib.sha256(entry["body"].encode("utf-8")).hexdigest()
        self.assertEqual(task["body"], entry["body"])
        self.assertIn("\r\n", task["body"])
        self.assertEqual(grant["body_sha256"], digest)
        self.assertEqual(task["body_sha256"], digest)
        for field in ("task_id", "owner", "scope", "write_roots"):
            self.assertEqual(grant[field], entry[field])
            self.assertEqual(task[field], entry[field])
        self.assertIsNot(grant["write_roots"], task["write_roots"])
        self.assertEqual(grant["allowed_actions"], ["FOLLOWUP", "SEND"])
        self.assertEqual(grant["state"], "REVOKED")
        self.assertEqual(len(pending["tasks"]), 1)
        plan = plan_dispatch(encoded(snapshot), encoded(pending), now_utc=NOW,
                             max_age_seconds=60, max_plan_items=65)
        self.assertEqual(plan["items"][0]["action"], "NEVER")
        self.assertIs(plan["actual_start"], False)
        self.assertEqual(before, (encoded(snapshot), encoded(curation)))

    def test_every_authority_and_top_level_field_must_be_explicit(self):
        for field in ("grant_id", "task_id", "owner", "body", "scope", "write_roots", "state",
                      "evidence", "not_before_utc", "expires_at_utc", "allowed_actions"):
            snapshot, curation = example()
            del curation["entries"][0][field]
            with self.subTest(missing_entry=field), self.assertRaises(PlanError):
                self.build(snapshot, curation)
        for field in ("schema", "bundle_id", "prepared_at_utc", "entries"):
            snapshot, curation = example()
            del curation[field]
            with self.subTest(missing_top=field), self.assertRaises(PlanError):
                self.build(snapshot, curation)
        snapshot, curation = example()
        curation["entries"][0]["body_sha256"] = "0" * 64
        with self.assertRaises(PlanError):
            self.build(snapshot, curation)

    def test_original_validation_rejects_illegal_data_but_keeps_valid_guard_data(self):
        for field, value in (("write_roots", ["C:/outside"]), ("write_roots", "D:/not-an-array"),
                             ("state", "DEFAULT"), ("allowed_actions", []), ("owner", "relative-owner")):
            snapshot, curation = example()
            curation["entries"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(PlanError):
                self.build(snapshot, curation)
        snapshot, curation = example()
        curation["entries"].append(copy.deepcopy(curation["entries"][0]))
        with self.assertRaises(PlanError):
            self.build(snapshot, curation)
        for raw in (b'{"schema":1,"schema":2}', b'{"entries":[NaN]}'):
            with self.assertRaises(PlanError):
                builder.build_pending(encoded(example()[0]), raw, now_utc=NOW,
                                      max_age_seconds=60, max_plan_items=65)
        snapshot, curation = example()
        snapshot["observed_at_utc"] = "2026-11-03T19:00:00Z"
        with self.assertRaises(PlanError):
            self.build(snapshot, curation)
        snapshot, curation = example()
        curation["entries"] = []
        empty = self.build(snapshot, curation)
        self.assertEqual((empty["grants"], empty["tasks"]), ([], []))
        snapshot, curation = example()
        snapshot["agents"][0].update(status="ERROR", error={"confirmed_kinds": ["GUARD"],
            "raw": "Synthetic confirmed guard DATA", "evidence": "Synthetic test classification"})
        pending = self.build(snapshot, curation)
        self.assertEqual(pending["grants"][0]["state"], "ACTIVE")
        self.assertEqual(pending["grants"][0]["allowed_actions"], curation["entries"][0]["allowed_actions"])
        self.assertEqual(len(pending["tasks"]), 1)
        self.assertEqual(plan_dispatch(encoded(snapshot), encoded(pending), now_utc=NOW,
            max_age_seconds=60, max_plan_items=65)["items"][0]["action"], "NOT_RETRY")

    def test_cli_exclusive_output_and_validation_before_creation(self):
        root = Path(os.environ["DISPATCH_PLANNER_TEST_DATA_ROOT"]).resolve()
        self.assertEqual(root.drive, "D:")
        with tempfile.TemporaryDirectory(prefix="pending-data-", dir=root) as directory:
            directory = Path(directory)
            snapshot, curation = example()
            first, second, output = directory / "snapshot.json", directory / "curation.json", directory / "pending.json"
            first.write_bytes(encoded(snapshot))
            second.write_bytes(encoded(curation))
            args = ["--snapshot", first.as_posix(), "--curation", second.as_posix(), "--now", NOW,
                    "--max-age-seconds", "60", "--max-plans", "65", "--output", output.as_posix()]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(args), 0)
                initial = output.read_bytes()
                self.assertEqual(json.loads(initial), self.build(snapshot, curation))
                self.assertEqual(builder.main(args), 3)
                self.assertEqual(output.read_bytes(), initial)
                invalid_output = directory / "must-not-exist.json"
                del curation["entries"][0]["state"]
                second.write_bytes(encoded(curation))
                self.assertEqual(builder.main(args[:-1] + [invalid_output.as_posix()]), 2)
                self.assertFalse(invalid_output.exists())

    def test_original_historical_pending_fixture_is_object_exact(self):
        # Retained case name; this portable fixture is SYNTHETIC, never authorization.
        inputs = Path(__file__).resolve().parent / "fixtures"
        snapshot_bytes = (inputs / "SYNTHETIC-BUILDER824-SNAPSHOT.json").read_bytes()
        expected = json.loads((inputs / "SYNTHETIC-BUILDER824-PENDING.json").read_bytes())
        self.assertEqual(len(expected["grants"]), 1)
        self.assertEqual(len(expected["tasks"]), 1)
        grant, task = expected["grants"][0], expected["tasks"][0]
        entry = {key: copy.deepcopy(grant[key]) for key in
                 ("grant_id", "task_id", "owner", "scope", "write_roots", "state", "evidence",
                  "not_before_utc", "expires_at_utc", "allowed_actions")}
        entry["body"] = task["body"]
        curation = {"schema": "xar.authorized-dispatch-curation/v1", "bundle_id": expected["bundle_id"],
                    "prepared_at_utc": expected["prepared_at_utc"], "entries": [entry]}
        actual = builder.build_pending(snapshot_bytes, encoded(curation), now_utc="2026-01-01T00:00:17Z",
                                       max_age_seconds=60, max_plan_items=65)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["tasks"][0]["owner"], "/root/synthetic_builder824")


if __name__ == "__main__":
    unittest.main()
