#!/usr/bin/env python3
"""Two CPU-only HTTP frontends backed by one durable GPU queue."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time
from typing import Literal
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from video_queue import HOLD, MODELS, OMNI, REFINER, ROOT, QueueStore
from h3_refiner_profiles import PROFILES, RefinerSize


class OmniRequest(BaseModel):
    model_config = {"extra": "forbid"}
    model: Literal["fasth3-omni-bf16"] = OMNI
    task: Literal["ref2va"] = "ref2va"
    prompt: str = Field(min_length=1, max_length=50000)
    seconds: int = Field(default=5, ge=5, le=15)
    size: Literal["832x480", "1344x768", "768x1344", "768x768"] = "1344x768"
    seed: int = Field(default=1234, ge=0, lt=2**62)
    num_inference_steps: Literal[8] = 8
    guidance_scale: Literal[1.0] = 1.0
    negative_prompt: Literal[""] = ""
    image_reference: list[dict] = Field(default_factory=list)
    video_reference: list[dict] = Field(default_factory=list)
    audio_reference: list[dict] = Field(default_factory=list)


class RefinerRequest(BaseModel):
    model_config = {"extra": "forbid"}
    model: Literal["open-h3-2k"] = REFINER
    input_video: str | dict
    prompt: str = Field(default="", max_length=50000)
    size: RefinerSize = "2560x1440"
    seed: int = Field(default=1234, ge=0, lt=2**62)
    sampler: Literal["up3", "up4", "hf8"] = "up3"


def create_app(store=None, model=None):
    store = store or QueueStore()
    model = model or os.environ.get("VIDEO_HTTP_MODEL", OMNI)
    if model not in MODELS:
        raise ValueError("Unsupported HTTP model")

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(title=f"Local {model}", version="2.0", lifespan=lifespan,
                  description="Persistent asynchronous tasks; shared single-GPU scheduler with model affinity.")

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        limit = 513 * 1024**2 if request.url.path == "/v1/files" else 64 * 1024**2
        try:
            size = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        if size > limit:
            return JSONResponse({"detail": "Upload media separately through /v1/files"}, status_code=413)
        return await call_next(request)

    def find(job_id):
        job = store.get(job_id)
        if job is None or job["model"] != model:
            raise HTTPException(404, "Unknown task on this model endpoint")
        return job

    def resolve(value, kind):
        try:
            return store.resolve_media(value, kind)
        except FileNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def enqueue(payload, dependency=None):
        try:
            return store.public(store.enqueue(model, payload, dependency))
        except OverflowError as error:
            raise HTTPException(429, str(error)) from error

    @app.get("/health")
    def health():
        state = store.state()
        return {"status": "ok", "model": model, "queue": len([j for j in store.pending() if j["model"] == model]),
                "cloud_used": False, "queue_paused": HOLD.exists(), "scheduling": "shared_model_affinity",
                "scheduler_online": state.get("phase") != "stopped" and time.time() - state.get("heartbeat", 0) < 15,
                "active_model": state.get("active_model"), "worker_state": state.get("phase", "not_started")}

    @app.get("/v1/models")
    def models():
        info = {"id": model, "object": "model", "owned_by": "local", "shared_gpu_queue": True}
        if model == OMNI:
            info.update(root=str(ROOT / "models/FastH3-Omni-BF16"),
                        checkpoint="FastVideo/FastVideo-FastH3-Omni-8-Step-V1", dtype="BF16", decoder_layers=36,
                        num_inference_steps=8, sizes=["1344x768", "768x1344", "832x480", "768x768"])
        else:
            info.update(root=str(ROOT / "models/Open-H3-Regenerate-2K-IC"),
                        sizes=list(PROFILES), draft_generation=False,
                        native_resolutions=True, four_k_max_windows_per_load=1)
        return {"object": "list", "data": [info]}

    @app.get("/v1/queue")
    def queue():
        return store.snapshot()

    @app.post("/v1/files")
    async def upload(file: UploadFile = File(...)):
        extension = Path(file.filename or "").suffix.lower()
        allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
                   ".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
        if extension not in allowed:
            raise HTTPException(415, "Unsupported media format")
        file_id = "file_" + uuid.uuid4().hex
        path = store.uploads / (file_id + extension)
        size = 0
        try:
            with path.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 512 * 1024**2:
                        raise HTTPException(413, "File exceeds 512 MiB")
                    stream.write(chunk)
            store.add_file(file_id, path, Path(file.filename).name, size)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {"id": file_id, "object": "file", "filename": Path(file.filename).name, "bytes": size}

    if model == OMNI:
        @app.post("/v1/videos", status_code=202)
        def generate(request: OmniRequest):
            if not request.prompt.strip() or not (request.image_reference or request.video_reference):
                raise HTTPException(422, "Provide a prompt and at least one image or video")
            groups = [("image", request.image_reference, 9), ("video", request.video_reference, 3),
                      ("audio", request.audio_reference, 3)]
            if sum(len(items) for _, items, _ in groups) > 12 or any(len(items) > cap for _, items, cap in groups):
                raise HTTPException(422, "At most 9 images, 3 videos, 3 audio; 12 total")
            payload = request.model_dump(exclude={"image_reference", "video_reference", "audio_reference"})
            payload["mode"] = "omni"
            payload["references"] = [{"kind": kind, "path": resolve(value, kind)}
                                     for kind, items, _ in groups for value in items]
            return enqueue(payload)
    else:
        @app.post("/v1/videos/regenerations", status_code=202)
        def regenerate(request: RefinerRequest):
            payload = request.model_dump()
            payload["mode"] = "regenerate"
            source = request.input_video
            dependency = source.get("job_id") if isinstance(source, dict) else None
            if dependency:
                parent = store.get(dependency)
                if parent is None:
                    raise HTTPException(404, "Unknown source job")
                if parent["model"] != OMNI:
                    raise HTTPException(422, "job_id must reference a BF16 Omni draft")
                if parent["status"] in {"failed", "cancelled"}:
                    raise HTTPException(409, "Source job failed or was cancelled")
                payload["input_video"] = {"job_id": dependency}
            else:
                payload["input_video"] = resolve(source, "video")
            return enqueue(payload, dependency)

    @app.get("/v1/videos")
    def list_jobs(limit: int = 20):
        with store.connection() as db:
            rows = db.execute("SELECT * FROM jobs WHERE model=? ORDER BY created DESC LIMIT ?",
                              (model, min(max(limit, 1), 100))).fetchall()
        jobs = [store.public(store.decode(row)) for row in rows]
        return {"object": "list", "data": jobs, "has_more": False}

    @app.get("/v1/videos/{job_id}")
    def status(job_id: str):
        return store.public(find(job_id))

    @app.get("/v1/videos/{job_id}/content")
    def content(job_id: str):
        job = find(job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "Video has not completed")
        return FileResponse(Path(job["directory"]) / "result.mp4", media_type="video/mp4", filename=job_id + ".mp4")

    @app.get("/v1/videos/{job_id}/logs", response_class=PlainTextResponse)
    def logs(job_id: str):
        job = find(job_id)
        path = Path(job["directory"]) / "worker.log"
        if job["status"] == "in_progress" and model == REFINER and job["unit"]:
            batch_log = store.directory / "batches" / job["unit"].removesuffix(".service") / "worker.log"
            if batch_log.is_file():
                path = batch_log
        if not path.exists():
            return "Task has not started"
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 16000))
            return stream.read().decode(errors="replace")

    @app.delete("/v1/videos/{job_id}")
    def cancel(job_id: str):
        job = find(job_id)
        if job["status"] in {"queued", "in_progress"}:
            store.change(job_id, "cancelled")
            store.event("cancel_requested", job=job_id, model=model)
        return store.public(store.get(job_id))

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("VIDEO_HTTP_PORT", "8001")),
                timeout_keep_alive=300)
