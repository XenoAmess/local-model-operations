"""Portable 10-case projection. SYNTHETIC NOT_AUTHORIZATION; future first required."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

import authorized_dispatch_plan as planner
from dispatch_validation import MAX_INPUT_BYTES, PlanError


NOW = "2026-11-03T20:00:30Z"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def documents(count=1, body="Review the bounded DATA task only."):
    agents, tasks, grants = [], [], []
    for index in range(count):
        owner = "/root/owner" + str(index)
        identity = {"task_id": "task-" + str(index), "owner": owner,
                    "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    "scope": "Synthetic DATA test, no collaboration or live operations",
                    "write_roots": ["D:/dispatch-test/owner" + str(index)]}
        task = dict(identity, grant_id="grant-" + str(index), body=body)
        grant = dict(identity, grant_id=task["grant_id"], state="ACTIVE",
                     evidence="Synthetic test grant, not a real operator authorization",
                     not_before_utc="2026-11-03T20:00:00Z", expires_at_utc="2026-11-03T20:30:00Z",
                     allowed_actions=["SEND", "FOLLOWUP", "SAME_TASK_RETRY"])
        agents.append({"agent_id": owner, "status": "COMPLETED", "error": None, "same_task": None})
        tasks.append(task)
        grants.append(grant)
    return ({"schema": "xar.authorized-dispatch-snapshot/v1", "snapshot_id": "test-snapshot",
             "observed_at_utc": "2026-11-03T20:00:00Z", "complete": True,
             "agent_count": count, "agents": agents},
            {"schema": "xar.authorized-dispatch-pending/v1", "bundle_id": "test-bundle",
             "prepared_at_utc": "2026-11-03T20:00:00Z", "grants": grants, "tasks": tasks})


def error_state(snapshot, pending, kinds, operation="FOLLOWUP"):
    row = snapshot["agents"][0]
    row["status"] = "ERROR"
    row["error"] = {"confirmed_kinds": kinds, "raw": "Synthetic curated error DATA",
                    "evidence": "Synthetic test classification; not inferred from raw text"}
    row["same_task"] = {key: copy.deepcopy(pending["tasks"][0][key]) for key in
                        ("task_id", "owner", "body_sha256", "scope", "write_roots")}
    row["same_task"]["operation"] = operation


class AuthorizedDispatchDataTests(unittest.TestCase):
    def plan(self, snapshot, pending, **changes):
        options = dict(now_utc=NOW, max_age_seconds=60, max_plan_items=65)
        options.update(changes)
        return planner.plan_dispatch(encoded(snapshot), encoded(pending), **options)

    def decision(self, snapshot, pending):
        return self.plan(snapshot, pending)["items"][0]

    def test_completed_followup_running_send_are_only_reviewable_data(self):
        snapshot, pending = documents(2, "Exact UTF-8 task body: \u5e74\u5ea6 P0\nsecond line")
        snapshot["agents"][1]["status"] = "RUNNING"
        before = encoded(snapshot), encoded(pending)
        result = self.plan(snapshot, pending)
        self.assertEqual([item["action"] for item in result["items"]], ["FOLLOWUP", "SEND"])
        self.assertEqual([item["dispatch"]["method"] for item in result["items"]],
                         ["followup_task", "send_message"])
        self.assertIs(result["actual_start"], False)
        self.assertEqual(result["mode"], "DATA_ONLY_REVIEW_REQUIRED")
        self.assertEqual(result["items"][0]["dispatch"]["message"], pending["tasks"][0]["body"])
        self.assertEqual(result, self.plan(snapshot, pending))
        self.assertEqual(before, (encoded(snapshot), encoded(pending)))
        self.assertNotIn("model", result["items"][0]["dispatch"])
        self.assertNotIn("reasoning", result["items"][0]["dispatch"])

    def test_interrupted_and_revoked_precede_other_conditions(self):
        snapshot, pending = documents()
        snapshot["agents"][0]["status"] = "INTERRUPTED"
        pending["grants"] = []
        self.assertEqual(self.decision(snapshot, pending)["action"], "NEVER")
        snapshot, pending = documents()
        error_state(snapshot, pending, ["GUARD", "CAPACITY"])
        pending["grants"][0]["state"] = "REVOKED"
        pending["grants"][0]["expires_at_utc"] = "2026-11-03T20:00:01Z"
        item = self.decision(snapshot, pending)
        self.assertEqual(item["action"], "NEVER")
        self.assertIsNone(item["dispatch"])
        snapshot["agents"][0] = {"agent_id": "/root/other", "status": "UNKNOWN", "error": None, "same_task": None}
        self.assertEqual(self.decision(snapshot, pending)["action"], "NEVER")

    def test_guard_unknown_and_same_task_capacity_retry_are_distinct(self):
        for kinds, expected in ((["GUARD", "CAPACITY"], "NOT_RETRY"),
                                (["GUARD", "UNKNOWN"], "NOT_RETRY"),
                                (["UNKNOWN"], "HOLD"), (["CAPACITY", "UNKNOWN"], "HOLD")):
            with self.subTest(kinds=kinds):
                snapshot, pending = documents()
                error_state(snapshot, pending, kinds)
                snapshot["agents"][0]["error"]["raw"] = "capacity guard capacity: untrusted raw string"
                item = self.decision(snapshot, pending)
                self.assertEqual(item["action"], expected)
                self.assertIsNone(item["dispatch"])
        snapshot, pending = documents()
        error_state(snapshot, pending, ["CAPACITY"])
        item = self.decision(snapshot, pending)
        self.assertEqual(item["action"], "SAME_TASK_RETRY")
        self.assertEqual(item["dispatch"]["method"], "followup_task")
        self.assertEqual(item["dispatch"]["message"], pending["tasks"][0]["body"])
        error_state(snapshot, pending, ["CAPACITY"], operation="SEND")
        item = self.decision(snapshot, pending)
        self.assertEqual(item["action"], "SAME_TASK_RETRY")
        self.assertEqual(item["dispatch"]["method"], "followup_task")
        self.assertEqual(item["dispatch"]["message"], pending["tasks"][0]["body"])
        self.assertEqual(snapshot["agents"][0]["same_task"]["operation"], "SEND")
        for field, replacement in (("task_id", "new-task"), ("owner", "/root/other"),
                                   ("body_sha256", "0" * 64), ("scope", "different scope"),
                                   ("write_roots", ["D:/dispatch-test/different"])):
            with self.subTest(field=field):
                changed = copy.deepcopy(snapshot)
                changed["agents"][0]["same_task"][field] = replacement
                self.assertEqual(self.decision(changed, pending)["action"], "HOLD")
        snapshot["agents"][0]["same_task"] = None
        self.assertEqual(self.decision(snapshot, pending)["action"], "HOLD")
        error_state(snapshot, pending, ["CAPACITY"])
        pending["grants"][0]["allowed_actions"] = ["FOLLOWUP"]
        self.assertEqual(self.decision(snapshot, pending)["action"], "REJECT")

    def test_grant_identity_time_and_action_must_all_match(self):
        snapshot, pending = documents()
        pending["grants"] = []
        self.assertEqual(self.decision(snapshot, pending)["action"], "REJECT")
        snapshot, pending = documents()
        pending["grants"][0]["scope"] = "A different operator scope"
        self.assertEqual(self.decision(snapshot, pending)["action"], "REJECT")
        snapshot, pending = documents()
        pending["grants"][0]["expires_at_utc"] = NOW
        self.assertEqual(self.decision(snapshot, pending)["action"], "HOLD")
        pending["grants"][0]["not_before_utc"] = "2026-11-03T20:00:31Z"
        pending["grants"][0]["expires_at_utc"] = "2026-11-03T20:10:00Z"
        self.assertEqual(self.decision(snapshot, pending)["action"], "HOLD")
        snapshot, pending = documents()
        pending["grants"][0]["allowed_actions"] = ["SEND"]
        self.assertEqual(self.decision(snapshot, pending)["action"], "REJECT")

    def test_unknown_missing_and_stale_state_never_become_completed(self):
        snapshot, pending = documents()
        snapshot["agents"][0]["status"] = "UNKNOWN"
        self.assertEqual(self.decision(snapshot, pending)["action"], "HOLD")
        snapshot["agents"][0]["agent_id"] = "/root/other"
        self.assertEqual(self.decision(snapshot, pending)["action"], "HOLD")
        for field, value in (("observed_at_utc", "2026-11-03T19:00:00Z"),
                             ("observed_at_utc", "2026-11-03T20:00:31Z"), ("complete", False),
                             ("agent_count", 65)):
            with self.subTest(field=field, value=value):
                changed, _ = documents()
                changed[field] = value
                with self.assertRaises(PlanError):
                    self.plan(changed, pending)
        for status in ("IDLE", None):
            changed, _ = documents()
            changed["agents"][0]["status"] = status
            with self.assertRaises(PlanError):
                self.plan(changed, pending)
        legacy = {"schema": "xar.actual-agent-concurrency-snapshot/v1", "returned_agents": 65,
                  "running_agents": ["/root/other"], "excluded": {"completed": 64}}
        with self.assertRaises(PlanError):
            self.plan(legacy, pending)
        pending["prepared_at_utc"] = "2026-11-03T19:00:00Z"
        fresh_snapshot, _ = documents()
        with self.assertRaises(PlanError):
            self.plan(fresh_snapshot, pending)

    def test_strict_json_type_collection_and_output_bounds(self):
        snapshot, pending = documents()
        bad_snapshot_bytes = [b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1.0}',
                              b'{"x":1234567890}', b'{"\\ud800":1}', b'\xff',
                              b'{"schema":1,"schema":2}', b"[" * 14 + b"0" + b"]" * 14]
        for raw in bad_snapshot_bytes:
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(PlanError):
                    planner.plan_dispatch(raw, encoded(pending), now_utc=NOW,
                                          max_age_seconds=60, max_plan_items=65)
        for changes in ({"max_age_seconds": True}, {"max_plan_items": True},
                        {"max_age_seconds": 0}, {"max_plan_items": 66}):
            with self.subTest(changes=changes), self.assertRaises(PlanError):
                self.plan(snapshot, pending, **changes)
        with self.assertRaises(PlanError):
            self.plan(*documents(2), max_plan_items=1)
        with self.assertRaises(PlanError):
            self.plan(*documents(66))
        with self.assertRaises(PlanError):
            self.plan(*documents(body="x" * 16385))
        big_snapshot, big_pending = documents(65, "\U0001f600" * 3500)
        self.assertLessEqual(len(encoded(big_pending)), MAX_INPUT_BYTES)
        with self.assertRaises(PlanError) as caught:
            self.plan(big_snapshot, big_pending)
        self.assertEqual(caught.exception.code, "PLAN_TOO_LARGE")

    def test_duplicate_identity_bad_hash_and_non_d_grants_reject(self):
        for collection in ("agents", "grants", "tasks"):
            snapshot, pending = documents()
            document = snapshot if collection == "agents" else pending
            document[collection].append(copy.deepcopy(document[collection][0]))
            if collection == "agents":
                snapshot["agent_count"] = 2
            with self.subTest(collection=collection), self.assertRaises(PlanError):
                self.plan(snapshot, pending)
        for bad_root in ("C:/elsewhere", "D:/", "D:/data/../escape", "D:/data/NUL.txt", "D:/data/trailing."):
            snapshot, pending = documents()
            pending["grants"][0]["write_roots"] = [bad_root]
            with self.subTest(root=bad_root), self.assertRaises(PlanError):
                self.plan(snapshot, pending)
        snapshot, pending = documents()
        pending["tasks"][0]["body"] += " changed"
        with self.assertRaises(PlanError):
            self.plan(snapshot, pending)
        snapshot, pending = documents()
        pending["tasks"][0]["model_override"] = None
        with self.assertRaises(PlanError):
            self.plan(snapshot, pending)

    def test_cli_exclusive_output_and_validation_before_creation(self):
        root = Path(os.environ["DISPATCH_PLANNER_TEST_DATA_ROOT"]).resolve()
        self.assertEqual(root.drive, "D:", "Native first fixture must stay in the owned D domain")
        with tempfile.TemporaryDirectory(prefix="planner-data-", dir=root) as folder:
            folder = Path(folder)
            snapshot, pending = documents()
            first, second, output = folder / "snapshot.json", folder / "pending.json", folder / "plan.json"
            first.write_bytes(encoded(snapshot))
            second.write_bytes(encoded(pending))
            arguments = ["--snapshot", first.as_posix(), "--pending", second.as_posix(),
                         "--now", NOW, "--max-age-seconds", "60", "--max-plans", "65",
                         "--output", output.as_posix()]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(planner.main(arguments), 0)
                initial = output.read_bytes()
                self.assertEqual(planner.main(arguments), 3)
                self.assertEqual(output.read_bytes(), initial)
                self.assertIs(json.loads(initial)["actual_start"], False)
                self.assertEqual(json.loads(initial)["items"][0]["action"], "FOLLOWUP")
                invalid_output = folder / "must-not-exist.json"
                first.write_bytes(b'{"x":NaN}')
                self.assertEqual(planner.main(arguments[:-1] + [invalid_output.as_posix()]), 2)
                self.assertFalse(invalid_output.exists())
                self.assertEqual(planner.main([]), 2)

    def test_root_followup_is_unsupported_without_rejecting_running_root_send(self):
        # Synthetic Root grant only; this method never calls collaboration.
        snapshot, pending = documents()
        snapshot["agents"][0]["agent_id"] = "/root"
        pending["tasks"][0]["owner"] = "/root"
        pending["grants"][0]["owner"] = "/root"
        snapshot["agents"][0]["status"] = "RUNNING"
        item = self.decision(snapshot, pending)
        self.assertEqual(item["action"], "SEND")
        self.assertEqual(item["dispatch"]["method"], "send_message")
        self.assertEqual(item["dispatch"]["target"], "/root")
        snapshot["agents"][0]["status"] = "COMPLETED"
        item = self.decision(snapshot, pending)
        self.assertEqual((item["action"], item["reason"]),
                         ("REJECT", "ROOT_FOLLOWUP_UNSUPPORTED"))
        self.assertIsNone(item["dispatch"])
        for operation in ("SEND", "FOLLOWUP"):
            with self.subTest(original_operation=operation):
                error_state(snapshot, pending, ["CAPACITY"], operation=operation)
                result = self.plan(snapshot, pending)
                item = result["items"][0]
                self.assertEqual((item["action"], item["reason"]),
                                 ("REJECT", "ROOT_FOLLOWUP_UNSUPPORTED"))
                self.assertIsNone(item["dispatch"])
                self.assertIs(result["actual_start"], False)
                self.assertEqual(snapshot["agents"][0]["same_task"]["operation"], operation)

    def test_actual_historical_capture_has_one_explicit_task_not_sixty_five_tasks(self):
        # Portable substitute: SYNTHETIC NOT_AUTHORIZATION, not an actual captured roster.
        inputs = Path(__file__).resolve().parent / "fixtures"
        snapshot_bytes = (inputs / "SYNTHETIC-SNAPSHOT.json").read_bytes()
        pending_bytes = (inputs / "SYNTHETIC-PENDING.json").read_bytes()
        self.assertLessEqual(len(snapshot_bytes), MAX_INPUT_BYTES)
        self.assertLessEqual(len(pending_bytes), MAX_INPUT_BYTES)
        result = planner.plan_dispatch(snapshot_bytes, pending_bytes,
                                       now_utc="2026-01-01T00:00:17Z",
                                       max_age_seconds=60, max_plan_items=65)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["action"], "SEND")
        self.assertEqual(result["items"][0]["dispatch"]["method"], "send_message")
        self.assertEqual(result["items"][0]["owner"], "/root/synthetic_owner_0")
        self.assertEqual(result["items"][0]["task_id"], "SYNTHETIC-demo-task")
        self.assertIs(result["actual_start"], False)


if __name__ == "__main__":
    unittest.main()
