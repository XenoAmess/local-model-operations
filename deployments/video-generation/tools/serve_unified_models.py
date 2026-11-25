#!/usr/bin/env python3
"""CPU frontend for the existing shared GPU queue and the Bifrost provider."""
from contextlib import asynccontextmanager
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import httpx
from pydantic import BaseModel, Field

from blender_review import (
    MAX_IMAGES, MAX_UPLOAD, SOURCE, ReviewRequest, inspect_archive, ready as blender_ready,
    resolve_manifest, valid_sha, validate_samples,
)
from queued_llm import SUPPORTED_OPERATIONS
from video_queue import OMNI, REFINER, QueueConflict, QueueStore, ServiceUnavailable
from video_service_state import service_status

BIFROST = "http://127.0.0.1:8081"
TERMINAL = {"completed", "failed", "cancelled"}
EDGE_VIDEO = re.compile(r"^videos(?:/video_gen_[a-f0-9]+(?::openai)?(?:/(?:content|logs))?|/regenerations)?$")
FORWARDED_HEADERS = {"accept", "authorization", "content-type", "if-none-match", "range", "idempotency-key"}
RESPONSE_HEADERS = {"accept-ranges", "content-disposition", "content-length", "content-range", "content-type", "etag"}


class Preferences(BaseModel):
    model_config = {"extra": "forbid"}
    default_seconds: int = Field(default=3600, ge=0, le=86400, strict=True)
    models: dict[str, int] = Field(default_factory=dict)


