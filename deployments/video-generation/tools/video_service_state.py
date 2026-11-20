"""CPU-only availability, kept independent of model loading and HTTP restarts."""

import json
from pathlib import Path
import sqlite3
import time

API_VERSION = "3.0"


def status_from_database(directory):
    """Read without migrations, so this monitor also works during an upgrade."""
    directory = Path(directory)
    try:
        with sqlite3.connect(f"file:{directory / 'queue.sqlite3'}?mode=ro", uri=True, timeout=2) as db:
            state = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM state")}
            counts = dict(db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status"))
            running = [r[0] for r in db.execute("SELECT id FROM jobs WHERE status='in_progress'")]
    except (OSError, ValueError, sqlite3.Error) as error:
        return {"status": "unavailable", "ready": False, "accepting_jobs": False,
                "api_version": API_VERSION, "reason": "Queue database unavailable: " + type(error).__name__,
                "checked_at": time.time(), "retry_after_seconds": 30}
    control = state.get("service_control", {})
    memory = state.get("memory_recovery", {})
    online = state.get("phase") != "stopped" and time.time() - state.get("heartbeat", 0) < 15
    if online:
        # A cancelled DB row can still own a worker until the scheduler confirms
        # process teardown. Keep the service busy/draining during that interval.
        running = list(dict.fromkeys(running + state.get("running_jobs", [])))
    paused = memory.get("status") in {"cooldown", "waiting_for_resources", "manual_intervention"}
    maintenance = bool(control.get("enabled"))
    if maintenance:
        mode = "draining" if running else "upgrading"
    elif not online:
        mode = "unavailable"
    elif paused:
        mode = "degraded"
    else:
        mode = "busy" if running else "available"
    ready = online and not maintenance and not paused
    return {"status": mode, "ready": ready, "accepting_jobs": online and not maintenance,
            "api_version": API_VERSION, "checked_at": time.time(), "scheduler_online": online,
            "scheduler_phase": state.get("phase", "not_started"), "running_jobs": running,
            "queue_counts": counts, "queue_paused": maintenance or paused,
            "maintenance": control, "memory_recovery_status": memory.get("status", "ready"),
            "reason": control.get("reason", "") if maintenance else memory.get("reason", "") if paused else "",
            "retry_after_seconds": 0 if ready else 30}


def service_status(store):
    return status_from_database(store.directory)
