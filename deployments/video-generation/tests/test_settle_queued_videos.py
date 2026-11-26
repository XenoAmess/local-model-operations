from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from settle_queued_videos import MODELS, reconcile


class QueueVideoSettlementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.queue_path = Path(temp.name) / "queue.sqlite3"
        self.billing_path = Path(temp.name) / "config.db"
        self.queue = sqlite3.connect(self.queue_path)
        self.billing = sqlite3.connect(self.billing_path)
        self.addCleanup(self.queue.close)
        self.addCleanup(self.billing.close)
        self.queue.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, model TEXT, status TEXT)")
        self.billing.execute(
            "CREATE TABLE batch_jobs (id INTEGER PRIMARY KEY, batch_id TEXT, model TEXT, accounting_status TEXT, "
            "unpriceable_reason TEXT, aggregate_log_written_at TEXT, governance_reported_at TEXT, runner_id TEXT, "
            "claimed_at TEXT, provider TEXT, kind TEXT, provider_status TEXT, poll_attempts INTEGER, "
            "next_check_at TEXT, updated_at TEXT)"
        )
        self.now = datetime(2026, 11, 27, tzinfo=timezone.utc)

    def add_job(self, number, queue_status, *, model=MODELS[0], accounting="pending",
                reason=None, receipt=None, runner=None, claimed_at=None, provider="openai",
                provider_status="queued", attempts=0, next_check_at=None):
        task_id = f"video_gen_{number:032x}"
        if queue_status:
            self.queue.execute("INSERT INTO jobs VALUES (?, ?, ?)", (task_id, model, queue_status))
        self.billing.execute(
            "INSERT INTO batch_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (number, task_id + ":openai", model, accounting, reason, receipt, None, runner,
             claimed_at, provider, "video", provider_status, attempts, next_check_at, "2026-11-25"),
        )
        return task_id

    def run_pass(self, now=None, *, apply=True):
        self.queue.commit()
        self.billing.commit()
        return reconcile(self.queue_path, self.billing_path, apply=apply, now=now or self.now)["counts"]

    def test_healthy_long_queue_stays_eligible_across_more_than_120_passes(self):
        tasks = [self.add_job(number, "queued", attempts=119, next_check_at="2026-11-25")
                 for number in range(53)]
        self.add_job(53, "in_progress", accounting="unpriceable", reason="max_poll_attempts", attempts=119)
        self.assertEqual(self.run_pass(apply=False), {"deferred": 54})
        self.assertEqual(self.billing.execute("SELECT max(poll_attempts) FROM batch_jobs").fetchone(), (119,))
        self.assertEqual(self.run_pass(), {"deferred": 54})
        for tick in range(1, 126):
            self.assertEqual(self.run_pass(self.now + timedelta(minutes=tick)), {"waiting": 54})
        self.assertEqual(self.billing.execute(
            "SELECT count(*) FROM batch_jobs WHERE accounting_status='pending' AND next_check_at IS NULL AND poll_attempts=0"
        ).fetchone(), (54,))
        self.queue.execute("UPDATE jobs SET status='completed' WHERE id=?", (tasks[0],))
        self.assertEqual(self.run_pass(), {"handed_off": 1, "waiting": 53})
        self.assertEqual(self.run_pass(), {"settling": 1, "waiting": 53})

    def test_terminal_handoff_preserves_existing_claims_retries_and_nonlocal_jobs(self):
        stale = (self.now - timedelta(minutes=6)).isoformat(sep=" ")
        future = (self.now + timedelta(minutes=4)).isoformat(sep=" ")
        self.add_job(1, "cancelled", model=MODELS[1], accounting="unpriceable", reason="max_poll_attempts")
        self.add_job(2, "completed", accounting="accounted", receipt="billed")
        self.add_job(3, "failed", provider_status="failed", accounting="error", receipt="billed", attempts=45, next_check_at=future)
        self.add_job(4, "failed", provider_status="failed", accounting="error", receipt="billed", attempts=45)
        self.add_job(5, "completed", provider_status="completed", accounting="processing", runner="original", claimed_at=stale)
        self.add_job(6, "completed", accounting="unpriceable", reason="missing_pricing")
        self.add_job(7, None)
        self.add_job(8, "completed", provider="other")
        self.assertEqual(self.run_pass(), {
            "handed_off": 1, "settling": 1, "retry_scheduled": 2,
            "needs_accounting_review": 1, "missing_queue_job": 1,
        })
        rows = dict(self.billing.execute("SELECT id, next_check_at FROM batch_jobs"))
        self.assertEqual(rows[1], self.now.isoformat(sep=" "))
        self.assertIsNone(rows[2])
        self.assertEqual(rows[3], future)
        self.assertEqual(rows[4], (self.now + timedelta(minutes=5)).isoformat(sep=" "))
        self.assertEqual(rows[5], self.now.isoformat(sep=" "))
        self.assertEqual(self.billing.execute(
            "SELECT runner_id, accounting_status FROM batch_jobs WHERE id=5"
        ).fetchone(), ("original", "processing"))
        self.assertIsNone(rows[8])
        self.assertEqual(self.run_pass(), {"settling": 4, "needs_accounting_review": 1, "missing_queue_job": 1})
