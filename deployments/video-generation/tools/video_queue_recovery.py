"""Durable OOM cooldown and operator recovery; never retries a failed job."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import time
import uuid

GIB = 2**30
KEY = "memory_recovery"
ACTIVE = {"cooldown", "waiting_for_resources", "manual_intervention"}


@dataclass(frozen=True)
class RecoveryPolicy:
    cooldown_seconds: int = 60
    consecutive_oom_threshold: int = 2
    min_host_available_gib: int = 28
    min_gpu_free_fraction: float = 0.95
    probe_interval_seconds: int = 5


def probe_resources(policy):
    """Read resource availability without importing CUDA or allocating GPU memory."""
    result = {"checked_at": time.time(), "ready": False, "blockers": []}
    try:
        values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available = int(values["MemAvailable"].split()[0]) * 1024
        result["host_available_gib"] = round(available / GIB, 3)
        if available < policy.min_host_available_gib * GIB:
            result["blockers"].append("host_memory_below_reserve")
        gpu = subprocess.run(["nvidia-smi", "--id=0", "--query-gpu=memory.total,memory.free",
                              "--format=csv,noheader,nounits"], check=True, capture_output=True,
                             text=True, timeout=8)
        total, free = [float(value.strip()) for value in gpu.stdout.strip().split(",")]
        if total <= 0:
            raise ValueError("Invalid GPU memory total")
        result.update(gpu_total_mib=total, gpu_free_mib=free)
        if free / total < policy.min_gpu_free_fraction:
            result["blockers"].append("gpu_memory_not_released")
        apps = subprocess.run(["nvidia-smi", "--id=0", "--query-compute-apps=pid",
                               "--format=csv,noheader,nounits"], check=True, capture_output=True,
                              text=True, timeout=8)
        pids = [int(line.strip()) for line in apps.stdout.splitlines() if line.strip()]
        result["gpu_compute_processes"] = pids
        if pids:
            result["blockers"].append("gpu_compute_process_still_running")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result["blockers"].append("resource_probe_failed:" + type(error).__name__)
    result["ready"] = not result["blockers"]
    return result


class QueueRecovery:
    def __init__(self, store, policy=None):
        self.store = store
        self.policy = policy or RecoveryPolicy()
        self.hold = store.hold

    @staticmethod
    def _read(db):
        row = db.execute("SELECT value FROM state WHERE key=?", (KEY,)).fetchone()
        return json.loads(row[0]) if row else {"status": "ready", "consecutive_ooms": 0}

    @staticmethod
    def _save(db, value, event=None):
        db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (KEY, json.dumps(value)))
        if event:
            db.execute("INSERT INTO events(created,event,detail) VALUES(?,?,?)",
                       (time.time(), event, json.dumps({"incident_id": value.get("incident_id"),
                                                        "status": value["status"]})))

    def _legacy(self):
        try:
            value = json.loads(self.hold.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            value = {"reason": "Unreadable legacy memory hold; operator inspection required"}
        if not isinstance(value, dict):
            value = {"reason": "Invalid legacy memory hold; operator inspection required"}
        return {"status": "manual_intervention", "incident_id": "legacy-memory-hold",
                "consecutive_ooms": 0, "failed_jobs": value.get("jobs", [value.get("job")]),
                "reason": str(value.get("reason", "Legacy memory hold"))[-1500:],
                "cleanup_complete": False, "resume_requested": False, "legacy_hold": True,
                "cooldown_until": time.time() + self.policy.cooldown_seconds,
                "worker_units": [], "resources": None}

    def sync_legacy(self):
        """An old hold has unknown history, so import it as manual, never clear it silently."""
        if not self.hold.exists():
            return
        with self.store.connection(immediate=True) as db:
            current = self._read(db)
            if current.get("legacy_hold") and current["status"] in ACTIVE:
                return
            value = self._legacy()
            if value is not None:
                self._save(db, value, "memory_legacy_hold_imported")

    def snapshot(self):
        with self.store.connection() as db:
            value = self._read(db)
        if self.hold.exists() and not value.get("legacy_hold"):
            value = self._legacy() or value
        value["paused"] = value["status"] in ACTIVE
        value["manual_resume_required"] = value["status"] == "manual_intervention" and not value.get("resume_requested")
        value["cooldown_remaining_seconds"] = (max(0, round(value.get("cooldown_until", 0) - time.time(), 1))
                                                if value["paused"] else 0)
        value["policy"] = asdict(self.policy)
        return value

    def record_failure(self, jobs, reason, worker_units):
        with self.store.connection(immediate=True) as db:
            previous = self._read(db)
            count = previous.get("consecutive_ooms", 0) + 1
            value = {"status": "manual_intervention" if count >= self.policy.consecutive_oom_threshold else "cooldown",
                     "incident_id": uuid.uuid4().hex, "consecutive_ooms": count,
                     "failed_at": time.time(), "failed_jobs": jobs, "reason": reason[-1500:],
                     "cooldown_until": time.time() + self.policy.cooldown_seconds,
                     "cleanup_complete": False, "resume_requested": False,
                     "worker_units": list(dict.fromkeys(unit for unit in worker_units if unit)),
                     "resources": None}
            self._save(db, value, "memory_failure_recorded")
        return value

    def record_success(self):
        with self.store.connection(immediate=True) as db:
            value = self._read(db)
            if value["status"] == "ready" and value.get("consecutive_ooms"):
                value["consecutive_ooms"] = 0
                self._save(db, value, "memory_failure_streak_reset_after_success")

    def request_resume(self, reason=""):
        self.sync_legacy()
        with self.store.connection(immediate=True) as db:
            value = self._read(db)
            if value["status"] not in ACTIVE:
                return {"accepted": False, "status": "already_running", "recovery_request_id": None}
            if not value.get("resume_requested"):
                value.update(resume_requested=True, recovery_request_id=uuid.uuid4().hex,
                             resume_reason=reason, resume_requested_at=time.time())
                self._save(db, value, "memory_resume_requested")
            return {"accepted": True, "status": "recovery_requested",
                    "recovery_request_id": value["recovery_request_id"]}

    def cleanup_result(self, incident_id, error=None):
        with self.store.connection(immediate=True) as db:
            value = self._read(db)
            if value.get("incident_id") != incident_id or value["status"] not in ACTIVE:
                return
            value["cleanup_error"] = error
            if error is None and not value.get("cleanup_complete"):
                value.update(cleanup_complete=True, cleaned_at=time.time(),
                             cooldown_until=max(value.get("cooldown_until", 0),
                                                time.time() + self.policy.cooldown_seconds))
            self._save(db, value)

    def observe(self, incident_id, resources):
        with self.store.connection(immediate=True) as db:
            value = self._read(db)
            if value.get("incident_id") != incident_id or value["status"] not in ACTIVE:
                return False
            value["resources"] = resources
            manual = value["status"] == "manual_intervention"
            permitted = not manual or value.get("resume_requested")
            if (permitted and value.get("cleanup_complete") and resources.get("ready")
                    and time.time() >= value.get("cooldown_until", 0)):
                if value.get("legacy_hold") and self.hold.exists():
                    destination = self.hold.with_name("inference-hold.resolved-" + uuid.uuid4().hex + ".json")
                    self.hold.replace(destination)
                    value["archived_hold"] = str(destination)
                if value.get("resume_requested"):
                    value["consecutive_ooms"] = 0
                value.update(status="ready", resumed_at=time.time(), legacy_hold=False)
                self._save(db, value, "memory_queue_resumed")
                return True
            if not manual:
                value["status"] = ("cooldown" if time.time() < value.get("cooldown_until", 0)
                                   else "waiting_for_resources")
            self._save(db, value)
            return False
