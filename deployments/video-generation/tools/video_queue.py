"""Durable jobs and a fair model-affinity policy, shared by both LAN APIs."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("VIDEO_QUEUE_DATA", ROOT / "outputs/video-queue"))
OMNI = "fasth3-omni-bf16"
REFINER = "open-h3-2k"
MODELS = (OMNI, REFINER)
HOLD = ROOT / "outputs/h3-2k-http/inference-hold.json"
MAX_BATCH = 3
MAX_WAIT_SECONDS = 1800


class QueueChanged(RuntimeError):
    """A task was cancelled between choosing and atomically claiming a cohort."""


def choose_next(jobs, active_model=None, consecutive=0, now=None,
                max_batch=MAX_BATCH, max_wait=MAX_WAIT_SECONDS):
    """FIFO within a model, with affinity until another model's turn is due."""
    ready = sorted(jobs, key=lambda j: (j["created"], j["id"]))
    if not ready:
        return None
    same = [j for j in ready if j["model"] == active_model]
    other = [j for j in ready if j["model"] != active_model]
    now = time.time() if now is None else now
    if same and other and (consecutive >= max_batch or now - other[0]["created"] >= max_wait):
        return other[0]
    return same[0] if same else ready[0]


def preview(jobs, active_model=None, consecutive=0, now=None):
    remaining, ordered = list(jobs), []
    while remaining:
        item = choose_next(remaining, active_model, consecutive, now)
        remaining.remove(item)
        consecutive = consecutive + 1 if item["model"] == active_model else 1
        active_model = item["model"]
        ordered.append(item)
    return ordered


