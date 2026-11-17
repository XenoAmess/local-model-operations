"""Exercise persistent job records and media boundaries without running inference."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location(
    "h3_http", Path(__file__).resolve().parents[1] / "tools/serve_h3_2k_http.py")
API = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(API)


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        API.DATA = Path(self.temp.name)
        API.JOBS, API.UPLOADS, API.DB = API.DATA / "jobs", API.DATA / "uploads", API.DATA / "jobs.sqlite3"
        API.HOLD, API.GPU_LOCK = API.DATA / "hold.json", API.DATA / "gpu.lock"
        self.busy = patch.object(API, "gpu_busy", new=AsyncMock(return_value=True))
        self.busy.start()
        self.addCleanup(self.busy.stop)

    def upload(self, client, name="reference.png"):
        response = client.post("/v1/files", files={"file": (name, b"fixture", "application/octet-stream")})
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def test_upload_submission_and_restart_preserve_job_id(self):
        with TestClient(API.app) as client:
            file_id = self.upload(client)
            response = client.post("/v1/videos", json={"prompt": "A character waves.",
                                   "image_reference": [{"file_id": file_id}], "seconds": "15"})
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["id"]
            self.assertEqual(response.json()["status"], "queued")
        with TestClient(API.app) as client:
            response = client.get("/v1/videos/" + job_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["seconds"], "15")
            self.assertEqual(client.get("/v1/videos/" + job_id + "/content").status_code, 409)

    def test_unuploaded_host_paths_and_remote_urls_are_rejected(self):
        with TestClient(API.app) as client:
            for source in ["/etc/passwd", "https://example.com/private.png"]:
                response = client.post("/v1/videos", json={"prompt": "A character waves.",
                                       "image_reference": [{"image_url": source}]})
                self.assertEqual(response.status_code, 422)

    def test_wrong_media_type_and_missing_file_id_are_rejected(self):
        with TestClient(API.app) as client:
            file_id = self.upload(client)
            response = client.post("/v1/videos/regenerations", json={"input_video": {"file_id": file_id}})
            self.assertEqual(response.status_code, 415)
            response = client.post("/v1/videos", json={"prompt": "x", "image_reference": [{"file_id": "file_missing"}]})
            self.assertEqual(response.status_code, 404)

    def test_cancelled_job_is_not_requeued_by_restart(self):
        with TestClient(API.app) as client:
            file_id = self.upload(client)
            job_id = client.post("/v1/videos", json={"prompt": "x", "image_reference": [{"file_id": file_id}]}).json()["id"]
            self.assertEqual(client.delete("/v1/videos/" + job_id).json()["status"], "cancelled")
        with TestClient(API.app) as client:
            self.assertEqual(client.get("/v1/videos/" + job_id).json()["status"], "cancelled")

    def refiner(self):
        spec = importlib.util.spec_from_file_location("refiner_http", SPEC.origin)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"H3_HTTP_MODE": "refiner", "H3_HTTP_MODEL": "open-h3-2k"}):
            spec.loader.exec_module(module)
        module.DATA = API.DATA / "refiner"
        module.JOBS, module.UPLOADS, module.DB = module.DATA / "jobs", module.DATA / "uploads", module.DATA / "jobs.sqlite3"
        module.HOLD, module.GPU_LOCK = API.HOLD, API.GPU_LOCK
        return module

    def test_refiner_accepts_only_existing_video_jobs(self):
        refiner = self.refiner()
        with patch.object(refiner, "gpu_busy", new=AsyncMock(return_value=True)), TestClient(refiner.app) as client:
            self.assertEqual(client.get("/health").json()["mode"], "refiner")
            self.assertNotIn("/v1/videos", client.get("/openapi.json").json()["paths"])
            video = self.upload(client, "draft.mp4")
            image = self.upload(client, "character.png")
            response = client.post("/v1/videos/regenerations", json={"input_video": {"file_id": video}})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["model"], "open-h3-2k")
            job_id = response.json()["id"]
            request = refiner.get_job(job_id)
            self.assertEqual(request["status"], "queued")
            with refiner.connection() as db:
                import json
                payload = json.loads(db.execute("SELECT request FROM jobs WHERE id=?", (job_id,)).fetchone()[0])
            self.assertEqual(payload["mode"], "regenerate")
            response = client.post("/v1/videos", json={"prompt": "x", "image_reference": [{"file_id": image}]})
            self.assertEqual(response.status_code, 404)
            response = client.post("/v1/videos/regenerations", json={"input_video": {"file_id": video},
                                   "image_reference": [{"file_id": image}]})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(client.delete("/v1/videos/" + job_id).json()["status"], "cancelled")

    def test_two_http_queues_share_the_same_gpu_lease(self):
        refiner = self.refiner()
        first = API.acquire_gpu_lease()
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(refiner.acquire_gpu_lease())
        finally:
            first.close()
        second = refiner.acquire_gpu_lease()
        self.assertIsNotNone(second)
        second.close()


if __name__ == "__main__":
    unittest.main()
