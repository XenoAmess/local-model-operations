"""Synthetic public DATA projection. No tool capture, private fixture or authority.
The production module remains unchanged; these public Test bindings need their own
future necessary first and do not inherit any earlier private fixture result.
"""
import contextlib
import hashlib
import io
import json
import unittest
from unittest import mock

import collaboration_roster_snapshot as roster
from authorized_dispatch_plan import plan_dispatch
from dispatch_validation import MAX_INPUT_BYTES, PlanError

WHEN = "2026-01-02T03:04:05Z"
GUARD_AGENT = "/root/example_branch/blocked_member"


def fixture_bytes():
    return encoded({"agents": [
        {"agent_name": "/root/example_branch", "agent_status": "running"},
        {"agent_name": GUARD_AGENT, "agent_status": {"errored": "Synthetic error text; never classify by words"}},
        {"agent_name": "/root/example_branch/completed_one", "agent_status": {"completed": "Synthetic completed DATA"}},
        {"agent_name": "/root/example_branch/completed_two", "agent_status": {"completed": "running is only text in this completed body"}},
        {"agent_name": "/root/example_branch/active_one", "agent_status": "running"},
        {"agent_name": "/root/example_branch/active_two", "agent_status": "running"},
    ]})


def encoded(value, **options):
    return json.dumps(value, **options).encode("utf-8")


def capture(prefix="/root/example_branch", classifications=None):
    return {
        "schema": "xar.collaboration-roster-capture/v1",
        "snapshot_id": "synthetic-structured-view",
        "observed_at_utc": WHEN,
        "returned_view_complete": True,
        "path_prefix": prefix,
        "capture_kind": "STRUCTURED_VALUE_SERIALIZATION",
        "evidence": "Synthetic documentation DATA, not an actual capture or raw transport",
        "error_classifications": classifications if classifications is not None else [{
            "agent_id": GUARD_AGENT,
            "confirmed_kinds": ["GUARD"],
            "evidence": "Explicit synthetic operator classification; no real denial or permission assertion",
        }],
    }


def normalized(rows, metadata):
    return roster.normalize_roster(encoded({"agents": rows}), encoded(metadata))