def create_app(store=None, *, bifrost=BIFROST):
    store = store or QueueStore()
    assets = store.directory / "render-assets"

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        assets.mkdir(mode=0o700, exist_ok=True)
        async with httpx.AsyncClient(timeout=httpx.Timeout(86400, connect=5), trust_env=False) as client:
            app.state.client = client
            yield

    app = FastAPI(title="Local shared model API", version="4.0", lifespan=lifespan)

    async def body(request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 32 * 1024**2:
                raise HTTPException(413, "Submit large assets using their file upload endpoint")
        try:
            decoded = json.loads(data)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, "Expected a JSON object") from error
        if not isinstance(decoded, dict):
            raise HTTPException(422, "Expected a JSON object")
        return decoded

    def enqueue(model, payload, priority=0, key=None):
        if key is not None and (not isinstance(key, str) or not key or len(key) > 200):
            raise HTTPException(422, "Idempotency-Key is too long")
        if not service_status(store)["accepting_jobs"]:
            raise HTTPException(503, "Shared queue is unavailable", headers={"Retry-After": "30"})
        try:
            return store.enqueue(model, payload, priority=priority, idempotency_key=key)
        except QueueConflict as error:
            raise HTTPException(409, str(error)) from error
        except OverflowError as error:
            raise HTTPException(429, str(error), headers={"Retry-After": "30"}) from error
        except ServiceUnavailable as error:
            raise HTTPException(503, str(error), headers={"Retry-After": "30"}) from error

    def find(task_id, kind=None):
        task = store.get(task_id)
        if not task or (kind and task["request"].get("task_kind", "video") != kind):
            raise HTTPException(404, "Unknown task")
        return task

    async def proxy(request, target, payload=None, *, extensions=False):
        headers = {key: value for key, value in request.headers.items() if key in FORWARDED_HEADERS}
        if extensions:
            headers["x-bf-passthrough-extra-params"] = "true"
        options = {"json": payload} if payload is not None else {}
        if payload is None and request.method in {"POST", "PUT", "PATCH"}:
            options["content"] = request.stream()
        client = app.state.client
        outgoing = client.build_request(request.method, target, headers=headers, params=request.query_params, **options)
        try:
            incoming = await client.send(outgoing, stream=True)
        except httpx.HTTPError as error:
            raise HTTPException(502, "Local backend is unavailable") from error
        response_headers = {key: value for key, value in incoming.headers.items() if key in RESPONSE_HEADERS}

        async def relay():
            try:
                async for chunk in incoming.aiter_raw():
                    yield chunk
            finally:
                await incoming.aclose()

        return StreamingResponse(relay(), status_code=incoming.status_code, headers=response_headers)

    @app.get("/health")
    @app.get("/v1/service/status")
    def health():
        return service_status(store)

    @app.get("/v1/models")
    def model_list():
        data = []
        for entry in store.models.values():
            data.append({"id": entry["id"], "object": "model", "owned_by": "local",
                         "capabilities": entry["capabilities"], "max_inflight": entry["max_inflight"],
                         "configured": blender_ready() if entry["adapter"] == "blender_review" else True})
        return {"object": "list", "data": data}

    @app.get("/v1/capabilities")
    def capabilities():
        return {"schema_version": 1, "models": model_list()["data"],
                "render": {"kind": "blender_review", "source_commit": SOURCE, "engine": "EEVEE",
                           "blender_version": "5.3.0", "max_upload_bytes": MAX_UPLOAD, "max_images": MAX_IMAGES,
                           "resolution_per_side": [128, 4096], "samples": [1, 128], "max_gpu_tasks": 1}}

    @app.get("/v1/queue/preferences")
    def preferences():
        return {"default_seconds": store.registry["default_residency_seconds"], "models": {}, **store.preferences()}

    @app.put("/v1/queue/preferences")
    def update_preferences(request: Preferences):
        if any(name not in store.models or type(seconds) is not int or not 0 <= seconds <= 86400
               for name, seconds in request.models.items()):
            raise HTTPException(422, "Use registered model names and integer seconds between 0 and 86400")
        return store.set_preferences(request.model_dump())

    @app.get("/v1/usage")
    def usage():
        rows, more = store.list_jobs(statuses=["completed", "failed", "cancelled"], limit=50)
        result = []
        for row in rows:
            view = store.public(row)
            receipt = view.get("result", {})
            result.append({"task_id": row["id"], "model": row["model"], "status": row["status"],
                           "kind": view.get("kind", "video"), "images": receipt.get("images"),
                           "run_seconds": receipt.get("render_seconds", view.get("run_seconds")),
                           "output_video_seconds": view.get("seconds"), "size": view.get("size"),
                           "cost_estimate": receipt["metering"] if isinstance(receipt.get("metering"), dict) else None,
                           "metering": "see_bifrost_for_gateway_requests"})
        return {"object": "list", "data": result, "has_more": more}

    @app.api_route("/v1/queue", methods=["GET"])
    @app.api_route("/v1/queue/{suffix:path}", methods=["GET", "POST", "PATCH", "DELETE"])
    @app.api_route("/v1/service/maintenance", methods=["POST"])
    @app.api_route("/v1/files", methods=["POST"])
    async def shared_control(request: Request, suffix=""):
        return await proxy(request, store.models[OMNI]["api_url"] + request.url.path)

    def video_payload(data, *, outward=False):
        data = dict(data)
        name = data.get("model", REFINER if "input_video" in data else OMNI)
        model = store.models.get(name)
        if not model or model["adapter"] not in {"omni", "ic"}:
            raise HTTPException(422, "Select a registered video model")
        data["model"] = name
        if outward and type(data.get("seconds")) is int:
            data["seconds"] = str(data["seconds"])
        if model["adapter"] == "ic":
            item = data.get("input_video")
            if isinstance(item, dict) and isinstance(item.get("job_id"), str):
                data["input_video"] = dict(item, job_id=item["job_id"].removesuffix(":openai"))
            if outward and not data.get("prompt"):
                data["video_uri"] = "local-source://queued-input"
            if not outward:
                data.pop("video_uri", None)
                data.pop("seconds", None)
        return name, data

    @app.post("/v1/videos")
    @app.post("/v1/videos/regenerations")
    async def provider_video(request: Request):
        name, data = video_payload(await body(request))
        suffix = "/regenerations" if store.models[name]["adapter"] == "ic" else ""
        return await proxy(request, store.models[name]["api_url"] + "/v1/videos" + suffix, data)

    @app.get("/v1/videos")
    def list_videos(model: str | None = None, limit: int = 20):
        if model is not None and model not in {OMNI, REFINER}:
            raise HTTPException(422, "Choose a video model")
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Limit must be between 1 and 100")
        names = [model] if model else [OMNI, REFINER]
        rows = [row for name in names for row in store.list_jobs(model=name, limit=limit)[0]]
        rows.sort(key=lambda row: (row["created"], row["id"]), reverse=True)
        return {"object": "list", "data": [store.public(row) for row in rows[:limit]]}

    @app.api_route("/v1/videos/{task_id}", methods=["GET", "DELETE"])
    @app.get("/v1/videos/{task_id}/{operation}")
    async def provider_video_result(request: Request, task_id: str, operation=""):
        job = find(task_id, "video")
        name = job["model"]
        if not operation and request.method == "GET":
            value = store.public(job)
            if value["status"] == "cancelled":
                value.update(status="failed", error={"code": "cancelled", "message": "Video cancelled"})
            return value
        if operation not in {"", "content", "logs"}:
            raise HTTPException(404, "Unknown video operation")
        return await proxy(request, store.models[name]["api_url"] + request.url.path)

    @app.api_route("/ingress/{trail:path}", methods=["GET", "POST", "DELETE"])
    async def edge_video(request: Request, trail: str):
        if not EDGE_VIDEO.fullmatch(trail):
            raise HTTPException(404, "Unknown video route")
        if request.method == "POST" and trail in {"videos", "videos/regenerations"}:
            _, data = video_payload(await body(request), outward=True)
            return await proxy(request, bifrost + "/v1/videos", data, extensions=True)
        # Native Bifrost IDs go through its completion accounting; historic IDs
        # remain directly usable for status and content.
        if trail.endswith(("/content", "/logs")) or request.method == "DELETE" or ":" not in trail:
            return await proxy(request, "http://127.0.0.1:8006/v1/" + trail.replace(":openai", ""))
        target = bifrost
        return await proxy(request, target + "/v1/" + trail)

    @app.put("/v1/render/assets/{digest}")
    async def upload_render_archive(digest: str, request: Request):
        if not valid_sha(digest):
            raise HTTPException(422, "Supply a lowercase SHA-256 digest")
        if request.headers.get("content-type", "").split(";")[0] != "application/zip":
            raise HTTPException(415, "Send an application/zip body")
        path = assets / (digest + ".zip")
        temp = assets / (uuid.uuid4().hex + ".partial")
        size = 0
        computed = hashlib.sha256()
        try:
            with temp.open("xb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, "Archive exceeds 2 GiB")
                    computed.update(chunk)
                    output.write(chunk)
            if computed.hexdigest() != digest:
                raise HTTPException(422, "Archive SHA-256 mismatch")
            try:
                inspect_archive(temp)
            except (ValueError, zipfile.BadZipFile, UnicodeError) as error:
                raise HTTPException(422, str(error)) from error
            created = True
            try:
                os.link(temp, path)
            except FileExistsError:
                created = False
            return JSONResponse({"sha256": digest, "bytes": size, "cached": not created},
                                status_code=201 if created else 200)
        finally:
            temp.unlink(missing_ok=True)

    def stage_render(value, key):
        if not blender_ready():
            raise HTTPException(503, "Pinned Blender runtime or recipe is unavailable")
        path = assets / (value.input_sha256 + ".zip")
        if not path.is_file():
            raise HTTPException(404, "Upload the input ZIP first")
        try:
            validate_samples(value.params)
            manifest, names = inspect_archive(path)
            resolve_manifest(manifest, names, value.params)
        except (ValueError, zipfile.BadZipFile, UnicodeError) as error:
            raise HTTPException(422, str(error)) from error
        payload = value.model_dump(exclude={"priority"})
        payload.update(task_kind="blender_review", source_commit=SOURCE, archive_path=str(path))
        return enqueue("blender-review", payload, value.priority, key)

    @app.post("/v1/render/jobs", status_code=202)
    def submit_render(request: Request, value: ReviewRequest):
        job = stage_render(value, request.headers.get("idempotency-key"))
        return dict(store.public(job), job_id=job["id"], result_url=f"/v1/render/jobs/{job['id']}/result")

    @app.get("/v1/render/jobs/{job_id}")
    def render_status(job_id: str):
        return store.public(find(job_id, "blender_review"))

    @app.delete("/v1/render/jobs/{job_id}", status_code=202)
    def render_cancel(job_id: str):
        find(job_id, "blender_review")
        job, active = store.cancel(job_id, "Cancelled by client")
        return dict(store.public(job), worker_stop_pending=active)

    @app.get("/v1/render/jobs/{job_id}/result")
    def render_result(job_id: str):
        job = find(job_id, "blender_review")
        if job["status"] != "completed":
            raise HTTPException(409, "Render result is not ready")
        folder = Path(job["directory"])
        meta = json.loads((folder / "result-meta.json").read_text())
        return FileResponse(folder / "result.zip", media_type="application/zip", filename=job_id + ".zip",
                            headers={"X-Result-SHA256": meta["sha256"]})

    @app.get("/v1/render/jobs/{job_id}/images/{image_path:path}")
    def image_result(job_id: str, image_path: str):
        job = find(job_id, "blender_review")
        if job["status"] != "completed":
            raise HTTPException(409, "Render result is not ready")
        root = (Path(job["directory"]) / "blender/output").resolve()
        path = (root / image_path).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != ".png" or not path.is_file():
            raise HTTPException(404, "Unknown output image")
        return FileResponse(path, media_type="image/png")

    @app.post("/v1/images/generations")
    async def provider_render(request: Request):
        """Bifrost's async image job awaits the same renderer and records real image outputs."""
        data = await body(request)
        if data.get("model") != "blender-review" or not isinstance(data.get("render"), dict):
            raise HTTPException(422, "Provide model=blender-review and the render request")
        try:
            params = ReviewRequest.model_validate(data["render"])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        job = await asyncio.to_thread(stage_render, params, data.get("render_idempotency_key"))
        while True:
            state = find(job["id"], "blender_review")
            if state["status"] in TERMINAL:
                break
            if await request.is_disconnected():
                return JSONResponse({"error": {"message": "Gateway disconnected"}}, status_code=499)
            await asyncio.sleep(0.5)
        if state["status"] != "completed":
            raise HTTPException(409, state["error"] or state["status"])
        folder = Path(state["directory"]) / "blender/output"
        images = sorted(folder.rglob("*.png"))
        if not images or len(images) > MAX_IMAGES:
            raise HTTPException(502, "Unexpected render output count")
        meta = json.loads((Path(state["directory"]) / "result-meta.json").read_text())
        metering = meta.get("metering")
        # Only one completed provider response per task may enter image billing.
        if not store.claim_metering(job["id"], "bifrost_image"):
            raise HTTPException(409, f"Task already reported: {job['id']}")
        lan = os.environ.get("UNIFIED_PUBLIC_URL", "http://192.168.1.11:8080").rstrip("/")
        result = {"id": job["id"], "model": job["model"], "created": int(time.time()),
                  "size": "x".join(map(str, params.params.resolution)),
                  "data": [{"url": f"{lan}/v1/render/jobs/{job['id']}/images/{image.relative_to(folder).as_posix()}"}
                           for image in images]}
        if isinstance(metering, dict):
            result["usage"] = {"cost": {"total_cost": metering["amount"]}}
        return result

    @app.post("/v1/{operation:path}")
    async def inference(operation: str, request: Request):
        if operation not in SUPPORTED_OPERATIONS:
            raise HTTPException(404, "Unknown inference operation")
        data = await body(request)
        name = data.get("model")
        if name not in store.models or store.models[name]["adapter"] != "openai_llm":
            raise HTTPException(422, "Select a registered language model")
        job = enqueue(name, {"task_kind": "llm", "operation": operation, "body": data})
        job_id = job["id"]
        folder = Path(job["directory"])
        metadata = folder / "response-meta.json"
        for_wait = 0.15
        while True:
            state = find(job_id)
            if metadata.exists() and (state["status"] in TERMINAL or json.loads(metadata.read_text())["stream"]):
                break
            if state["status"] in TERMINAL:
                return JSONResponse({"error": {"message": state["error"] or state["status"]}},
                                    status_code=409 if state["status"] == "cancelled" else 502,
                                    headers={"x-local-task-id": job_id})
            if await request.is_disconnected():
                store.cancel(job_id, "Request disconnected")
                return JSONResponse({"error": {"message": "Client disconnected"}}, status_code=499)
            await asyncio.sleep(for_wait)
        info = json.loads(metadata.read_text())
        headers = {"x-local-task-id": job_id}
        path = folder / info["filename"]
        if not info["stream"]:
            return FileResponse(path, status_code=info["status_code"], media_type=info["content_type"], headers=headers)

        async def chunks():
            try:
                with path.open("rb") as stream:
                    while True:
                        available = stream.read(65536)
                        if available:
                            yield available
                        elif find(job_id)["status"] in TERMINAL:
                            return
                        else:
                            await asyncio.sleep(0.05)
            finally:
                if find(job_id)["status"] not in TERMINAL:
                    store.cancel(job_id, "Stream disconnected")

        return StreamingResponse(chunks(), media_type=info["content_type"], headers=headers)

    return app


app = create_app()
