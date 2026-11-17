#!/usr/bin/env python3
"""Compare three resident HTTP servers after a full workload warmup, with cache hits excluded."""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/framework-comparison-20261117/steady"
COORDINATOR = "video-gpu-scheduler.service"


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def waiting():
    with sqlite3.connect(ROOT / "outputs/video-queue/queue.sqlite3") as db:
        return db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','in_progress')").fetchone()[0]


def main():
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True)
    owner = (OUT / "suite-owner.lock").open("a")
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    report = dict(status="preparing", started=time.time(), results=[],
                  methodology="One complete warmup excluded, then two sequential complete768p/124-frame/8-forward jobs; same media/prompt/seeds, no conditioning-cache hits; startup separate",
                  warmup_seed=1234, measured_seeds=[1234, 1235], cold_start_used_for_ranking=False)

    def save():
        temporary = OUT / "suite-status.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(OUT / "suite-status.json")

    specs = (
        ("uniserve", ROOT / "tools/vendor/uniserve-candidate/.venv/bin/python", "run_uniserve_omni_candidate.py"),
        ("sglang", ROOT / "tools/vendor/sglang-candidate/.venv/bin/python", "run_sglang_omni_candidate.py"),
        ("fastvideo", ROOT / "FastVideo/.venv/bin/python", "run_fastvideo_omni_candidate.py"),
    )
    paused = False
    active_unit = None
    save()
    try:
        # Acquire the shared lease only to inspect and pause at an idle boundary.
        # Each actual model wrapper then owns it for that server's lifetime.
        lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if waiting():
            raise RuntimeError("Production jobs are waiting; do not pause for benchmarks")
        systemctl("stop", COORDINATOR).check_returncode()
        paused = True
        lease.close()
        for backend, python, wrapper in specs:
            if waiting() or (OUT / "suite.cancel").exists():
                report["status"] = "yielded_to_production"
                break
            directory = OUT / backend
            directory.mkdir(exist_ok=True)
            receipt = directory / f"{backend}-http-benchmark.json"
            if receipt.exists():
                raise RuntimeError("Refusing to overwrite previous measurements: " + str(receipt))
            report.update(status="running", backend=backend)
            save()
            active_unit = "llmlab-omni-steady-" + backend + "-20261117.service"
            command = ["/usr/bin/env", "H3_FRAMEWORK_EXPERIMENTAL_SM120=1",
                       "H3_FRAMEWORK_DISABLE_CONDITIONING_CACHE=1", str(python), str(ROOT / "tools" / wrapper)]
            launch = ["python3", str(ROOT / "llm-lab/scripts/run_isolated.py"),
                      "--unit", active_unit.removesuffix(".service"), "--memory-gib", "80",
                      "--runtime-max-seconds", "3600", "--wait", "--", *command]
            env = os.environ.copy()
            env.update(H3_FRAMEWORK_OUTPUT_DIR=str(directory), H3_FRAMEWORK_BACKEND=backend,
                       H3_FRAMEWORK_UNIT=active_unit, H3_FRAMEWORK_REPEATS="3",
                       H3_FRAMEWORK_WARMUP_REQUESTS="1", H3_FRAMEWORK_SEEDS="[1234,1234,1235]",
                       H3_FRAMEWORK_MAX_REQUEST_SECONDS="1500", H3_FRAMEWORK_YIELD_TO_PRODUCTION="1",
                       H3_FRAMEWORK_DISABLE_CONDITIONING_CACHE="1", H3_FRAMEWORK_EXPERIMENTAL_SM120="1")
            with (directory / "launcher.log").open("w") as log:
                process = subprocess.Popen(launch, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                with (directory / "client.log").open("w") as clientlog:
                    code = subprocess.call(["python3", str(ROOT / "tools/measure_sglang_omni_http.py")],
                                           cwd=ROOT, env=env, stdout=clientlog, stderr=subprocess.STDOUT)
                process.wait(timeout=30)
            result = json.loads(receipt.read_text())
            report["results"].append(dict(backend=backend, client_exit=code, measurement=result))
            save()
            journal = (directory / f"{backend}-server.log").read_text()
            if "CUDA out of memory" in journal or "illegal memory access" in journal:
                raise RuntimeError("GPU memory/device failure; no automatic retries or further GPU tests")
            if code != 0:
                raise RuntimeError("Candidate failed; preserve evidence and review before proceeding")
            active_unit = None
            if result["status"] == "yielded_to_production":
                report["status"] = "yielded_to_production"
                break
        else:
            report["status"] = "measured_pending_review"
    except BaseException as error:
        report.update(status="stopped", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        if active_unit:
            systemctl("stop", active_unit)
        if paused:
            systemctl("start", COORDINATOR)
        report.update(finished=time.time(), coordinator_active=systemctl("is-active", COORDINATOR).stdout.strip() == "active")
        save()


if __name__ == "__main__":
    main()
