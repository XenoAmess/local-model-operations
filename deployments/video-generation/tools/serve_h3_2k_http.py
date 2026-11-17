#!/usr/bin/env python3
"""LAN HTTP API for sequential, fully local H3-Base and IC 2K generation."""

import asyncio
from contextlib import asynccontextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from typing import Literal
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("H3_HTTP_DATA", str(ROOT / "outputs/h3-2k-http")))
JOBS = DATA / "jobs"
UPLOADS = DATA / "uploads"
DB = DATA / "jobs.sqlite3"
REFINER_ONLY = os.environ.get("H3_HTTP_MODE", "pipeline") == "refiner"
MODEL = os.environ.get("H3_HTTP_MODEL", "open-h3-2k" if REFINER_ONLY else "minimax-h3-2k")
GPU_LOCK = ROOT / "outputs/h3-2k-gpu.lock"
HOLD = ROOT / "outputs/h3-2k-http/inference-hold.json"
UNIT_PREFIX = "llmlab-h3-2k-refiner-job" if REFINER_ONLY else "llmlab-h3-2k-job"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
              ".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}


class VideoRequest(BaseModel):
    model: str = MODEL
    task: Literal["ref2va"] = "ref2va"
    prompt: str = Field(min_length=1, max_length=50000)
    seconds: int = Field(default=5, ge=5, le=15)
    size: Literal["2560x1440", "1440x2560"] = "2560x1440"
    seed: int = Field(default=1234, ge=0, lt=2**62)
    num_inference_steps: Literal[50] = 50
    sampler: Literal["up3", "up4", "hf8"] = "up3"
    image_reference: list[dict] = Field(default_factory=list)
    video_reference: list[dict] = Field(default_factory=list)
    audio_reference: list[dict] = Field(default_factory=list)


class RegenerateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    model: str = MODEL
    input_video: str | dict
    prompt: str = Field(default="", max_length=50000)
    size: Literal["2560x1440", "1440x2560"] = "2560x1440"
    seed: int = Field(default=1234, ge=0, lt=2**62)
    sampler: Literal["up3", "up4", "hf8"] = "up3"


def connection():
    handle = sqlite3.connect(DB, timeout=10)
    handle.row_factory = sqlite3.Row
    return handle


def initialize():
    JOBS.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, path TEXT, filename TEXT, size INTEGER)")
        db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, created REAL, updated REAL, "
                   "request TEXT, unit TEXT, error TEXT)")
        db.execute("UPDATE jobs SET status='queued', unit=NULL WHERE status='in_progress'")


def change(job_id, **values):
    values["updated"] = time.time()
    with connection() as db:
        db.execute("UPDATE jobs SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=?",
                   [*values.values(), job_id])


def get_job(job_id):
    if not re.fullmatch(r"video_gen_[0-9a-f]{32}", job_id):
        raise HTTPException(404, "Unknown job")
    with connection() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown job")
    request = json.loads(row["request"])
    result = {"id": job_id, "object": "video", "model": MODEL, "status": row["status"],
              "created_at": int(row["created"]), "size": request["size"], "seconds": str(request.get("seconds", "")),
              "progress": 100 if row["status"] == "completed" else 0, "stage": "等待处理"}
    progress = JOBS / job_id / "progress.json"
    try:
        state = json.loads(progress.read_text())
        result.update({key: state[key] for key in ("progress", "stage")})
    except (OSError, ValueError, KeyError):
        pass
    if row["error"]:
        result["error"] = {"code": "inference_failed", "message": row["error"]}
    if row["status"] == "completed":
        result["url"] = f"/v1/videos/{job_id}/content"
        receipt = JOBS / job_id / "result.json"
        if receipt.exists():
            result["result"] = json.loads(receipt.read_text())
    return result


