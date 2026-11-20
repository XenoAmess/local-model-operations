"""Operator queue changes, transaction races, maintenance and actual HTTP streaming."""

import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from serve_video_http import create_app
from video_queue import OMNI, REFINER, QueueChanged, QueueStore, choose_next
from video_service_state import service_status


class ManagementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QueueStore(self.temp.name)
        self.store.initialize()
        self.store.set_state(phase="idle", active_model=OMNI, consecutive=0)

    def job(self, model=OMNI, priority=0):
        return self.store.enqueue(model, {"size": "1344x768" if model == OMNI else "3840x2160",
                                         "seed": 1234, "sampler": "up3", "seconds": 5}, priority=priority)

    def test_promote_crosses_affinity_and_later_promote_becomes_first(self):
        a, b, c = self.job(), self.job(REFINER), self.job()
        with TestClient(create_app(self.store, OMNI)) as api:
            r = api.post(f"/v1/queue/jobs/{b['id']}/promote", json={"reason": "review"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["queue_position"], 1)
            self.assertEqual(choose_next(self.store.ready(), OMNI, 0)["id"], b["id"])
            self.assertEqual(api.post(f"/v1/queue/jobs/{c['id']}/promote").json()["queue_position"], 1)
            api.patch(f"/v1/queue/jobs/{c['id']}/priority", json={"priority": -1})
            self.assertEqual(choose_next(self.store.ready(), OMNI, 0)["id"], b["id"])

    def test_order_edit_invalidates_an_unclaimed_scheduler_selection(self):
        a, b = self.job(), self.job()
        selected = self.store.ready()[0]
        self.store.set_priority(b["id"], promote=True)
        with self.assertRaises(QueueChanged):
            self.store.claim([a["id"]], "test.service", expected_revision=selected["_queue_revision"])
        self.assertEqual(self.store.get(a["id"])["status"], "queued")

    def test_running_priority_conflict_and_cancel_terminal_race(self):
        a = self.job()
        self.store.claim([a["id"]], "test.service")
        with TestClient(create_app(self.store, OMNI)) as api:
            self.assertEqual(api.post(f"/v1/queue/jobs/{a['id']}/promote").status_code, 409)
            result = api.post(f"/v1/queue/jobs/{a['id']}/cancel")
            self.assertEqual(result.status_code, 202)
            self.store.change(a["id"], "completed", only_running=True)
            self.assertEqual(self.store.get(a["id"])["status"], "cancelled")
            self.assertEqual(api.delete(f"/v1/videos/{a['id']}").status_code, 200)
        b = self.job()
        self.store.change(b["id"], "completed")
        self.assertEqual(self.store.cancel(b["id"])[0]["status"], "completed")

    def test_pagination_filters_and_true_has_more(self):
        jobs = [self.job() for _ in range(3)]
        self.store.change(jobs[0]["id"], "failed")
        self.job(REFINER)
        with TestClient(create_app(self.store, OMNI)) as api:
            first = api.get("/v1/queue/jobs", params={"limit": 1, "status": "queued", "model": OMNI}).json()
            self.assertTrue(first["has_more"])
            second = api.get("/v1/queue/jobs", params={"limit": 1, "status": "queued", "model": OMNI,
                                                        "after": first["next_after"]}).json()
            self.assertFalse(second["has_more"])
            self.assertNotEqual(first["data"][0]["id"], second["data"][0]["id"])
            self.assertEqual(api.get("/v1/videos?status=failed").json()["data"][0]["id"], jobs[0]["id"])
            self.assertEqual(api.get("/v1/queue/jobs?after=missing").status_code, 422)
            self.assertEqual(api.get("/v1/queue/jobs?status=invalid").status_code, 422)

    def test_maintenance_drains_without_cancelling_and_blocks_dispatch_and_admission(self):
        a, b = self.job(), self.job()
        self.store.claim([a["id"]], "test.service")
        with TestClient(create_app(self.store, OMNI)) as api:
            r = api.post("/v1/service/maintenance", json={"enabled": True, "reason": "upgrade"})
            self.assertEqual(r.status_code, 202)
            self.assertEqual(api.get("/v1/service/status").json()["status"], "draining")
            self.assertEqual(api.get("/ready").status_code, 503)
            with self.assertRaises(QueueChanged):
                self.store.claim([b["id"]], "test.service")
            file_id = api.post("/v1/files", files={"file": ("ref.png", b"x")}).json()["id"]
            response = api.post("/v1/videos", json={"prompt": "wave", "image_reference": [{"file_id": file_id}]})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["Retry-After"], "30")
            self.store.change(a["id"], "completed", only_running=True)
            self.assertEqual(api.get("/v1/service/status").json()["status"], "upgrading")
            self.assertEqual(self.store.get(b["id"])["status"], "queued")
            api.post("/v1/service/maintenance", json={"enabled": False})
            self.assertEqual(api.get("/ready").status_code, 200)

    def test_full_download_records_exact_byte_count(self):
        a = self.job()
        media = b"fixture video bytes" * 10000
        (Path(a["directory"]) / "result.mp4").write_bytes(media)
        self.store.change(a["id"], "completed")
        with TestClient(create_app(self.store, OMNI)) as api:
            response = api.get(f"/v1/videos/{a['id']}/content")
            self.assertEqual(response.content, media)
        with self.store.connection() as db:
            rows = db.execute("SELECT detail FROM events WHERE event='content_delivery_complete'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["bytes_sent"], len(media))

    def test_cancelled_worker_keeps_status_busy_until_teardown_is_confirmed(self):
        a = self.job()
        self.store.claim([a["id"]], "test.service")
        self.store.set_state(phase="refiner_batch", running_jobs=[a["id"]])
        with TestClient(create_app(self.store, OMNI)) as api:
            for _ in range(2):
                self.assertTrue(api.post(f"/v1/queue/jobs/{a['id']}/cancel").json()["worker_stop_pending"])
            self.assertEqual(service_status(self.store)["status"], "busy")
            self.store.set_state(phase="idle", running_jobs=[])
            self.assertEqual(service_status(self.store)["status"], "available")

    def test_old_ten_column_schema_migrates_without_changing_task_id_or_state(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with sqlite3.connect(folder / "queue.sqlite3") as db:
                db.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,model TEXT,status TEXT,created REAL,updated REAL,"
                           "payload TEXT,directory TEXT,dependency TEXT,unit TEXT,error TEXT)")
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("video_gen_old", OMNI, "completed", 1, 2,
                           '{"size":"1344x768"}', str(folder / "old"), None, None, None))
            migrated = QueueStore(folder)
            migrated.initialize()
            old = migrated.get("video_gen_old")
            self.assertEqual((old["status"], old["priority"], old["front_order"]), ("completed", 0, 0))


if __name__ == "__main__":
    unittest.main()
