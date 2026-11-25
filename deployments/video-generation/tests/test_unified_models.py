import asyncio
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile

from fastapi.testclient import TestClient
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from model_registry import select_job
from queued_llm import execute_llm_job
from serve_unified_models import create_app
from video_queue import OMNI, REFINER, QueueConflict, QueueStore


class UnifiedModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QueueStore(Path(self.temp.name))
        self.store.initialize()
        self.store.set_state(phase="idle")

    def tearDown(self):
        self.temp.cleanup()

    def test_protection_and_safe_release(self):
        a = {"id": "omni", "model": OMNI, "created": 2, "priority": 0}
        b = {"id": "qwen", "model": "qwen38-coder", "created": 1, "priority": 1000}
        self.assertEqual(select_job([a, b], OMNI, 10, 3600, now=3609), a)
        self.assertEqual(select_job([a, b], OMNI, 10, 3600, now=3610), b)
        self.assertEqual(select_job([b], OMNI, 10, 3600, now=11), b)
        self.assertEqual(select_job([a, b], OMNI, None, 3600, now=9000), a)

    def test_preferences_and_dependency(self):
        parent = self.store.enqueue(OMNI, {"size": "832x480"})
        dependent = self.store.enqueue(REFINER, {"size": "3840x2160"}, dependency=parent["id"])
        self.store.set_state(phase="idle", active_model=REFINER, model_ready_at=time.time())
        with TestClient(create_app(self.store)) as client:
            prefs = client.get("/v1/queue/preferences").json()
            self.assertEqual(prefs["default_seconds"], 3600)
            self.assertEqual(client.put("/v1/queue/preferences", json={
                "default_seconds": 3600, "models": {OMNI: 600}}).status_code, 200)
            self.assertEqual(client.put("/v1/queue/preferences", json={
                "default_seconds": 3600, "models": {"unknown": 5}}).status_code, 422)
            snap = self.store.snapshot()
            self.assertEqual(snap["queued"][0]["id"], parent["id"])
            self.assertEqual(snap["waiting_for_source"][0]["id"], dependent["id"])
            self.assertEqual(len(client.get("/v1/models").json()["data"]), 4)

    def test_idempotency_and_metering(self):
        payload = {"task_kind": "blender_review", "params": {"samples": 32}}
        first = self.store.enqueue("blender-review", payload, idempotency_key="one")
        self.assertEqual(first["id"], self.store.enqueue("blender-review", payload, idempotency_key="one")["id"])
        with self.assertRaises(QueueConflict):
            self.store.enqueue("blender-review", dict(payload, params={"samples": 33}), idempotency_key="one")
        self.assertFalse(self.store.claim_metering(first["id"], "bifrost_image"))
        self.store.claim([first["id"]], "test.service")
        self.store.change(first["id"], "completed", only_running=True)
        self.assertTrue(self.store.claim_metering(first["id"], "bifrost_image"))
        self.assertFalse(self.store.claim_metering(first["id"], "bifrost_image"))
        self.assertEqual(self.store.public(self.store.get(first["id"]))["kind"], "blender_review")

    def test_public_video_status_keeps_bifrost_id_and_reads_queue(self):
        job = self.store.enqueue(OMNI, {"size": "832x480", "seconds": 5})
        public_id = job["id"] + ":openai"
        with TestClient(create_app(self.store, bifrost="http://127.0.0.1:1")) as client:
            response = client.get("/ingress/videos/" + public_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["id"], public_id)
            self.assertEqual(response.json()["status"], "queued")
            self.store.change(job["id"], "cancelled")
            response = client.get("/ingress/videos/" + public_id)
            self.assertEqual(response.json()["status"], "failed")

    def test_sha_upload_and_archive_validation(self):
        def zip_with(entry):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                archive.writestr("manifest.json", '{"forms": {}}')
                archive.writestr(entry, b"fixture")
            return stream.getvalue()

        with TestClient(create_app(self.store)) as client:
            good = zip_with("assets/a.blend")
            uri = "/v1/render/assets/" + sha256(good).hexdigest()
            headers = {"Content-Type": "application/zip"}
            self.assertEqual(client.put(uri, content=good, headers=headers).status_code, 201)
            self.assertEqual(client.put(uri, content=good, headers=headers).status_code, 200)
            self.assertEqual(client.put(uri, content=b"wrong", headers=headers).status_code, 422)
            bad = zip_with("../escape.blend")
            self.assertEqual(client.put("/v1/render/assets/" + sha256(bad).hexdigest(),
                                        content=bad, headers=headers).status_code, 422)

    def test_llm_stream_spool_preserves_tool_chunks(self):
        async def scenario():
            chunk = b'data: {"choices":[{"delta":{"tool_calls":[{"index":0}]} }]}\n\ndata: [DONE]\n\n'
            data = {"model": "qwen38-coder", "stream": True, "tools": [{"type": "function"}]}
            job = self.store.enqueue("qwen38-coder", {"task_kind": "llm", "operation": "chat/completions", "body": data})
            self.store.claim([job["id"]], "test.service")

            async def native(request):
                self.assertEqual(json.loads(request.content), data)
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=chunk)

            async with httpx.AsyncClient(transport=httpx.MockTransport(native)) as client:
                await execute_llm_job(self.store, job, "http://test", client, asyncio.Event())
            self.assertEqual(self.store.get(job["id"])["status"], "completed")
            self.assertEqual((Path(job["directory"]) / "response.sse").read_bytes(), chunk)
        asyncio.run(scenario())