class RosterSnapshotDataTest(unittest.TestCase):
    def test_synthetic_returned_view_counts_and_original_planner_snapshot(self):
        raw = fixture_bytes()
        result = roster.normalize_roster(raw, encoded(capture()))
        self.assertEqual(result["counts"], {
            "agents": 6, "running": 3, "completed": 2, "error": 1,
            "guard_error": 1, "capacity_error": 0, "unknown_error": 0, "root_running": 0,
        })
        self.assertEqual(result["view"], {
            "path_prefix": "/root/example_branch", "returned_view_complete": True,
            "global_status": "UNKNOWN", "root_returned": False, "root_status": None,
        })
        snapshot = result["snapshot"]
        self.assertEqual(set(snapshot), {
            "schema", "snapshot_id", "observed_at_utc", "complete", "agent_count", "agents",
        })
        self.assertEqual([row["agent_id"] for row in snapshot["agents"]],
                         [row["agent_name"] for row in json.loads(raw)["agents"]])
        error = next(row for row in snapshot["agents"] if row["agent_id"] == GUARD_AGENT)
        held_error = json.loads(raw)["agents"][1]["agent_status"]["errored"]
        self.assertEqual(error["error"]["raw"], held_error)
        self.assertEqual(error["error"]["confirmed_kinds"], ["GUARD"])
        self.assertTrue(all(row["same_task"] is None for row in snapshot["agents"]))
        empty_pending = {
            "schema": "xar.authorized-dispatch-pending/v1", "bundle_id": "explicit-empty-data",
            "prepared_at_utc": WHEN, "grants": [], "tasks": [],
        }
        plan = plan_dispatch(encoded(snapshot), encoded(empty_pending), now_utc=WHEN,
                             max_age_seconds=60, max_plan_items=65)
        self.assertEqual(plan["items"], [])
        self.assertIs(plan["actual_start"], False)
        self.assertIs(result["actual_start"], False)

    def test_strict_shape_duplicates_unknown_status_and_prefix_reject_whole(self):
        valid = {"agent_name": "/root/member", "agent_status": "running"}
        cases = [
            {"agents": [1]},
            {"agents": [valid, dict(valid)]},
            {"agents": [{"agent_name": "/root/member", "agent_status": "completed"}]},
            {"agents": [{"agent_name": "/root/member", "agent_status": "interrupted"}]},
            {"agents": [{"agent_name": "/root/member", "agent_status": {"completed": "x", "errored": "x"}}]},
            {"agents": [{"agent_name": "/root/member", "agent_status": {"running": "x"}}]},
            {"agents": [{"agent_name": "/root/member", "agent_status": True}]},
            {"agents": [{"agent_name": "/root/member", "agent_status": {"completed": None}}]},
            {"agents": [{"agent_name": "/root/member", "agent_status": "running", "extra": 1}]},
            {"agents": [{"agent_name": "/root/Member", "agent_status": "running"}]},
            {"agents": [], "extra": 1},
        ]
        for document in cases:
            with self.subTest(document=document), self.assertRaises(PlanError):
                roster.normalize_roster(encoded(document), encoded(capture(None, [])))
        with self.assertRaises(PlanError):
            roster.normalize_roster(b'{"agents":[],"agents":[]}', encoded(capture(None, [])))
        with self.assertRaises(PlanError):
            normalized([{"agent_name": "/root/example_branch_extra", "agent_status": "running"}],
                       capture("/root/example_branch", []))
        for change in ({"returned_view_complete": False}, {"observed_at_utc": "2026-02-30T00:00:00Z"},
                       {"path_prefix": ""}, {"extra": True}):
            metadata = capture(None, [])
            metadata.update(change)
            with self.subTest(change=change), self.assertRaises(PlanError):
                normalized([valid], metadata)
        with self.assertRaises(PlanError):
            roster.normalize_roster(bytearray(encoded({"agents": [valid]})), encoded(capture(None, [])))

    def test_exact_input_byte_evidence_root_membership_and_full_view_not_global(self):
        rows = [{"agent_name": "/root", "agent_status": "running"}] + [
            {"agent_name": "/root/member_" + str(index), "agent_status": "running"} for index in range(64)
        ]
        metadata_bytes = encoded(capture(None, []))
        first_raw = encoded({"agents": rows}, separators=(",", ":"))
        second_raw = encoded({"agents": rows}, indent=2) + b"\n"
        first = roster.normalize_roster(first_raw, metadata_bytes)
        second = roster.normalize_roster(second_raw, metadata_bytes)
        self.assertEqual(first["snapshot"], second["snapshot"])
        for raw, result in ((first_raw, first), (second_raw, second)):
            self.assertEqual(result["evidence"]["tool_input"],
                             {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            self.assertEqual(result["evidence"]["capture_input"],
                             {"bytes": len(metadata_bytes), "sha256": hashlib.sha256(metadata_bytes).hexdigest()})
            self.assertEqual(result["view"]["global_status"], "UNKNOWN")
            self.assertEqual(result["counts"]["root_running"], 1)
        self.assertNotEqual(first["evidence"]["tool_input"]["sha256"],
                            second["evidence"]["tool_input"]["sha256"])
        rows[0]["agent_status"] = {"completed": "running; must not count this word"}
        completed = normalized(rows, capture(None, []))
        self.assertEqual(completed["counts"]["running"], 64)
        self.assertEqual(completed["counts"]["completed"], 1)
        self.assertEqual(completed["counts"]["root_running"], 0)
        self.assertEqual(completed["view"]["root_status"], "COMPLETED")
        self.assertTrue(completed["view"]["root_returned"])
        root_error = normalized(
            [{"agent_name": "/root", "agent_status": {"errored": "synthetic held Root DATA error"}}],
            capture(None, [{"agent_id": "/root", "confirmed_kinds": ["UNKNOWN"],
                            "evidence": "Explicit synthetic operator UNKNOWN classification"}]))
        self.assertEqual(root_error["view"]["root_status"], "ERROR")
        self.assertTrue(root_error["view"]["root_returned"])
        self.assertEqual(root_error["counts"]["root_running"], 0)
        first["snapshot"]["agents"].clear()
        fresh = roster.normalize_roster(first_raw, metadata_bytes)
        self.assertEqual(fresh["counts"]["agents"], 65)
        self.assertEqual(len(fresh["snapshot"]["agents"]), 65)

    def test_error_classification_requires_operator_evidence_and_never_creates_work(self):
        row = {"agent_name": "/root/member", "agent_status": {"errored": "capacity GUARD running completed"}}
        for kind in ("GUARD", "UNKNOWN", "CAPACITY"):
            classification = {"agent_id": "/root/member", "confirmed_kinds": [kind],
                              "evidence": "Explicit operator classification for this exact DATA error"}
            result = normalized([row], capture(None, [classification]))
            actual = result["snapshot"]["agents"][0]
            self.assertEqual(actual["status"], "ERROR")
            self.assertEqual(actual["error"]["confirmed_kinds"], [kind])
            self.assertEqual(actual["error"]["raw"], row["agent_status"]["errored"])
            self.assertIsNone(actual["same_task"])
            self.assertFalse(any(key in result for key in ("tasks", "grants", "pending", "dispatch")))
        with self.assertRaises(PlanError) as absent:
            normalized([row], capture(None, []))
        self.assertEqual(absent.exception.code, "UNCLASSIFIED_ERROR")
        base = {"agent_id": "/root/member", "confirmed_kinds": ["GUARD"], "evidence": "explicit"}
        bad_rows = [
            [None],
            [base, dict(base)], [dict(base, agent_id="/root/missing")],
            [dict(base, confirmed_kinds=[])], [dict(base, confirmed_kinds=["GUARD", "GUARD"])],
            [dict(base, confirmed_kinds=["GUARD_DENIAL"])], [dict(base, evidence=" ")],
            [dict(base, same_task={"owner": "/root/member"})],
        ]
        for classifications in bad_rows:
            with self.subTest(classifications=classifications), self.assertRaises(PlanError):
                normalized([row], capture(None, classifications))
        with self.assertRaises(PlanError):
            normalized([{"agent_name": "/root/member", "agent_status": "running"}], capture(None, [base]))

    def test_cli_bounded_explicit_d_inputs_validation_before_xb_and_no_overwrite(self):
        # In-memory stream projection: no machine drive or real filesystem is needed.
        tool_path = "D:/roster-fixture/tool.json"
        capture_path = "D:/roster-fixture/capture.json"
        output = "D:/roster-fixture/new-output.json"
        valid_tool = encoded({"agents": [{"agent_name": "/root/member", "agent_status": "running"}]})
        valid_capture = encoded(capture(None, []))
        files = {tool_path: valid_tool, capture_path: valid_capture}
        args = ["--tool", tool_path, "--capture", capture_path, "--output", output]

        def call(arguments, short_write=False):
            out, err = io.StringIO(), io.StringIO()
            reads, creates = [], []

            class Reader(io.BytesIO):
                def read(self, size=-1):
                    reads.append(size)
                    return super().read(size)

            class Writer(io.BytesIO):
                def write(self, data):
                    return super().write(data[:-1] if short_write else data)
                def __exit__(self, *exc):
                    files[output] = self.getvalue()
                    return super().__exit__(*exc)

            def synthetic_open(path, mode="r", *positional, **keywords):
                if path == output:
                    creates.append(mode)
                if mode == "rb" and path in (tool_path, capture_path):
                    if path not in files:
                        raise FileNotFoundError("synthetic missing input")
                    return Reader(files[path])
                if path == output and mode == "xb":
                    if path in files:
                        raise FileExistsError("synthetic output exists")
                    files[path] = b""
                    return Writer()
                raise AssertionError("unexpected synthetic DATA I/O")

            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with mock.patch("builtins.open", side_effect=synthetic_open), mock.patch("io.open", side_effect=synthetic_open):
                    status = roster.main(arguments)
            self.assertTrue(all(size == MAX_INPUT_BYTES + 1 for size in reads))
            self.assertTrue(all(mode == "xb" for mode in creates))
            self.assertLessEqual(len(creates), 1)
            return status, out.getvalue(), err.getvalue()

        status, stdout, stderr = call(args)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), {"code": "ROSTER_DATA_CREATED", "actual_start": False, "agents": 1})
        frozen = files[output]
        status, _, stderr = call(args)
        self.assertEqual(status, 3)
        self.assertEqual(json.loads(stderr)["code"], "OUTPUT_EXISTS")
        self.assertEqual(files[output], frozen)
        reordered = ["--output", output, "--capture", capture_path, "--tool", tool_path]
        self.assertEqual(call(reordered)[0], 3)
        self.assertEqual(files[output], frozen)
        del files[output]
        malformed = capture(None, [])
        malformed["returned_view_complete"] = False
        files[capture_path] = encoded(malformed)
        self.assertEqual(call(args)[0], 2)
        self.assertNotIn(output, files)
        files[capture_path] = valid_capture
        files[tool_path] = b" " * (MAX_INPUT_BYTES + 1)
        self.assertEqual(call(args)[0], 2)
        self.assertNotIn(output, files)
        files[tool_path] = valid_tool
        for bad_args in (["--tool", "C:/forbidden.json", "--capture", capture_path, "--output", output],
                         args + ["--tool", tool_path], args + ["--unexpected", "x"]):
            self.assertEqual(call(bad_args)[0], 2)
            self.assertNotIn(output, files)
        status, _, stderr = call(args, short_write=True)
        self.assertEqual(status, 4)
        self.assertEqual(json.loads(stderr)["code"], "DATA_IO_FAILED")
        self.assertIn(output, files)
        self.assertLess(len(files[output]), len(frozen))


if __name__ == "__main__":
    unittest.main()
