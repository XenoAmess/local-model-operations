"""Meaningful alert boundaries: slow dense inference, true failures, and terminal completion."""

import sys
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from watch_video_progress import evaluate, main, GIB


class VideoProgressTest(unittest.TestCase):
    def sample(self, now=2000, update=1000, block=40):
        return {"time": now, "task": {"status": "in_progress", "stage": "整段密集推理", "progress": 33,
                "denoising_step": 1, "transformer_block": block, "updated_at": update},
                "errors": {}, "worker": {"ActiveState": "active", "FreezerState": "running"},
                "gpus": [{"utilization_percent": 100, "temperature_c": 52}],
                "host_available_bytes": 60 * GIB, "disk_free_bytes": 60 * GIB}

    def test_normal_fifteen_minute_block_reporting_does_not_alert(self):
        alerts, state = evaluate(self.sample(), {}, {})
        self.assertEqual(alerts, {})
        alerts, state = evaluate(self.sample(now=2600), state, {})
        self.assertNotIn("progress_stalled", alerts)

    def test_real_half_hour_stall_alerts_even_when_gpu_busy(self):
        alerts, state = evaluate(self.sample(), {}, {})
        alerts, _ = evaluate(self.sample(now=2801), state, {})
        self.assertIn("progress_stalled", alerts)

    def test_block_progress_resets_stall_clock(self):
        _, state = evaluate(self.sample(), {}, {})
        alerts, _ = evaluate(self.sample(now=4000, update=3900, block=45), state, {})
        self.assertNotIn("progress_stalled", alerts)

    def test_completed_job_does_not_alert_on_expected_worker_exit(self):
        s = self.sample(now=8000)
        s["task"]["status"] = "completed"
        s["worker"]["ActiveState"] = "inactive"
        s["errors"]["gpu"] = "nvidia-smi temporarily unavailable"
        alerts, _ = evaluate(s, {}, {})
        self.assertEqual(alerts, {})

    def test_failed_job_alerts_with_error_instead_of_stall(self):
        s = self.sample(now=8000)
        s["task"].update(status="failed", error="CUDA out of memory")
        alerts, _ = evaluate(s, {}, {})
        self.assertEqual(set(alerts), {"task_failed"})
        self.assertIn("out of memory", alerts["task_failed"])

    def test_single_idle_sample_is_not_failure_two_samples_can_warn(self):
        s = self.sample()
        s["gpus"][0]["utilization_percent"] = 0
        alerts, state = evaluate(s, {}, {})
        self.assertNotIn("gpu_idle", alerts)
        s["time"] += 600
        alerts, _ = evaluate(s, state, {})
        self.assertIn("gpu_idle", alerts)

    def test_inactive_or_frozen_worker_alerts_while_task_active(self):
        s = self.sample()
        s["worker"].update(ActiveState="inactive", FreezerState="frozen")
        alerts, _ = evaluate(s, {}, {})
        self.assertTrue({"worker_inactive", "worker_frozen"}.issubset(alerts))

    def test_oom_counter_increment_is_detected_without_model_restart(self):
        s = self.sample()
        s["memory_events"] = {"oom": 1, "oom_kill": 0}
        alerts, state = evaluate(s, {}, {})
        self.assertIn("worker_oom", alerts)
        alerts, _ = evaluate(s, state, {})
        self.assertNotIn("worker_oom", alerts)

    def test_temporary_incident_notification_is_retried_after_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            config = path / "config.json"
            config.write_text(json.dumps({"job": "fixture", "state_directory": str(path)}))
            first, recovered = self.sample(), self.sample(now=2200, update=2100, block=45)
            first["memory_events"] = recovered["memory_events"] = {"oom": 1}
            with patch("sys.argv", ["watch", "--config", str(config)]), patch("watch_video_progress.collect", return_value=first), patch("watch_video_progress.notify", return_value=False):
                self.assertEqual(main(), 75)
            self.assertIn("worker_oom", json.loads((path / "state.json").read_text())["pending_alerts"])
            with patch("sys.argv", ["watch", "--config", str(config)]), patch("watch_video_progress.collect", return_value=recovered), patch("watch_video_progress.notify", return_value=True) as send:
                self.assertEqual(main(), 0)
            send.assert_called_once()
            self.assertEqual(json.loads((path / "state.json").read_text())["pending_alerts"], {})

    def test_same_persistent_incident_notifies_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            config = path / "config.json"
            config.write_text(json.dumps({"job": "fixture", "state_directory": str(path)}))
            sample = self.sample(now=4000)
            with patch("sys.argv", ["watch", "--config", str(config)]), patch("watch_video_progress.collect", return_value=sample), patch("watch_video_progress.notify", return_value=True) as send:
                self.assertEqual(main(), 0)
                sample["time"] += 600
                self.assertEqual(main(), 0)
            send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
