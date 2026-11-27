#!/usr/bin/env python3
"""Two CPU-only HTTP frontends backed by one durable GPU queue."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time
from typing import Literal
import uuid

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from video_queue import HOLD, MODELS, OMNI, REFINER, ROOT, QueueConflict, QueueStore, ServiceUnavailable
from h3_refiner_profiles import PROFILES, RefinerSize
from h3_full_sequence import FPS, SINGLE_WINDOW_FRAMES
from video_queue_recovery import QueueRecovery
from video_service_state import API_VERSION, service_status


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
    priority: int = Field(default=0, ge=-1000, le=1000, strict=True)
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
    priority: int = Field(default=0, ge=-1000, le=1000, strict=True)


class QueueResumeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str = Field(default="", max_length=500)


class PriorityRequest(QueueResumeRequest):
    priority: int = Field(ge=-1000, le=1000, strict=True)


class MaintenanceRequest(QueueResumeRequest):
    enabled: bool = Field(strict=True)


JobStatus = Literal["queued", "in_progress", "completed", "failed", "cancelled"]


def create_app(store=None, model=None):
    store = store or QueueStore()
    model = model or os.environ.get("VIDEO_HTTP_MODEL", OMNI)
    if model not in MODELS:
        raise ValueError("Unsupported HTTP model")
    recovery = QueueRecovery(store)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(title=f"Local {model}", version=API_VERSION, lifespan=lifespan,
                  description="Persistent asynchronous tasks; shared single-GPU scheduler with model affinity.")
    from video_delivery import DeliveryAudit
    app.add_middleware(DeliveryAudit, store=store)

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

    def enqueue(payload, dependency=None, priority=0):
        try:
            available = service_status(store)
            if not available["accepting_jobs"]:
                raise ServiceUnavailable(available.get("reason") or "GPU scheduler is offline")
            return store.public(store.enqueue(model, payload, dependency, priority))
        except OverflowError as error:
            raise HTTPException(429, str(error)) from error
        except ServiceUnavailable as error:
            raise HTTPException(503, str(error), headers={"Retry-After": "30"}) from error

    def any_job(job_id):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown task")
        return job

    def priority_change(job_id, priority=None, promote=False, reason=""):
        try:
            job = store.set_priority(job_id, priority, promote=promote, reason=reason)
            result = store.public(job)
            order = store.snapshot()
            position = next((j["position"] for j in order["queued"] if j["id"] == job_id), None)
            return dict(result, queue_position=position, preempts_running=False)
        except FileNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except QueueConflict as error:
            raise HTTPException(409, str(error)) from error

    def cancel_job(job_id, reason=""):
        try:
            job, stopping = store.cancel(job_id, reason)
        except FileNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        stopping = stopping or (job["status"] == "cancelled" and job_id in store.state().get("running_jobs", []))
        result = dict(store.public(job), worker_stop_pending=stopping)
        return JSONResponse(result, status_code=202 if stopping else 200)

    @app.get("/health")
    def health():
        state = store.state()
        memory = recovery.snapshot()
        return {"status": "ok", "model": model, "queue": store.pending_count(model),
                "cloud_used": False, "queue_paused": memory["paused"], "recovery": memory,
                "scheduling": "shared_model_affinity",
                "scheduler_online": state.get("phase") != "stopped" and time.time() - state.get("heartbeat", 0) < 15,
                "active_model": state.get("active_model"), "worker_state": state.get("phase", "not_started"),
                "service": service_status(store), "api_version": API_VERSION}

    @app.get("/v1/service/status", tags=["Service status"])
    def availability():
        return JSONResponse(service_status(store), headers={"Cache-Control": "no-store"})

    @app.get("/ready", tags=["Service status"])
    def readiness():
        value = service_status(store)
        return JSONResponse(value, status_code=200 if value["ready"] else 503,
                            headers={"Cache-Control": "no-store", **({} if value["ready"] else {"Retry-After": "30"})})

    @app.post("/v1/service/maintenance", tags=["Queue administration"])
    def maintenance(request: MaintenanceRequest):
        """Drain at task boundaries. Keep polling, downloads, cancellation and recovery available."""
        store.maintenance(request.enabled, request.reason)
        return JSONResponse({"accepted": True, "service": service_status(store), "running_jobs_interrupted": False},
                            status_code=202 if request.enabled else 200)

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
                        native_resolutions=True, four_k_max_windows_per_load=1,
                        long_4k_strategy="full_sequence", single_window_frame_limit=SINGLE_WINDOW_FRAMES, timeline_fps=FPS,
                        long_4k_threshold_seconds=SINGLE_WINDOW_FRAMES / FPS,
                        long_4k_threshold_rule=f"normalized_frames > {SINGLE_WINDOW_FRAMES}",
                        long_4k_independent_window_fallback=False)
        return {"object": "list", "data": [info]}

    @app.get("/v1/queue")
    def queue():
        return store.snapshot()

    def browse(model_filter=None, statuses=None, limit=20, after=None):
        try:
            jobs, more = store.list_jobs(model=model_filter, statuses=statuses, limit=limit, after=after)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        positions = {j["id"]: j["position"] for j in store.snapshot()["queued"]}
        values = [dict(store.public(j), queue_position=positions.get(j["id"])) for j in jobs]
        return {"object": "list", "data": values, "has_more": more,
                "next_after": jobs[-1]["id"] if more and jobs else None,
                "list_order": "created_desc", "queue_order": "model_residency_then_priority_and_front_order"}

    @app.get("/v1/queue/jobs", tags=["Queue administration"])
    def browse_queue(model: str | None = None,
                     status: list[JobStatus] | None = Query(default=None),
                     limit: int = Query(default=20, ge=1, le=100), after: str | None = None):
        return browse(model, status, limit, after)

    @app.get("/v1/queue/jobs/{job_id}", tags=["Queue administration"])
    def global_status(job_id: str):
        return store.public(any_job(job_id))

    @app.patch("/v1/queue/jobs/{job_id}/priority", tags=["Queue administration"])
    def reprioritize(job_id: str, request: PriorityRequest):
        return priority_change(job_id, request.priority, reason=request.reason)

    @app.post("/v1/queue/jobs/{job_id}/promote", tags=["Queue administration"])
    def promote(job_id: str, request: QueueResumeRequest | None = None):
        return priority_change(job_id, promote=True, reason=request.reason if request else "")

    @app.post("/v1/queue/jobs/{job_id}/cancel", tags=["Queue administration"])
    def cancel_global(job_id: str, request: QueueResumeRequest | None = None):
        return cancel_job(job_id, request.reason if request else "")

    @app.post("/v1/queue/resume", tags=["Queue administration"], responses={202: {"description": "Recovery requested; poll /v1/queue"}})
    def resume_queue(request: QueueResumeRequest | None = None):
        """Request global recovery without retrying failed jobs or bypassing resource/cooldown checks."""
        state = store.state()
        if state.get("phase") == "stopped" or time.time() - state.get("heartbeat", 0) >= 15:
            raise HTTPException(503, "GPU scheduler is offline; start video-gpu-scheduler.service before resuming")
        result = recovery.request_resume(request.reason if request else "")
        result.update(failed_jobs_retried=False, recovery=recovery.snapshot())
        return JSONResponse(result, status_code=202 if result["accepted"] else 200)

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
            payload = request.model_dump(exclude={"image_reference", "video_reference", "audio_reference", "priority"})
            payload["mode"] = "omni"
            payload["references"] = [{"kind": kind, "path": resolve(value, kind)}
                                     for kind, items, _ in groups for value in items]
            return enqueue(payload, priority=request.priority)
    else:
        @app.post("/v1/videos/regenerations", status_code=202)
        def regenerate(request: RefinerRequest):
            payload = request.model_dump(exclude={"priority"})
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
            return enqueue(payload, dependency, request.priority)

    @app.get("/v1/videos")
    def list_jobs(limit: int = Query(default=20, ge=1, le=100), after: str | None = None,
                  status: list[JobStatus] | None = Query(default=None)):
        return browse(model, status, limit, after)

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
        find(job_id)
        return cancel_job(job_id)

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("VIDEO_HTTP_PORT", "8001")),
                timeout_keep_alive=300)