def resolve_reference(value, kind):
    if isinstance(value, dict):
        source = value.get("file_id") or value.get(kind + "_url") or value.get("path")
    else:
        source = value
    if not isinstance(source, str) or not source:
        raise HTTPException(422, f"A {kind} reference requires file_id or a permitted local path")
    if source.startswith("file_"):
        with connection() as db:
            record = db.execute("SELECT path FROM files WHERE id=?", (source,)).fetchone()
        if record is None:
            raise HTTPException(404, "Unknown uploaded file")
        source = record["path"]
    path = Path(source).resolve()
    roots = [UPLOADS.resolve(), (ROOT / "omni-web/uploads").resolve()]
    if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
        raise HTTPException(422, "Upload media through /v1/files or the webpage before referencing it")
    formats = {"image": {".png", ".jpg", ".jpeg", ".webp", ".bmp"},
               "video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
               "audio": {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}}
    if path.suffix.lower() not in formats[kind]:
        raise HTTPException(415, f"Uploaded file is not a supported {kind} format")
    return str(path)


def enqueue(payload):
    if payload["model"] != MODEL:
        raise HTTPException(400, f"This server provides {MODEL}")
    with connection() as db:
        count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','in_progress')").fetchone()[0]
        if count >= 8:
            raise HTTPException(429, "The video queue is full; retry after an existing job finishes")
        job_id = "video_gen_" + uuid.uuid4().hex
        folder = JOBS / job_id
        folder.mkdir()
        (folder / "request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        now = time.time()
        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
                   (job_id, "queued", now, now, json.dumps(payload), None, None))
    return get_job(job_id)


def acquire_gpu_lease():
    """Serialize both HTTP queues before either one launches a GPU process."""
    GPU_LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = GPU_LOCK.open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


async def gpu_busy():
    command = ["systemctl", "--user", "list-units", "--state=running", "--no-legend",
               "llmlab-h3-2k-*.service", "llmlab-fasth3-omni*.service", "llmlab-coder-lan.service"]
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.DEVNULL)
    output, _ = await process.communicate()
    return bool(output.strip())


async def queue_worker():
    while True:
        with connection() as db:
            row = db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if row is None or HOLD.exists() or await gpu_busy():
            await asyncio.sleep(2)
            continue
        lease = acquire_gpu_lease()
        if lease is None:
            await asyncio.sleep(2)
            continue
        try:
            # The first check can race with the other HTTP queue. Hold the
            # process-wide file lease through launch, inference and teardown.
            if await gpu_busy() or get_job(row["id"])["status"] != "queued":
                continue
            await execute_job(row["id"])
        finally:
            lease.close()


async def execute_job(job_id):
    unit = f"{UNIT_PREFIX}-{job_id[-10:]}-{int(time.time())}"
    change(job_id, status="in_progress", unit=unit)
    command = ["/usr/bin/python3", str(ROOT / "llm-lab/scripts/run_isolated.py"),
               "--unit", unit, "--memory-gib", "80", "--wait", "--",
               str(ROOT / "start-h3-2k-worker.sh"), str(ROOT / "tools/h3_2k_worker.py"),
               "--job-dir", str(JOBS / job_id)]
    try:
        with (JOBS / job_id / "launcher.log").open("ab") as log:
            process = await asyncio.create_subprocess_exec(*command, stdout=log, stderr=log)
            code = await process.wait()
        if get_job(job_id)["status"] == "cancelled":
            return
        if code == 0 and (JOBS / job_id / "result.json").is_file():
            change(job_id, status="completed", error=None)
        else:
            error_path = JOBS / job_id / "error.json"
            error = json.loads(error_path.read_text())["message"] if error_path.exists() else f"Inference process exited {code}; see job logs"
            change(job_id, status="failed", error=error)
            result = subprocess.run(["systemctl", "--user", "show", unit, "-p", "Result", "--value"],
                                    capture_output=True, text=True).stdout.strip()
            if result == "oom-kill" or "out of memory" in error.lower():
                HOLD.parent.mkdir(parents=True, exist_ok=True)
                HOLD.write_text(json.dumps({"job": job_id, "unit": unit,
                    "reason": "Memory failure requires inspection before another inference", "time": time.time()}))
    except asyncio.CancelledError:
        subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=30)
        raise
    except Exception as error:
        change(job_id, status="failed", error=str(error))


@asynccontextmanager
async def lifespan(app):
    initialize()
    worker = asyncio.create_task(queue_worker())
    yield
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Local Open-H3 2K Refiner" if REFINER_ONLY else "Local MiniMax H3 2K",
              version="1.1", lifespan=lifespan,
              description=("Existing video and optional text to local Open-H3 IC 2K; skips draft generation."
                           if REFINER_ONLY else "Full BF16 H3 reference generation followed by local Open-H3 IC regeneration; one GPU, sequential stages."))


