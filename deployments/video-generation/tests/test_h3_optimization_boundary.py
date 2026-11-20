"""The scheduled test must not preempt a render or override another owner."""

import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("optimization_boundary", ROOT / "tools/watch_h3_optimization_boundary.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from video_queue import QueueStore


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"id": "test-only-reservation", "trigger_job_id": "video_gen_test"}
        self.task = {"status": "completed"}
        self.queue = {"maintenance": {"enabled": True, "upgrade_id": self.plan["id"]},
                      "scheduler": {"running_jobs": [], "phase": "upgrading"}, "running": [],
                      "recovery": {"paused": False}}

    def test_wait_for_worker_cleanup_not_only_completed_database_row(self):
        self.queue["scheduler"]["running_jobs"] = ["video_gen_test"]
        self.assertFalse(module.boundary_ready(self.task, self.queue, self.plan))
        self.queue["scheduler"]["running_jobs"] = []
        self.assertTrue(module.boundary_ready(self.task, self.queue, self.plan))

    def test_no_tests_before_delivery_or_under_another_maintenance_or_oom(self):
        for status in ("in_progress", "queued", "failed", "cancelled"):
            self.assertFalse(module.boundary_ready({"status": status}, self.queue, self.plan))
        for change in ({"maintenance": {"enabled": True, "upgrade_id": "other-owner"}},
                       {"maintenance": {"enabled": False, "upgrade_id": self.plan["id"]}},
                       {"recovery": {"paused": True}}, {"recovery": {}}):
            queue = copy.deepcopy(self.queue)
            queue.update(change)
            self.assertFalse(module.boundary_ready(self.task, queue, self.plan))

    def test_reservation_preserves_in_progress_job_and_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = QueueStore(tmp)
            store.initialize()
            with store.connection() as db:
                db.execute("INSERT INTO jobs(id,model,status,created,updated,payload,directory) VALUES(?,?,?,?,?,?,?)",
                           (self.plan["trigger_job_id"], "open-h3-2k", "in_progress", 1, 1, "{}", tmp))
            with patch("video_queue.QueueStore", return_value=store):
                control = module.arm(self.plan)
            self.assertFalse(control["enabled"])
            self.assertEqual(control["validation_job"], self.plan["trigger_job_id"])
            self.assertEqual(store.get(self.plan["trigger_job_id"])["status"], "in_progress")
            with patch("video_queue.QueueStore", return_value=store):
                with self.assertRaises(RuntimeError):
                    module.arm(self.plan)

    def test_refuse_to_reserve_a_different_or_already_finished_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = QueueStore(tmp)
            store.initialize()
            with patch("video_queue.QueueStore", return_value=store):
                with self.assertRaises(RuntimeError):
                    module.arm(self.plan)
            self.assertNotIn("service_control", store.state())


if __name__ == "__main__":
    unittest.main()
