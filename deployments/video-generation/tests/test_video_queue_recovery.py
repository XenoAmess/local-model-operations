"""OOM control-plane tests use temporary databases and injected failures, never model inference."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from video_queue import OMNI, REFINER, QueueStore
from video_queue_recovery import QueueRecovery, RecoveryPolicy, probe_resources
from video_gpu_scheduler import Scheduler
from serve_video_http import create_app

HEALTHY = {"ready": True, "blockers": []}


class RecoveryStateTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = QueueStore(self.directory.name)
        self.store.initialize()
        self.recovery = QueueRecovery(self.store, RecoveryPolicy(cooldown_seconds=0))

    def fail(self):
        return self.recovery.record_failure(["failed-job"], "CUDA out of memory", [])

    def complete(self, memory):
        self.recovery.cleanup_result(memory["incident_id"])
        return self.recovery.observe(memory["incident_id"], HEALTHY)

    def test_requires_cleanup_cooldown_and_healthy_resources(self):
        with patch("video_queue_recovery.time.time", return_value=100):
            control = QueueRecovery(self.store, RecoveryPolicy(cooldown_seconds=60))
            memory = control.record_failure([], "OOM", [])
            self.assertFalse(control.observe(memory["incident_id"], HEALTHY))
            control.cleanup_result(memory["incident_id"])
            self.assertFalse(control.observe(memory["incident_id"], HEALTHY))
        with patch("video_queue_recovery.time.time", return_value=161):
            self.assertFalse(control.observe(memory["incident_id"], {"ready": False, "blockers": ["GPU busy"]}))
            self.assertEqual(control.snapshot()["status"], "waiting_for_resources")
            self.assertTrue(control.observe(memory["incident_id"], HEALTHY))

    def test_consecutive_ooms_persist_and_only_manual_resume_releases_circuit(self):
        self.assertTrue(self.complete(self.fail()))
        restarted = QueueRecovery(self.store, RecoveryPolicy(cooldown_seconds=0))
        self.assertEqual(restarted.snapshot()["consecutive_ooms"], 1)
        second = restarted.record_failure([], "CUDA out of memory", [])
        restarted.cleanup_result(second["incident_id"])
        self.assertFalse(restarted.observe(second["incident_id"], HEALTHY))
        self.assertTrue(restarted.snapshot()["manual_resume_required"])
        request = restarted.request_resume("operator inspected")
        self.assertTrue(request["accepted"])
        self.assertFalse(restarted.observe(second["incident_id"], {"ready": False}))
        self.assertTrue(restarted.observe(second["incident_id"], HEALTHY))
        self.assertEqual(restarted.snapshot()["consecutive_ooms"], 0)

    def test_success_breaks_oom_streak_but_idle_resume_does_not_reset_it(self):
        self.assertTrue(self.complete(self.fail()))
        self.assertFalse(self.recovery.request_resume()["accepted"])
        self.assertEqual(self.recovery.snapshot()["consecutive_ooms"], 1)
        self.recovery.record_success()
        self.assertEqual(self.fail()["status"], "cooldown")

    def test_stale_probe_cannot_clear_new_incident(self):
        old = self.fail()
        current = self.fail()
        self.recovery.cleanup_result(old["incident_id"])
        self.assertFalse(self.recovery.observe(old["incident_id"], HEALTHY))
        self.assertEqual(self.recovery.snapshot()["incident_id"], current["incident_id"])
        self.assertFalse(self.recovery.snapshot()["cleanup_complete"])

    def test_legacy_hold_requires_manual_resume_and_is_archived(self):
        self.store.hold.write_text(json.dumps({"jobs": ["old"], "reason": "OOM"}))
        self.recovery.sync_legacy()
        self.assertTrue(self.recovery.snapshot()["manual_resume_required"])
        memory = self.recovery.snapshot()
        self.assertFalse(self.complete(memory))
        self.assertTrue(self.store.hold.exists())
        self.recovery.request_resume()
        self.assertTrue(self.complete(memory))
        self.assertFalse(self.store.hold.exists())
        self.assertEqual(len(list(Path(self.directory.name).glob("inference-hold.resolved-*.json"))), 1)

    def test_concurrent_resume_is_idempotent_and_never_requeues_failed_job(self):
        job = self.store.enqueue(OMNI, {"size": "1344x768", "seconds": 5})
        self.store.change(job["id"], "failed", "OOM")
        self.fail()
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.recovery.request_resume(), range(8)))
        self.assertEqual(len({r["recovery_request_id"] for r in responses}), 1)
        self.assertEqual(self.store.get(job["id"])["status"], "failed")
        self.assertEqual(self.store.pending(), [])

    def test_management_contract_shared_across_ports_and_offline_scheduler(self):
        self.fail()
        with TestClient(create_app(self.store, OMNI)) as omni, TestClient(create_app(self.store, REFINER)) as refiner:
            self.assertEqual(omni.post("/v1/queue/resume", json={}).status_code, 503)
            self.store.set_state(phase="memory_cooldown")
            a = omni.post("/v1/queue/resume", json={"reason": "operator inspected"})
            b = refiner.post("/v1/queue/resume")
            self.assertEqual(a.status_code, 202, a.text)
            self.assertEqual(b.status_code, 202, b.text)
            self.assertEqual(a.json()["recovery_request_id"], b.json()["recovery_request_id"])
            self.assertFalse(a.json()["failed_jobs_retried"])
            self.assertEqual(refiner.get("/v1/queue").json()["recovery"]["incident_id"], a.json()["recovery"]["incident_id"])
            self.assertTrue(omni.get("/health").json()["queue_paused"])
            self.assertEqual(omni.post("/v1/queue/resume", json={"force": True}).status_code, 422)
            self.assertIn("/v1/queue/resume", omni.get("/openapi.json").json()["paths"])
        self.assertTrue(self.complete(self.recovery.snapshot()))
        with TestClient(create_app(self.store, OMNI)) as omni:
            self.assertEqual(omni.post("/v1/queue/resume", json={}).status_code, 200)
            self.assertFalse(omni.get("/health").json()["queue_paused"])

    def test_resource_probe_reports_host_gpu_and_unknown_failures(self):
        gpu = subprocess.CompletedProcess([], 0, "85651, 85043\n")
        empty = subprocess.CompletedProcess([], 0, "")
        with patch("video_queue_recovery.Path.read_text", return_value="MemAvailable: 41943040 kB\n"), \
                patch("video_queue_recovery.subprocess.run", side_effect=[gpu, empty]):
            self.assertTrue(probe_resources(RecoveryPolicy())["ready"])
        with patch("video_queue_recovery.Path.read_text", return_value="MemAvailable: 1048576 kB\n"), \
                patch("video_queue_recovery.subprocess.run", side_effect=[gpu, subprocess.CompletedProcess([], 0, "123\n")]):
            result = probe_resources(RecoveryPolicy())
            self.assertFalse(result["ready"])
            self.assertIn("host_memory_below_reserve", result["blockers"])
            self.assertIn("gpu_compute_process_still_running", result["blockers"])
        with patch("video_queue_recovery.Path.read_text", side_effect=OSError("unavailable")):
            self.assertFalse(probe_resources(RecoveryPolicy())["ready"])
        with patch("video_queue_recovery.Path.read_text", return_value="MemAvailable: 41943040 kB\n"), \
                patch("video_queue_recovery.subprocess.run", side_effect=[subprocess.CompletedProcess([], 0, "85651, 1000\n"), empty]):
            self.assertIn("gpu_memory_not_released", probe_resources(RecoveryPolicy())["blockers"])


class RecoverySchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_ooms_stop_third_job_until_manual_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QueueStore(directory)
            store.initialize()
            jobs = [store.enqueue(OMNI, {"size": "1344x768", "seconds": 5}) for _ in range(3)]
            scheduler = Scheduler(store)
            scheduler.recovery = QueueRecovery(store, RecoveryPolicy(cooldown_seconds=0))
            attempts = []

            async def execute(job):
                attempts.append(job["id"])
                store.claim([job["id"]], "fake.service")
                raise MemoryError("CUDA out of memory")

            original_state = scheduler.state
            def state(phase):
                original_state(phase)
                if phase == "memory_circuit_open":
                    scheduler.stop.set()

            with patch.object(store, "migrate_refiner"), patch.object(scheduler, "execute_omni", new=execute), \
                    patch.object(scheduler, "external_busy", new=AsyncMock(return_value=False)), \
                    patch.object(scheduler, "acquire", return_value=True), patch.object(scheduler, "state", new=state), \
                    patch("video_gpu_scheduler.systemctl", new=AsyncMock(return_value="inactive")), \
                    patch("video_gpu_scheduler.probe_resources", return_value=HEALTHY):
                await asyncio.wait_for(scheduler.run(), 8)
            self.assertEqual(attempts, [j["id"] for j in jobs[:2]])
            self.assertEqual([store.get(j["id"])["status"] for j in jobs], ["failed", "failed", "queued"])
            self.assertTrue(scheduler.recovery.snapshot()["manual_resume_required"])

            # A fresh scheduler preserves the circuit; HTTP confirmation releases only job 3.
            restarted = Scheduler(store)
            restarted.recovery = QueueRecovery(store, RecoveryPolicy(cooldown_seconds=0, probe_interval_seconds=0))

            async def complete(job):
                attempts.append(job["id"])
                store.claim([job["id"]], "fake.service")
                store.change(job["id"], "completed")
                restarted.stop.set()

            with patch.object(store, "migrate_refiner"), patch.object(restarted, "execute_omni", new=complete), \
                    patch.object(restarted, "external_busy", new=AsyncMock(return_value=False)), \
                    patch.object(restarted, "acquire", return_value=True), \
                    patch("video_gpu_scheduler.systemctl", new=AsyncMock(return_value="inactive")), \
                    patch("video_gpu_scheduler.probe_resources", return_value=HEALTHY):
                task = asyncio.create_task(restarted.run())
                try:
                    for _ in range(100):
                        if store.state().get("phase") == "memory_circuit_open":
                            break
                        await asyncio.sleep(0.01)
                    with TestClient(create_app(store, REFINER)) as api:
                        response = api.post("/v1/queue/resume", json={"reason": "inspected"})
                        self.assertEqual(response.status_code, 202, response.text)
                    await asyncio.wait_for(task, 5)
                finally:
                    if not task.done():
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
            self.assertEqual(attempts, [j["id"] for j in jobs])
            self.assertEqual([store.get(j["id"])["status"] for j in jobs], ["failed", "failed", "completed"])

    async def test_cleanup_failure_retries_cleanup_without_dispatch_or_resource_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QueueStore(directory)
            store.initialize()
            scheduler = Scheduler(store)
            scheduler.recovery = QueueRecovery(store, RecoveryPolicy(cooldown_seconds=0))
            scheduler.recovery.record_failure([], "OOM", [])
            with patch("video_gpu_scheduler.systemctl", new=AsyncMock(side_effect=RuntimeError("stop failed"))), \
                    patch("video_gpu_scheduler.probe_resources", return_value=HEALTHY):
                self.assertTrue(await scheduler.recover_memory())
                self.assertFalse(scheduler.recovery.snapshot()["cleanup_complete"])
            with patch("video_gpu_scheduler.systemctl", new=AsyncMock(return_value="inactive")), \
                    patch("video_gpu_scheduler.probe_resources", return_value=HEALTHY):
                self.assertFalse(await scheduler.recover_memory())
                self.assertFalse(scheduler.recovery.snapshot()["paused"])


if __name__ == "__main__":
    unittest.main()