@app.middleware("http")
async def limit_body(request: Request, call_next):
    limit = 513 * 1024**2 if request.url.path == "/v1/files" else 64 * 1024**2
    if int(request.headers.get("content-length", "0")) > limit:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Request body is too large; upload files separately"}, status_code=413)
    return await call_next(request)


@app.get("/health")
def health():
    with connection() as db:
        pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','in_progress')").fetchone()[0]
    return {"status": "ok", "model": MODEL, "queue": pending, "cloud_used": False,
            "mode": "refiner" if REFINER_ONLY else "pipeline", "queue_paused": HOLD.exists(),
            "loading": "Models load for each task and release their GPU memory between stages"}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "local",
            "base": "MiniMaxAI/MiniMax-H3 full BF16 Ref2VA", "refiner": "Open-H3-Regenerate-2K-IC",
            "draft_generation": not REFINER_ONLY,
            "sizes": ["2560x1440", "1440x2560"], "fps": 24, "max_seconds": 15}]}


@app.post("/v1/files")
async def upload(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in EXTENSIONS:
        raise HTTPException(415, "Unsupported media format")
    file_id = "file_" + uuid.uuid4().hex
    path = UPLOADS / (file_id + extension)
    size = 0
    try:
        with path.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 512 * 1024**2:
                    raise HTTPException(413, "Uploaded file exceeds 512 MiB")
                stream.write(chunk)
        with connection() as db:
            db.execute("INSERT INTO files VALUES (?,?,?,?)", (file_id, str(path), Path(file.filename).name, size))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"id": file_id, "object": "file", "bytes": size, "filename": Path(file.filename).name}


@app.post("/v1/videos", status_code=202, include_in_schema=not REFINER_ONLY)
def create_video(request: VideoRequest):
    if REFINER_ONLY:
        raise HTTPException(404, "This service only regenerates existing videos; use /v1/videos/regenerations")
    groups = [("image", request.image_reference, 9), ("video", request.video_reference, 3),
              ("audio", request.audio_reference, 3)]
    if not request.prompt.strip() or not request.image_reference and not request.video_reference:
        raise HTTPException(422, "Provide a prompt and at least one reference image or video")
    if sum(len(items) for _, items, _ in groups) > 12 or any(len(items) > cap for _, items, cap in groups):
        raise HTTPException(422, "Reference limits: 9 images, 3 videos, 3 audio; 12 total")
    payload = request.model_dump(exclude={"image_reference", "video_reference", "audio_reference"})
    payload["mode"] = "generate"
    payload["references"] = [{"kind": kind, "path": resolve_reference(value, kind)}
                             for kind, items, _ in groups for value in items]
    return enqueue(payload)


@app.post("/v1/videos/regenerations", status_code=202)
def regenerate(request: RegenerateRequest):
    payload = request.model_dump()
    payload.update(mode="regenerate", input_video=resolve_reference(request.input_video, "video"))
    return enqueue(payload)


@app.get("/v1/videos/{job_id}")
def video_status(job_id: str):
    return get_job(job_id)


@app.get("/v1/videos/{job_id}/content")
def content(job_id: str):
    job = get_job(job_id)
    if job["status"] != "completed":
        raise HTTPException(409, "The video is not completed")
    return FileResponse(JOBS / job_id / "result.mp4", media_type="video/mp4", filename=job_id + "-2k.mp4")


@app.get("/v1/videos/{job_id}/logs", response_class=PlainTextResponse)
def logs(job_id: str):
    get_job(job_id)
    path = JOBS / job_id / "worker.log"
    if not path.exists():
        return "Job has not started"
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 16000))
        return stream.read().decode(errors="replace")


@app.delete("/v1/videos/{job_id}")
async def cancel(job_id: str):
    get_job(job_id)
    with connection() as db:
        row = db.execute("SELECT unit,status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row["status"] in {"queued", "in_progress"}:
        change(job_id, status="cancelled")
        if row["unit"]:
            process = await asyncio.create_subprocess_exec("systemctl", "--user", "stop", row["unit"])
            await process.wait()
    return get_job(job_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("H3_HTTP_PORT", "8001")), timeout_keep_alive=300)
