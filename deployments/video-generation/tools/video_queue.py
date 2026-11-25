"""Durable jobs and a fair model-affinity policy, shared by both LAN APIs."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from model_registry import effective_duration, load_registry, select_job

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("VIDEO_QUEUE_DATA", ROOT / "outputs/video-queue"))
OMNI = "fasth3-omni-bf16"
REFINER = "open-h3-2k"
MODELS = (OMNI, REFINER)
HOLD = ROOT / "outputs/h3-2k-http/inference-hold.json"
MAX_BATCH = 3
MAX_WAIT_SECONDS = 1800
PRIORITY_MIN, PRIORITY_MAX = -1000, 1000
JOB_STATES = ("queued", "in_progress", "completed", "failed", "cancelled")


class QueueConflict(ValueError):
    """A requested queue edit no longer applies to the current task state."""


class ServiceUnavailable(RuntimeError):
    """Admissions/dispatch are temporarily disabled for maintenance."""


class QueueChanged(RuntimeError):
    """A task was cancelled between choosing and atomically claiming a cohort."""


def choose_next(jobs, active_model=None, consecutive=0, now=None,
                max_batch=MAX_BATCH, max_wait=MAX_WAIT_SECONDS):
    """FIFO within a model, with affinity until another model's turn is due."""
    ready = sorted(jobs, key=lambda j: (-j.get("priority", 0), -j.get("front_order", 0), j["created"], j["id"]))
    if not ready:
        return None
    # Explicit operator priority precedes model affinity. Fairness still applies
    # within one priority/front group, including the default priority-zero FIFO.
    rank = (ready[0].get("priority", 0), ready[0].get("front_order", 0))
    ready = [j for j in ready if (j.get("priority", 0), j.get("front_order", 0)) == rank]
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
        self.registry, self.models = load_registry()

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
        with self.connection(immediate=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,path TEXT,name TEXT,bytes INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,model TEXT,status TEXT,created REAL,"
                       "updated REAL,payload TEXT,directory TEXT,dependency TEXT,unit TEXT,error TEXT)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            for name in ("priority", "front_order"):
                if name not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            if "started" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN started REAL")
            db.execute("CREATE INDEX IF NOT EXISTS pending_jobs ON jobs(status,created)")
            db.execute("CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS idempotency(model TEXT, key TEXT, digest TEXT, job TEXT, "
                       "PRIMARY KEY(model,key))")
            db.execute("CREATE TABLE IF NOT EXISTS task_metering(job TEXT, channel TEXT, created REAL, "
                       "PRIMARY KEY(job,channel))")
            db.execute("CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "created REAL,event TEXT,detail TEXT)")

    @staticmethod
    def _state_value(db, key, default=None):
        row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @classmethod
    def _bump_revision(cls, db):
        revision = cls._state_value(db, "queue_revision", 0) + 1
        db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", ("queue_revision", json.dumps(revision)))
        return revision

    @staticmethod
    def _event(db, event, **detail):
        db.execute("INSERT INTO events(created,event,detail) VALUES(?,?,?)",
                   (time.time(), event, json.dumps(detail)))

    def maintenance(self, enabled, reason=""):
        with self.connection(immediate=True) as db:
            value = dict(self._state_value(db, "service_control", {}), enabled=enabled,
                         reason=reason, updated_at=time.time())
            value.pop("validation_job", None)
            db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", ("service_control", json.dumps(value)))
            self._bump_revision(db)
            self._event(db, "maintenance_changed", **value)
        return value

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
        with self.connection() as db:
            db.execute("BEGIN")
            revision = self._state_value(db, "queue_revision", 0)
            rows = db.execute("SELECT j.* FROM jobs j LEFT JOIN jobs p ON p.id=j.dependency "
                              "WHERE j.status='queued' AND (j.dependency IS NULL OR p.status='completed')").fetchall()
        return [dict(self.decode(row), _queue_revision=revision) for row in rows]

    def enqueue(self, model, request, dependency=None, priority=0, *, idempotency_key=None):
        if type(priority) is not int or not PRIORITY_MIN <= priority <= PRIORITY_MAX:
            raise ValueError("priority must be an integer from -1000 to 1000")
        now = time.time()
        prefix = {"llm": "lm_task_", "blender_review": "render_"}.get(request.get("task_kind"), "video_gen_")
        job_id = prefix + uuid.uuid4().hex
        folder = self.jobs / job_id
        digest = hashlib.sha256(json.dumps([request, dependency, priority], sort_keys=True).encode()).hexdigest()
        try:
            with self.connection(immediate=True) as db:
                if idempotency_key:
                    previous = db.execute("SELECT digest,job FROM idempotency WHERE model=? AND key=?",
                                          (model, idempotency_key)).fetchone()
                    if previous is not None:
                        if previous["digest"] != digest:
                            raise QueueConflict("Idempotency-Key belongs to a different request")
                        return self.decode(db.execute("SELECT * FROM jobs WHERE id=?", (previous["job"],)).fetchone())
                if self._state_value(db, "service_control", {}).get("enabled"):
                    raise ServiceUnavailable("Service is draining/upgrading; retry after maintenance")
                count = db.execute("SELECT COUNT(*) FROM jobs WHERE model=? AND status IN "
                                   "('queued','in_progress')", (model,)).fetchone()[0]
                limit = self.models.get(model, {}).get("max_pending", 32)
                if count >= limit:
                    raise OverflowError(f"This model's queue is full ({limit} pending jobs)")
                folder.mkdir(mode=0o700)
                (folder / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n")
                db.execute("INSERT INTO jobs(id,model,status,created,updated,payload,directory,dependency,unit,error,priority) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (job_id, model, "queued", now, now, json.dumps(request), str(folder), dependency, None, None, priority))
                if idempotency_key:
                    db.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (model, idempotency_key, digest, job_id))
                self._bump_revision(db)
        except BaseException:
            (folder / "request.json").unlink(missing_ok=True)
            if folder.exists():
                folder.rmdir()
            raise
        self.event("enqueued", job=job_id, model=model, dependency=dependency)
        return self.get(job_id)

    def claim(self, ids, unit, expected_revision=None):
        with self.connection(immediate=True) as db:
            if self._state_value(db, "service_control", {}).get("enabled"):
                raise QueueChanged("Maintenance started before dispatch")
            if expected_revision is not None and expected_revision != self._state_value(db, "queue_revision", 0):
                raise QueueChanged("Queue order changed before dispatch")
            for job_id in ids:
                now = time.time()
                changed = db.execute("UPDATE jobs SET status='in_progress',unit=?,updated=?,started=? "
                                     "WHERE id=? AND status='queued'", (unit, now, now, job_id)).rowcount
                if changed != 1:
                    raise QueueChanged("Queue changed before dispatch")
            self._bump_revision(db)

    def change(self, job_id, status, error=None, only_running=False):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status=?,error=?,updated=? WHERE id=?" +
                       (" AND status='in_progress'" if only_running else ""),
                       (status, error, time.time(), job_id))
            self._bump_revision(db)

    def set_priority(self, job_id, priority=None, *, promote=False, reason=""):
        if not promote and (type(priority) is not int or not PRIORITY_MIN <= priority <= PRIORITY_MAX):
            raise ValueError("priority must be an integer from -1000 to 1000")
        with self.connection(immediate=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("Unknown task")
            if row["status"] != "queued":
                raise QueueConflict("Only queued tasks can be promoted or reprioritized; running tasks are not preempted")
            front = self._bump_revision(db) if promote else 0
            db.execute("UPDATE jobs SET priority=?,front_order=?,updated=? WHERE id=?",
                       (PRIORITY_MAX if promote else priority, front, time.time(), job_id))
            if not promote:
                self._bump_revision(db)
            self._event(db, "task_promoted" if promote else "task_priority_changed", job=job_id,
                        priority=PRIORITY_MAX if promote else priority, front_order=front, reason=reason)
        return self.get(job_id)

    def cancel(self, job_id, reason=""):
        with self.connection(immediate=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("Unknown task")
            changed = row["status"] in {"queued", "in_progress"}
            if changed:
                db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?", (time.time(), job_id))
                self._bump_revision(db)
                self._event(db, "cancel_requested", job=job_id, model=row["model"], reason=reason)
        return self.get(job_id), changed and row["status"] == "in_progress"

    def list_jobs(self, *, model=None, statuses=None, limit=20, after=None):
        clauses, args = [], []
        if model:
            clauses.append("model=?")
            args.append(model)
        if statuses:
            clauses.append("status IN (" + ",".join("?" for _ in statuses) + ")")
            args.extend(statuses)
        with self.connection() as db:
            if after:
                cursor = db.execute("SELECT created,id FROM jobs WHERE id=?", (after,)).fetchone()
                if cursor is None:
                    raise ValueError("Unknown pagination cursor")
                clauses.append("(created<? OR (created=? AND id<?))")
                args.extend((cursor["created"], cursor["created"], cursor["id"]))
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = db.execute("SELECT * FROM jobs" + where + " ORDER BY created DESC,id DESC LIMIT ?",
                              [*args, limit + 1]).fetchall()
        more = len(rows) > limit
        return [self.decode(row) for row in rows[:limit]], more

    def add_file(self, file_id, path, name, size):
        with self.connection() as db:
            db.execute("INSERT INTO files VALUES(?,?,?,?)", (file_id, str(path), name, size))

    def uploaded_file(self, file_id):
        with self.connection() as db:
            file = db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        if file is None:
            raise FileNotFoundError("Unknown uploaded file")
        path = Path(file["path"]).resolve()
        if not path.is_relative_to(self.uploads.resolve()) or not path.is_file():
            raise FileNotFoundError("Uploaded file is unavailable")
        return path

    def preferences(self):
        return self.state().get("residency_preferences", {})

    def set_preferences(self, values):
        with self.connection(immediate=True) as db:
            db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", ("residency_preferences", json.dumps(values)))
            self._bump_revision(db)
            self._event(db, "residency_preferences_changed", **values)
        return values

    def claim_metering(self, task_id, channel):
        with self.connection(immediate=True) as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "completed":
                return False
            changed = db.execute("INSERT OR IGNORE INTO task_metering VALUES(?,?,?)",
                                 (task_id, channel, time.time())).rowcount
            return changed == 1

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
        control = state.get("service_control", {})
        ready = self.ready()
        preferences = state.get("residency_preferences", {})
        active = state.get("active_model")
        now = time.time()
        ready_at = state.get("model_ready_at")
        duration = effective_duration(self.registry, preferences, active)
        protection = max(0, int(ready_at + duration - now + 0.999)) if ready_at is not None else None
        order = []
        remaining = list(ready)
        predicted_model, predicted_ready = active, ready_at
        while remaining:
            seconds = effective_duration(self.registry, preferences, predicted_model)
            item = select_job(remaining, predicted_model, predicted_ready, seconds, now)
            order.append(item)
            remaining.remove(item)
            if item["model"] != predicted_model:
                predicted_model, predicted_ready = item["model"], now
        pending = self.pending()
        ordered_ids = {job["id"] for job in order}
        blocked = [job for job in pending if job["status"] == "queued" and job["id"] not in ordered_ids]
        clean = lambda j: {key: j[key] for key in ("id", "model", "status", "created", "dependency", "priority", "front_order")}
        return {"scheduler": state, "paused": recovery["paused"] or bool(control.get("enabled")),
                "maintenance": control, "recovery": recovery,
                "policy": {"residency_seconds": duration, "residency_preferences": preferences,
                           "model_ready_at": ready_at, "protection_remaining_seconds": protection,
                           "priority_range": [PRIORITY_MIN, PRIORITY_MAX],
                           "note": "Model residency precedes cross-model priority. Positions estimate dispatch order; running work is not preempted."},
                "running": [clean(j) for j in pending if j["status"] == "in_progress"],
                "queued": [dict(clean(j), position=i + 1) for i, j in enumerate(order)],
                "waiting_for_source": [clean(j) for j in blocked]}

    def public(self, job):
        request = job["request"]
        kind = request.get("task_kind", "video")
        if kind != "video":
            folder = Path(job["directory"])
            started = job.get("started")
            now = time.time() if job["status"] in {"queued", "in_progress"} else job["updated"]
            result = {"id": job["id"], "object": "task", "kind": kind, "model": job["model"],
                      "status": job["status"], "created_at": job["created"], "started_at": started,
                      "queue_seconds": max(0, (started or now) - job["created"]),
                      "run_seconds": max(0, now - started) if started else 0,
                      "priority": job["priority"], "front_order": job["front_order"]}
            if job["error"]:
                result["error"] = {"code": "task_failed", "message": job["error"]}
            for name, field in (("progress.json", "progress"), ("result-meta.json", "result")):
                try:
                    result[field] = json.loads((folder / name).read_text())
                except (OSError, ValueError):
                    pass
            return result
        result = {"id": job["id"], "object": "video", "model": job["model"], "status": job["status"],
                  "created_at": int(job["created"]), "size": request["size"],
                  "priority": job.get("priority", 0), "front_order": job.get("front_order", 0),
                  "seconds": str(request.get("seconds", "")), "progress": 0, "stage": "等待 GPU 调度"}
        folder = Path(job["directory"])
        source = request.get("input_video")
        if isinstance(source, str):
            with self.connection() as db:
                uploaded = db.execute("SELECT name FROM files WHERE path=?", (source,)).fetchone()
            result["input_filename"] = uploaded[0] if uploaded else Path(source).name
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
                for key in ("seconds", "size"):
                    if receipt.get(key) is not None:
                        result[key] = str(receipt[key])
                if isinstance(receipt.get("duration"), (int, float)):
                    # Native Bifrost video rates consume integer output seconds.
                    # The unrounded output duration remains in the receipt.
                    result["seconds"] = str(max(1, round(receipt["duration"])))
                if receipt.get("width") and receipt.get("height"):
                    result["size"] = f"{receipt['width']}x{receipt['height']}"
                result["completed_at"] = int(job["updated"])
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
                    db.execute("INSERT OR IGNORE INTO jobs(id,model,status,created,updated,payload,directory,dependency,unit,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (row["id"], REFINER, status, row["created"], row["updated"], row["request"],
                                str(legacy.parent / "jobs" / row["id"]), None, None, row["error"]))
        finally:
            source.close()