class QueueStore:
    def __init__(self, directory=DATA):
        self.directory = Path(directory)
        self.hold = HOLD if self.directory == DATA else self.directory / "inference-hold.json"
        self.jobs = self.directory / "jobs"
        self.uploads = self.directory / "uploads"
        self.db = self.directory / "queue.sqlite3"

    @contextmanager
    def connection(self, immediate=False):
        db = sqlite3.connect(self.db, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            if immediate:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.uploads.mkdir(exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,path TEXT,name TEXT,bytes INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,model TEXT,status TEXT,created REAL,"
                       "updated REAL,payload TEXT,directory TEXT,dependency TEXT,unit TEXT,error TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS pending_jobs ON jobs(status,created)")
            db.execute("CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "created REAL,event TEXT,detail TEXT)")

    def event(self, event, **detail):
        with self.connection() as db:
            db.execute("INSERT INTO events(created,event,detail) VALUES(?,?,?)",
                       (time.time(), event, json.dumps(detail)))

    def state(self):
        with self.connection() as db:
            rows = db.execute("SELECT key,value FROM state").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def set_state(self, **values):
        values["heartbeat"] = time.time()
        with self.connection() as db:
            db.executemany("INSERT OR REPLACE INTO state VALUES(?,?)",
                           [(key, json.dumps(value)) for key, value in values.items()])

    @staticmethod
    def decode(row):
        if row is None:
            return None
        value = dict(row)
        value["request"] = json.loads(value.pop("payload"))
        return value

    def get(self, job_id):
        with self.connection() as db:
            return self.decode(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def pending(self):
        with self.connection() as db:
            return [self.decode(row) for row in db.execute(
                "SELECT * FROM jobs WHERE status IN ('queued','in_progress') ORDER BY created,id")]

    def ready(self):
        jobs = self.pending()
        result = []
        for job in jobs:
            parent = self.get(job["dependency"]) if job["dependency"] else None
            if job["status"] == "queued" and (not job["dependency"] or parent and parent["status"] == "completed"):
                result.append(job)
        return result

    def enqueue(self, model, request, dependency=None):
        now = time.time()
        job_id = "video_gen_" + uuid.uuid4().hex
        folder = self.jobs / job_id
        folder.mkdir()
        try:
            with self.connection(immediate=True) as db:
                count = db.execute("SELECT COUNT(*) FROM jobs WHERE model=? AND status IN "
                                   "('queued','in_progress')", (model,)).fetchone()[0]
                if count >= 32:
                    raise OverflowError("This model's queue is full (32 pending jobs)")
                (folder / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n")
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (job_id, model, "queued", now, now, json.dumps(request), str(folder), dependency, None, None))
        except BaseException:
            (folder / "request.json").unlink(missing_ok=True)
            folder.rmdir()
            raise
        self.event("enqueued", job=job_id, model=model, dependency=dependency)
        return self.get(job_id)

    def claim(self, ids, unit):
        with self.connection(immediate=True) as db:
            for job_id in ids:
                changed = db.execute("UPDATE jobs SET status='in_progress',unit=?,updated=? "
                                     "WHERE id=? AND status='queued'", (unit, time.time(), job_id)).rowcount
                if changed != 1:
                    raise QueueChanged("Queue changed before dispatch")

    def change(self, job_id, status, error=None, only_running=False):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status=?,error=?,updated=? WHERE id=?" +
                       (" AND status='in_progress'" if only_running else ""),
                       (status, error, time.time(), job_id))

    def add_file(self, file_id, path, name, size):
        with self.connection() as db:
            db.execute("INSERT INTO files VALUES(?,?,?,?)", (file_id, str(path), name, size))

    def resolve_media(self, value, kind):
        if isinstance(value, dict):
            value = value.get("file_id") or value.get(kind + "_url") or value.get("path")
        if not isinstance(value, str) or not value:
            raise ValueError("A reference needs file_id or a permitted server path")
        if value.startswith("file_"):
            with self.connection() as db:
                row = db.execute("SELECT path FROM files WHERE id=?", (value,)).fetchone()
            if row is None:
                raise FileNotFoundError("Unknown uploaded file")
            value = row[0]
        path = Path(value).resolve()
        roots = [self.uploads.resolve(), (ROOT / "omni-web/uploads").resolve(),
                 (ROOT / "omni-web/cache").resolve(), (ROOT / "outputs/h3-2k-refiner-http/uploads").resolve()]
        if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
            raise ValueError("Upload files using POST /v1/files before referencing them")
        formats = {"image": {".png", ".jpg", ".jpeg", ".webp", ".bmp"},
                   "video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
                   "audio": {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}}
        if path.suffix.lower() not in formats[kind]:
            raise ValueError(f"Not a supported {kind} file")
        return str(path)

    def fail_dependencies(self):
        for job in self.pending():
            if job["status"] != "queued" or not job["dependency"]:
                continue
            parent = self.get(job["dependency"])
            if parent is None or parent["status"] in {"failed", "cancelled"}:
                self.change(job["id"], "failed", "The source video task failed or was cancelled")

    def snapshot(self):
        from video_queue_recovery import QueueRecovery
        recovery = QueueRecovery(self).snapshot()
        state = self.state()
        ready = self.ready()
        order = preview(ready, state.get("active_model"), state.get("consecutive", 0))
        pending = self.pending()
        ordered_ids = {job["id"] for job in order}
        blocked = [job for job in pending if job["status"] == "queued" and job["id"] not in ordered_ids]
        clean = lambda j: {key: j[key] for key in ("id", "model", "status", "created", "dependency")}
        return {"scheduler": state, "paused": recovery["paused"], "recovery": recovery,
                "policy": {"max_consecutive_jobs_with_competition": MAX_BATCH,
                           "max_other_model_wait_seconds": MAX_WAIT_SECONDS,
                           "note": "Switches at task or dispatched-cohort boundaries; running inference is not preempted"},
                "running": [clean(j) for j in pending if j["status"] == "in_progress"],
                "queued": [dict(clean(j), position=i + 1) for i, j in enumerate(order)],
                "waiting_for_source": [clean(j) for j in blocked]}

    def public(self, job):
        request = job["request"]
        result = {"id": job["id"], "object": "video", "model": job["model"], "status": job["status"],
                  "created_at": int(job["created"]), "size": request["size"],
                  "seconds": str(request.get("seconds", "")), "progress": 0, "stage": "等待 GPU 调度"}
        folder = Path(job["directory"])
        try:
            result.update(json.loads((folder / "progress.json").read_text()))
        except (OSError, ValueError):
            pass
        if job["error"]:
            result["error"] = {"code": "inference_failed", "message": job["error"]}
        if job["status"] == "completed":
            result.update(progress=100, stage="生成完成", url=f"/v1/videos/{job['id']}/content")
            try:
                receipt = json.loads((folder / "result.json").read_text())
                result["result"] = receipt
                for key in ("inference_time_s", "stage_durations"):
                    if key in receipt:
                        result[key] = receipt[key]
            except (OSError, ValueError):
                pass
        if job["dependency"]:
            result["source_job_id"] = job["dependency"]
        if job["status"] == "queued":
            parent = self.get(job["dependency"]) if job["dependency"] else None
            result.update(progress=0, stage="等待草稿任务完成" if parent and parent["status"] != "completed" else "等待 GPU 调度")
        elif job["status"] == "cancelled":
            result.update(progress=0, stage="任务已取消")
        return result

    def migrate_refiner(self):
        """Import old IDs and paths once; keep media and existing checkpoints in place."""
        legacy = ROOT / "outputs/h3-2k-refiner-http/jobs.sqlite3"
        if not legacy.exists():
            return
        source = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            with self.connection(immediate=True) as db:
                for row in source.execute("SELECT * FROM files"):
                    db.execute("INSERT OR IGNORE INTO files VALUES(?,?,?,?)",
                               (row["id"], row["path"], row["filename"], row["size"]))
                for row in source.execute("SELECT * FROM jobs"):
                    status = "queued" if row["status"] == "in_progress" else row["status"]
                    db.execute("INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (row["id"], REFINER, status, row["created"], row["updated"], row["request"],
                                str(legacy.parent / "jobs" / row["id"]), None, None, row["error"]))
        finally:
            source.close()
