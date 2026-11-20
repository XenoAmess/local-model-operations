"""Check fairness, durability, cancellation and the two real HTTP contracts without GPU work."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from video_queue import OMNI, REFINER, QueueStore, choose_next, preview
from serve_video_http import create_app
from video_gpu_scheduler import Scheduler
from video_queue_recovery import QueueRecovery, RecoveryPolicy


def job(name, model, created):
    return {"id": name, "model": model, "created": created}


class PolicyTest(unittest.TestCase):
    def test_interleaved_arrivals_group_models_and_preserve_each_models_fifo(self):
        jobs = [job("a1", OMNI, 1), job("b1", REFINER, 2), job("a2", OMNI, 3),
                job("b2", REFINER, 4), job("a3", OMNI, 5), job("a4", OMNI, 6)]
        self.assertEqual([j["id"] for j in preview(jobs, now=10)], ["a1", "a2", "a3", "b1", "b2", "a4"])

    def test_age_limit_overrides_affinity_before_batch_is_full(self):
        jobs = [job("a", OMNI, 10), job("b", REFINER, 11)]
        self.assertEqual(choose_next(jobs, OMNI, 1, now=2000)["id"], "b")

    def test_empty_other_queue_does_not_force_a_pointless_switch(self):
        self.assertEqual(choose_next([job("a", OMNI, 1)], OMNI, 100, now=5)["id"], "a")


class StoreAndHttpTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QueueStore(self.temp.name)
        self.store.initialize()
        self.store.set_state(phase="idle", active_model=None, consecutive=0)

    def enqueue(self, model=OMNI, dependency=None):
        payload = {"model": model, "size": "1344x768" if model == OMNI else "2560x1440",
                   "seconds": 5, "seed": 1234, "sampler": "up3", "prompt": "wave"}
        return self.store.enqueue(model, payload, dependency)

    def test_claim_is_atomic_when_a_cohort_member_was_cancelled(self):
        a, b = self.enqueue(), self.enqueue()
        self.store.change(b["id"], "cancelled")
        with self.assertRaises(RuntimeError):
            self.store.claim([a["id"], b["id"]], "fake.service")
        self.assertEqual(self.store.get(a["id"])["status"], "queued")

    def test_frontend_restart_does_not_requeue_a_running_gpu_job(self):
        a = self.enqueue()
        self.store.claim([a["id"]], "fake.service")
        with TestClient(create_app(self.store, OMNI)):
            pass
        self.assertEqual(self.store.get(a["id"])["status"], "in_progress")

    def test_cancelled_job_survives_restart_and_is_never_ready(self):
        a = self.enqueue()
        self.store.change(a["id"], "cancelled")
        self.store.initialize()
        self.assertEqual(self.store.ready(), [])

    def test_dependencies_only_become_ready_after_success(self):
        parent = self.enqueue()
        child = self.enqueue(REFINER, parent["id"])
        self.assertEqual([j["id"] for j in self.store.ready()], [parent["id"]])
        self.store.change(parent["id"], "completed")
        self.assertEqual([j["id"] for j in self.store.ready()], [child["id"]])
        self.store.change(parent["id"], "cancelled")
        self.store.fail_dependencies()
        self.assertEqual(self.store.get(child["id"])["status"], "failed")

    def test_concurrent_enqueues_enforce_the_queue_limit_without_orphan_folders(self):
        def insert(_):
            try:
                return self.enqueue()["id"]
            except OverflowError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = [x for x in pool.map(insert, range(40)) if x]
        self.assertEqual(len(set(ids)), 32)
        self.assertEqual(len(list(self.store.jobs.iterdir())), 32)

    def test_upload_generate_dependent_refine_and_global_queue(self):
        with TestClient(create_app(self.store, OMNI)) as omni, TestClient(create_app(self.store, REFINER)) as refiner:
            image = omni.post("/v1/files", files={"file": ("character.png", b"fixture", "image/png")}).json()["id"]
            request = {"model": OMNI, "prompt": "Use <Picture 1>", "image_reference": [{"file_id": image}],
                       "num_inference_steps": 8, "seconds": "5"}
            response = omni.post("/v1/videos", json=request)
            self.assertEqual(response.status_code, 202, response.text)
            parent = response.json()["id"]
            response = refiner.post("/v1/videos/regenerations", json={"model": REFINER, "input_video": {"job_id": parent}})
            self.assertEqual(response.status_code, 202, response.text)
            child = response.json()["id"]
            snapshot = omni.get("/v1/queue").json()
            self.assertEqual(snapshot["queued"][0]["id"], parent)
            self.assertEqual(snapshot["waiting_for_source"][0]["id"], child)
            self.assertEqual(refiner.get("/v1/videos/" + parent).status_code, 404)
            self.assertEqual(omni.get("/v1/videos/" + parent + "/content").status_code, 409)
            self.assertEqual(omni.delete("/v1/videos/" + parent).json()["status"], "cancelled")
            self.store.fail_dependencies()
            self.assertEqual(refiner.get("/v1/videos/" + child).json()["status"], "failed")
            self.assertNotIn("/v1/videos/regenerations", omni.get("/openapi.json").json()["paths"])
            self.assertNotIn("post", refiner.get("/openapi.json").json()["paths"]["/v1/videos"])

    def test_bad_models_step_counts_and_host_paths_are_rejected(self):
        with TestClient(create_app(self.store, OMNI)) as client:
            base = {"prompt": "wave", "image_reference": [{"image_url": "/etc/passwd"}]}
            for extra in [{}, {"model": "fasth3-omni"}, {"num_inference_steps": 50}, {"guidance_scale": 5}]:
                self.assertEqual(client.post("/v1/videos", json=dict(base, **extra)).status_code, 422)
            self.assertEqual(client.get("/v1/models").json()["data"][0]["id"], OMNI)


class DispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancelling_one_member_before_claim_does_not_fail_its_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QueueStore(directory)
            store.initialize()
            payload = {"size": "2560x1440", "seed": 1234, "sampler": "up3"}
            first, second = [store.enqueue(REFINER, payload) for _ in range(2)]
            scheduler = Scheduler(store)
            attempts = []

            async def execute(jobs):
                attempts.append([j["id"] for j in jobs])
                if len(attempts) == 1:
                    store.change(second["id"], "cancelled")
                store.claim([j["id"] for j in jobs], "simulation.service")
                for j in jobs:
                    store.change(j["id"], "completed")
                scheduler.stop.set()

            async def release():
                scheduler.model = None

            with patch.object(store, "migrate_refiner"), patch.object(scheduler, "execute_refiner", new=execute), \
                    patch.object(scheduler, "external_busy", new=AsyncMock(return_value=False)), \
                    patch.object(scheduler, "acquire", return_value=True), \
                    patch.object(scheduler, "release", new=release), \
                    patch("video_gpu_scheduler.systemctl", new=AsyncMock(return_value="inactive")), \
                    patch("video_gpu_scheduler.HOLD", Path(directory) / "hold"):
                await asyncio.wait_for(scheduler.run(), 5)
            self.assertEqual(attempts, [[first["id"], second["id"]], [first["id"]]])
            self.assertEqual(store.get(first["id"])["status"], "completed")
            self.assertEqual(store.get(second["id"])["status"], "cancelled")

    async def test_refiner_grouping_never_changes_seeds_or_skips_earlier_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QueueStore(directory)
            store.initialize()
            jobs = [store.enqueue(REFINER, {"size": "2560x1440", "seed": seed, "sampler": "up3"})
                    for seed in [1, 2, 1]]
            scheduler = Scheduler(store)
            self.assertEqual([j["id"] for j in scheduler.cohort(jobs[0], jobs)], [jobs[0]["id"]])

    async def test_memory_failure_recovers_next_job_without_retrying_failed_job(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QueueStore(directory)
            store.initialize()
            jobs = [store.enqueue(OMNI, {"size": "1344x768", "seconds": 5}) for _ in range(2)]
            scheduler = Scheduler(store)
            scheduler.recovery = QueueRecovery(store, RecoveryPolicy(cooldown_seconds=0))
            attempts = []

            async def oom(job):
                attempts.append(job["id"])
                store.claim([job["id"]], "fake.service")
                if job["id"] == jobs[0]["id"]:
                    raise MemoryError("CUDA out of memory")
                store.change(job["id"], "completed")
                scheduler.stop.set()

            async def release():
                scheduler.model = None

            original_state = scheduler.state
            def state(phase):
                original_state(phase)

            with patch.object(store, "migrate_refiner"), patch.object(scheduler, "execute_omni", new=oom), \
                    patch.object(scheduler, "external_busy", new=AsyncMock(return_value=False)), \
                    patch.object(scheduler, "acquire", return_value=True), \
                    patch.object(scheduler, "release", new=release), patch.object(scheduler, "state", new=state), \
                    patch("video_gpu_scheduler.systemctl", new=AsyncMock(return_value="inactive")), \
                    patch("video_gpu_scheduler.probe_resources", return_value={"ready": True, "blockers": []}):
                await asyncio.wait_for(scheduler.run(), 5)
            self.assertEqual(attempts, [j["id"] for j in jobs])
            self.assertFalse(scheduler.recovery.snapshot()["paused"])
            self.assertEqual(store.get(jobs[0]["id"])["status"], "failed")
            self.assertEqual(store.get(jobs[1]["id"])["status"], "completed")

    async def test_shared_dispatch_reorders_jobs_and_never_runs_both_models_together(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QueueStore(directory)
            store.initialize()
            now = time.time()
            ids = []
            for model in [OMNI, REFINER, OMNI, REFINER, OMNI]:
                ids.append(store.enqueue(model, {"model": model, "size": "2560x1440", "seconds": 5,
                                                  "seed": 1234, "sampler": "up3"})["id"])
            scheduler = Scheduler(store)
            dispatched = []
            busy = False

            async def execute(jobs):
                nonlocal busy
                self.assertFalse(busy)
                busy = True
                store.claim([j["id"] for j in jobs], "simulation.service")
                await asyncio.sleep(0)
                for j in jobs:
                    store.change(j["id"], "completed")
                    dispatched.append(j["id"])
                busy = False
                if len(dispatched) == 5:
                    scheduler.stop.set()

            async def omni(j):
                await execute([j])

            async def release():
                scheduler.model = None
                scheduler.consecutive = 0

            with patch.object(store, "migrate_refiner"), patch.object(scheduler, "execute_omni", new=omni), \
                    patch.object(scheduler, "execute_refiner", new=execute), \
                    patch.object(scheduler, "external_busy", new=AsyncMock(return_value=False)), \
                    patch.object(scheduler, "acquire", return_value=True), \
                    patch.object(scheduler, "release", new=release), \
                    patch("video_gpu_scheduler.systemctl", new=AsyncMock(return_value="inactive")), \
                    patch("video_gpu_scheduler.HOLD", Path(directory) / "hold"):
                await asyncio.wait_for(scheduler.run(), 5)
            self.assertEqual(dispatched, [ids[0], ids[2], ids[4], ids[1], ids[3]])
            self.assertTrue(all(store.get(j)["status"] == "completed" for j in ids))


if __name__ == "__main__":
    unittest.main()
