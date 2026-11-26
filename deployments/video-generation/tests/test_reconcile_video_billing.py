from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from reconcile_video_billing import MODELS, reconcile


class ReconcileVideoBillingTests(unittest.TestCase):
    def test_only_expired_local_terminal_jobs_are_rearmed(self):
        omni, ic = MODELS
        fixtures = [
            ("completed", omni, "unpriceable", "max_poll_attempts", None, None, "openai", "video"),
            ("failed", ic, "unpriceable", "max_poll_attempts", None, None, "openai", "video"),
            ("cancelled", omni, "unpriceable", "max_poll_attempts", None, None, "openai", "video"),
            ("in_progress", omni, "unpriceable", "max_poll_attempts", None, None, "openai", "video"),
            ("completed", omni, "accounted", None, "already-written", None, "openai", "video"),
            ("completed", omni, "unpriceable", "missing_pricing", None, None, "openai", "video"),
            ("completed", omni, "unpriceable", "max_poll_attempts", "already-written", None, "openai", "video"),
            ("completed", ic, "unpriceable", "max_poll_attempts", None, "active-runner", "openai", "video"),
            ("completed", omni, "unpriceable", "max_poll_attempts", None, None, "custom", "video"),
            ("completed", omni, "unpriceable", "max_poll_attempts", None, None, "openai", "batch"),
            (None, omni, "unpriceable", "max_poll_attempts", None, None, "openai", "video"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            queue_db, bifrost_db = Path(temp) / "queue.sqlite3", Path(temp) / "config.db"
            with sqlite3.connect(queue_db) as queue, sqlite3.connect(bifrost_db) as bifrost:
                queue.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, model TEXT, status TEXT)")
                bifrost.execute(
                    "CREATE TABLE batch_jobs (id INTEGER PRIMARY KEY, batch_id TEXT, model TEXT, accounting_status TEXT, "
                    "unpriceable_reason TEXT, aggregate_log_written_at TEXT, governance_reported_at TEXT, runner_id TEXT, "
                    "claimed_at TEXT, provider TEXT, kind TEXT, provider_status TEXT DEFAULT 'queued', "
                    "poll_attempts INTEGER, next_check_at TEXT, "
                    "updated_at TEXT, last_error TEXT, created_at INTEGER)"
                )
                for index, (status, model, accounting, reason, receipt, runner, provider, kind) in enumerate(fixtures, 1):
                    job = f"video_gen_{index:032x}"
                    if status:
                        queue.execute("INSERT INTO jobs VALUES (?, ?, ?)", (job, model, status))
                    bifrost.execute(
                        "INSERT INTO batch_jobs (id, batch_id, model, accounting_status, unpriceable_reason, "
                        "aggregate_log_written_at, runner_id, provider, kind, poll_attempts, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 119, ?)",
                        (index, job + ":openai", model, accounting, reason, receipt, runner, provider, kind, index),
                    )
            expected = [f"video_gen_{index:032x}:openai" for index in (1, 2, 3)]
            preview = reconcile(queue_db, bifrost_db)
            self.assertEqual(preview["terminal"], expected)
            self.assertEqual(preview["rearmed"], [])
            self.assertEqual(reconcile(queue_db, bifrost_db, apply=True)["rearmed"], expected)
            self.assertEqual(reconcile(queue_db, bifrost_db, apply=True)["rearmed"], [])
            with sqlite3.connect(bifrost_db) as bifrost:
                for identifier, attempts, date, status, reason in bifrost.execute(
                    "SELECT id, poll_attempts, next_check_at, accounting_status, unpriceable_reason FROM batch_jobs"
                ):
                    if identifier <= 3:
                        self.assertEqual((attempts, status, reason), (0, "pending", None))
                        self.assertIsNotNone(date)
                    else:
                        self.assertEqual((attempts, date, status, reason), (
                            119, None, *fixtures[identifier - 1][2:4],
                        ))


if __name__ == "__main__":
    unittest.main()
