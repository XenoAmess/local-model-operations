#!/usr/bin/env python3
"""One GPU owner for the BF16 Omni and local 2K HTTP queues."""

import asyncio
from contextlib import suppress
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

import requests
import httpx

from video_queue import OMNI, REFINER, ROOT, QueueChanged, QueueStore
from h3_refiner_profiles import get_profile
from model_registry import effective_duration, select_job, task_sort_key
from queued_llm import execute_llm_job
from video_queue_recovery import QueueRecovery, probe_resources

BACKEND_UNIT = "fasth3-omni-bf16-worker.service"
BACKEND_URL = "http://127.0.0.1:8003"


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


async def systemctl(*args, check=True):
    process = await asyncio.create_subprocess_exec("systemctl", "--user", *args,
                                                  stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(process.communicate(), 45)
    if process.returncode and check:
        raise RuntimeError(stderr.decode().strip() or stdout.decode().strip())
    return stdout.decode().strip()


class Scheduler:
    def __init__(self, store=None):
        self.store = store or QueueStore()
        self.stop = asyncio.Event()
        self.model = None
        self.ready_at = None
        self.consecutive = 0
        self.backend = False
        self.lease = None
        self.current = []
        self.active_unit = None
        self.llm_worker = None
        self.last_job = time.monotonic()
        self.http = requests.Session()
        self.http.trust_env = False
        self.recovery = QueueRecovery(self.store)
        self.phase = "starting"

    async def recover_memory(self):
        """Only the GPU owner cleans workers and releases a durable recovery gate."""
        self.recovery.sync_legacy()
        memory = self.recovery.snapshot()
        if not memory["paused"]:
            return False
        if not memory.get("cleanup_complete"):
            try:
                registered = {m[key] for m in self.store.models.values() for key in ("worker_unit", "isolated_unit") if key in m}
                registered.add("llmlab-fasth3-omni-bf16-worker.service")
                units = sorted(registered) + memory.get("worker_units", [])
                for unit in dict.fromkeys(units):
                    if not unit or (unit not in registered and not unit.startswith(("llmlab-h3-2k-refiner-batch-", "llmlab-blender-review-"))):
                        continue
                    await systemctl("stop", unit, check=False)
                    active = await systemctl("is-active", unit, check=False)
                    if active not in {"inactive", "failed", "unknown"}:
                        raise RuntimeError("Worker stop could not be confirmed: " + unit)
                self.backend = False
                self.llm_worker = None
                self.active_unit = None
                await self.release()
                self.recovery.cleanup_result(memory["incident_id"])
            except Exception as error:
                self.recovery.cleanup_result(memory["incident_id"], str(error)[:500])
        resources = await asyncio.to_thread(probe_resources, self.recovery.policy)
        if self.recovery.observe(memory["incident_id"], resources):
            self.state("idle")
            return False
        memory = self.recovery.snapshot()
        phase = ("memory_circuit_open" if memory["manual_resume_required"] else
                 "recovering_after_memory_failure" if not memory.get("cleanup_complete") else
                 "memory_cooldown" if memory["cooldown_remaining_seconds"] else "waiting_for_memory_resources")
        self.state(phase)
        return True

    def state(self, phase):
        self.phase = phase
        self.store.set_state(active_model=self.model, consecutive=self.consecutive, phase=phase,
                             model_ready_at=self.ready_at,
                             running_jobs=[job["id"] for job in self.current],
                             backend_unit=BACKEND_UNIT if self.backend else self.llm_worker)

    async def heartbeat(self):
        while True:
            self.state(self.phase)
            await asyncio.sleep(5)

    async def external_busy(self):
        output = await systemctl("list-units", "--state=running", "--no-legend",
                                 "llmlab-h3-2k-*.service", "llmlab-fasth3-omni.service",
                                 "llmlab-coder-lan.service", "llmlab-minimax-h3*.service")
        return bool(output.strip())

    def acquire(self):
        if self.lease is not None:
            return True
        lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lease.close()
            return False
        self.lease = lease
        return True

    async def stop_workers(self, next_model=None):
        if self.backend and next_model != OMNI:
            await systemctl("stop", BACKEND_UNIT)
            self.backend = False
        if self.llm_worker and self.llm_worker != self.store.models.get(next_model, {}).get("worker_unit"):
            await systemctl("stop", self.llm_worker)
            self.llm_worker = None

    async def release(self):
        await self.stop_workers()
        if self.lease is not None:
            self.lease.close()
            self.lease = None
        self.model, self.consecutive = None, 0
        self.ready_at = None

    def select(self, ready):
        duration = effective_duration(self.store.registry, self.store.preferences(), self.model)
        return select_job(ready, self.model, self.ready_at, duration)

    async def request(self, method, path, **kwargs):
        response = await asyncio.to_thread(self.http.request, method, BACKEND_URL + path, timeout=15, **kwargs)
        response.raise_for_status()
        return response

    async def start_backend(self):
        if self.backend:
            return
        self.state("loading_bf16_runtime")
        await systemctl("start", BACKEND_UNIT)
        self.backend = True  # cleanup also applies when readiness fails
        for _ in range(90):
            if self.stop.is_set():
                raise InterruptedError("Scheduler is stopping")
            try:
                response = await self.request("GET", "/v1/models")
                if response.json()["data"][0]["id"] == OMNI:
                    self.ready_at = time.time()
                    return
            except requests.RequestException:
                pass
            await asyncio.sleep(1)
        raise RuntimeError("BF16 worker HTTP startup timed out")

    async def start_llm(self, entry, client):
        if self.llm_worker == entry["worker_unit"] and self.ready_at is not None:
            return
        self.state("loading_llm_worker")
        self.llm_worker = entry["worker_unit"]
        await systemctl("start", self.llm_worker)
        deadline = time.monotonic() + entry.get("startup_timeout_seconds", 360)
        while time.monotonic() < deadline:
            if self.stop.is_set():
                raise InterruptedError("Scheduler is stopping")
            try:
                result = await client.get(entry["worker_url"] + "/v1/models", timeout=2)
                if result.is_success and any(row["id"] == self.model for row in result.json()["data"]):
                    self.ready_at = time.time()
                    return
            except (ValueError, KeyError, httpx.HTTPError):
                pass
            if await systemctl("is-active", self.llm_worker, check=False) in {"inactive", "failed"}:
                raise RuntimeError("Qwen worker exited during startup")
            await asyncio.sleep(1)
        raise RuntimeError("Qwen worker startup timed out")

    async def execute_llm(self, jobs, entry):
        async with httpx.AsyncClient(trust_env=False, timeout=None,
                                     limits=httpx.Limits(max_connections=entry["max_inflight"] + 1)) as client:
            await self.start_llm(entry, client)
            self.store.claim([job["id"] for job in jobs], self.llm_worker, jobs[0]["_queue_revision"])
            active = {}

            def send(batch):
                for job in batch:
                    task = asyncio.create_task(execute_llm_job(self.store, job, entry["worker_url"], client, self.stop))
                    active[task] = job

            send(jobs)
            try:
                while active and not self.stop.is_set():
                    self.state("llm_inference")
                    done, _ = await asyncio.wait(active, timeout=0.25, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        job = active.pop(task)
                        try:
                            task.result()
                        except MemoryError:
                            self.current = [job, *active.values()]
                            raise
                        except Exception as error:
                            self.store.change(job["id"], "failed", str(error), only_running=True)
                        if self.store.job_status(job["id"]) == "completed":
                            self.recovery.record_success()
                    self.current = list(active.values())
                    if not active or len(active) >= entry["max_inflight"]:
                        continue
                    ready = self.store.ready()
                    selected = self.select(ready)
                    if selected is None or selected["model"] != self.model:
                        continue
                    batch = sorted((j for j in ready if j["model"] == self.model), key=task_sort_key)
                    batch = batch[:entry["max_inflight"] - len(active)]
                    try:
                        self.store.claim([j["id"] for j in batch], self.llm_worker, batch[0]["_queue_revision"])
                    except QueueChanged:
                        continue
                    send(self.store.load_selected(batch))
                    self.current = list(active.values())
                if self.stop.is_set():
                    raise InterruptedError("Scheduler is stopping")
            finally:
                for task in active:
                    task.cancel()
                await asyncio.gather(*active, return_exceptions=True)

    async def execute_omni(self, job):
        await self.start_backend()
        self.store.claim([job["id"]], BACKEND_UNIT, expected_revision=job.get("_queue_revision"))
        payload = {key: value for key, value in job["request"].items() if key not in {"mode", "references"}}
        for kind in ("image", "video", "audio"):
            values = [{kind + "_url": ref["path"]} for ref in job["request"]["references"] if ref["kind"] == kind]
            if values:
                payload[kind + "_reference"] = values
        folder = Path(job["directory"])
        atomic_json(folder / "progress.json", {"stage": "BF16 Omni 推理中", "progress": 1})
        native = (await self.request("POST", "/v1/videos", json=payload)).json()
        self.store.event("bf16_backend_job", job=job["id"], backend_job=native["id"])
        while True:
            self.state("bf16_generation")
            if self.stop.is_set():
                raise InterruptedError("Scheduler is stopping")
            if self.store.job_status(job["id"]) == "cancelled":
                await systemctl("stop", BACKEND_UNIT)
                self.backend = False
                return
            native = (await self.request("GET", "/v1/videos/" + native["id"])).json()
            atomic_json(folder / "backend-status.json", native)
            if native["status"] == "completed":
                break
            if native["status"] in {"failed", "cancelled"}:
                raise RuntimeError(str(native.get("error") or native["status"]))
            await asyncio.sleep(2)
        # Native backend is local and its media path is inside this pinned output root.
        source = Path(native["file_path"]).resolve()
        if not source.is_relative_to((ROOT / "outputs/omni-bf16-api").resolve()):
            raise RuntimeError("Unexpected BF16 backend output path")
        destination = folder / "result.mp4"
        import shutil
        shutil.copyfile(source, destination)
        receipt = {key: native.get(key) for key in ("inference_time_s", "stage_durations", "size", "seconds")}
        with destination.open("rb") as stream:
            receipt.update(model=OMNI, backend_job=native["id"], sha256=hashlib.file_digest(stream, "sha256").hexdigest(),
                           cloud_used=False)
        atomic_json(folder / "result.json", receipt)
        log = subprocess.run(["journalctl", "--user", "-u", "llmlab-fasth3-omni-bf16-worker.service",
                              "-n", "220", "--no-pager", "-o", "cat"], capture_output=True, text=True).stdout
        (folder / "worker.log").write_text(log)
        self.store.change(job["id"], "completed", only_running=True)

    async def execute_refiner(self, jobs):
        if self.backend:
            await systemctl("stop", BACKEND_UNIT)
            self.backend = False
        unit = f"llmlab-h3-2k-refiner-batch-{jobs[0]['id'][-10:]}-{time.time_ns()}"
        self.active_unit = unit + ".service"
        self.store.claim([job["id"] for job in jobs], self.active_unit,
                         expected_revision=jobs[0].get("_queue_revision"))
        batch_dir = self.store.directory / "batches" / unit
        batch_dir.mkdir(parents=True)
        for job in jobs:
            request = dict(job["request"])
            if job["dependency"]:
                parent = self.store.get(job["dependency"])
                request["input_video"] = str(Path(parent["directory"]) / "result.mp4")
            atomic_json(Path(job["directory"]) / "request.json", request)
        batch = batch_dir / "jobs.json"
        atomic_json(batch, [job["directory"] for job in jobs])
        command = ["/usr/bin/python3", str(ROOT / "llm-lab/scripts/run_isolated.py"),
                   "--unit", unit, "--memory-gib", "80", "--wait", "--",
                   str(ROOT / "start-h3-2k-worker.sh"), str(ROOT / "tools/h3_2k_batch_worker.py"),
                   "--batch", str(batch)]
        interrupted = False
        sampled_peaks = {}
        cgroup = None
        with (batch_dir / "launcher.log").open("ab") as log:
            process = await asyncio.create_subprocess_exec(*command, stdout=log, stderr=log)
            while process.returncode is None:
                self.state("refiner_batch")
                if self.ready_at is None:
                    for job in jobs:
                        try:
                            progress = json.loads((Path(job["directory"]) / "progress.json").read_text())
                            if progress.get("progress", 0) >= 35:
                                self.ready_at = time.time()
                                break
                        except (OSError, ValueError):
                            pass
                if cgroup is None:
                    name = await systemctl("show", self.active_unit, "-p", "ControlGroup", "--value", check=False)
                    if name.startswith("/"):
                        cgroup = Path("/sys/fs/cgroup") / name.lstrip("/")
                if cgroup is not None:
                    for field, filename in [("MemoryPeak", "memory.peak"), ("MemorySwapPeak", "memory.swap.peak")]:
                        try:
                            value = int((cgroup / filename).read_text().strip())
                            sampled_peaks[field] = max(sampled_peaks.get(field, 0), value)
                        except (OSError, ValueError):
                            pass
                if self.stop.is_set() or any(self.store.job_status(j["id"]) == "cancelled" for j in jobs):
                    interrupted = True
                    await systemctl("stop", self.active_unit)
                    break
                try:
                    await asyncio.wait_for(process.wait(), 2)
                except asyncio.TimeoutError:
                    pass
            code = await process.wait()
        resources = await systemctl("show", self.active_unit, "-p", "Result", "-p", "MemoryPeak", "-p", "MemorySwapPeak", check=False)
        resource_values = dict(line.split("=", 1) for line in resources.splitlines())
        for field, value in sampled_peaks.items():
            if not resource_values.get(field, "").isdigit():
                resource_values[field] = str(value)
        resource_values["peak_collection"] = "cgroup kernel peak counters sampled while worker was alive"
        atomic_json(batch_dir / "resources.json", resource_values)
        for job in jobs:
            if self.store.job_status(job["id"]) == "cancelled":
                continue
            folder = Path(job["directory"])
            if (folder / "result.json").is_file() and (folder / "result.mp4").is_file():
                self.store.change(job["id"], "completed", only_running=True)
            elif interrupted:
                self.store.change(job["id"], "queued", "Interrupted; verified windows retained for resumption", only_running=True)
            else:
                self.store.change(job["id"], "failed", f"2K batch exited {code}; inspect batch worker log", only_running=True)
            if (batch_dir / "worker.log").exists():
                with (folder / "worker.log").open("a") as target:
                    target.write((batch_dir / "worker.log").read_text()[-24000:])
        if "oom-kill" in resources:
            raise MemoryError("2K batch exhausted its memory allowance; inspect before resuming")
        if code and not interrupted:
            # Full-sequence work logs to its job folder; window cohorts log to
            # the batch. Both must feed the same CUDA-OOM recovery policy.
            log_paths = [batch_dir / "worker.log", batch_dir / "launcher.log"]
            log_paths.extend(Path(job["directory"]) / "worker.log" for job in jobs)
            log_text = ""
            for path in log_paths:
                if path.exists():
                    with path.open("rb") as stream:
                        stream.seek(max(0, path.stat().st_size - 24000))
                        log_text += stream.read().decode(errors="replace")
            if "out of memory" in log_text.lower():
                raise MemoryError("2K CUDA memory failure; inspect before resuming")
        self.active_unit = None

    async def execute_blender(self, job):
        import sys
        folder = Path(job["directory"])
        unit = f"llmlab-blender-review-{job['id'][-12:]}-{time.time_ns()}"
        self.active_unit = unit + ".service"
        self.store.claim([job["id"]], self.active_unit, job["_queue_revision"])
        command = ["/usr/bin/python3", str(ROOT / "llm-lab/scripts/run_isolated.py"), "--unit", unit,
                   "--memory-gib", "80", "--runtime-max-seconds", str(job["request"]["params"]["timeout_seconds"] + 120),
                   "--wait", "--", sys.executable, str(ROOT / "tools/blender_review_worker.py"), str(folder)]
        with (folder / "launcher.log").open("ab") as log:
            process = await asyncio.create_subprocess_exec(*command, stdout=log, stderr=log)
            while process.returncode is None:
                self.state("blender_rendering")
                if self.ready_at is None and (folder / "render-ready").exists():
                    self.ready_at = time.time()
                if self.stop.is_set() or self.store.job_status(job["id"]) == "cancelled":
                    await systemctl("stop", self.active_unit, check=False)
                    await process.wait()
                    if self.stop.is_set():
                        raise InterruptedError("Scheduler is stopping")
                    self.active_unit = None
                    return
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except asyncio.TimeoutError:
                    pass
        result = await systemctl("show", self.active_unit, "-p", "Result", "--value", check=False)
        if result == "oom-kill":
            raise MemoryError("Blender rendering exhausted its memory allowance")
        self.active_unit = None
        if process.returncode or not (folder / "result.zip").is_file():
            error_file = folder / "worker-error.json"
            message = json.loads(error_file.read_text())["message"] if error_file.is_file() else f"Blender exited {process.returncode}"
            raise RuntimeError(message)
        self.store.change(job["id"], "completed", only_running=True)

    def cohort(self, selected, ready):
        entry = self.store.models[selected["model"]]
        if entry["adapter"] == "openai_llm":
            jobs = sorted((j for j in ready if j["model"] == selected["model"]), key=task_sort_key)[:entry["max_inflight"]]
            return self.store.load_selected(jobs)
        jobs = self.store.load_selected([selected])
        if selected["model"] != REFINER:
            return jobs
        request = jobs[0]["request"]
        if get_profile(request["size"]).max_jobs_per_cohort == 1:
            return jobs
        key = tuple(request[k] for k in ("seed", "size", "sampler"))
        remaining = [job for job in ready if job["id"] != selected["id"]]
        residence = self.ready_at if self.model == REFINER else time.time()
        duration = effective_duration(self.store.registry, self.store.preferences(), REFINER)
        candidate = select_job(remaining, REFINER, residence, duration)
        if candidate and candidate["model"] == REFINER:
            candidate = self.store.load_selected([candidate])[0]
            if tuple(candidate["request"][k] for k in ("seed", "size", "sampler")) == key:
                jobs.append(candidate)
        return jobs

    async def run(self):
        self.store.initialize()
        self.store.migrate_refiner()
        singleton = (self.store.directory / "scheduler.lock").open("a")
        fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        heartbeat = asyncio.create_task(self.heartbeat())
        try:
            # No API process resets active jobs. Recovery belongs to this single owner.
            for entry in self.store.models.values():
                if entry.get("worker_unit"):
                    await systemctl("stop", entry["worker_unit"], check=False)
            for job in self.store.pending(running_only=True):
                if job["unit"]:
                    await systemctl("stop", job["unit"])
                replayable = job["request"].get("task_kind", "video") == "video"
                self.store.change(job["id"], "queued" if replayable else "failed", "Interrupted by scheduler restart")
            self.store.event("scheduler_started")
            while not self.stop.is_set():
                self.store.fail_dependencies()
                canary = self.store.state().get("service_control", {}).get("validation_job")
                if canary and self.store.job_status(canary) in {"completed", "failed", "cancelled"}:
                    self.store.maintenance(True, "Full-sequence canary finished; automated result verification in progress")
                if await self.recover_memory():
                    await asyncio.sleep(self.recovery.policy.probe_interval_seconds)
                    continue
                if self.store.state().get("service_control", {}).get("enabled"):
                    await self.release()
                    self.state("upgrading")
                    await asyncio.sleep(1)
                    continue
                ready = self.store.ready()
                selected = self.select(ready)
                if selected is None:
                    if self.lease and time.monotonic() - self.last_job >= self.store.registry["idle_release_seconds"]:
                        await self.release()
                    self.state("idle")
                    await asyncio.sleep(1)
                    continue
                if not self.acquire() or await self.external_busy():
                    if not self.backend and self.lease:
                        self.lease.close()
                        self.lease = None
                    self.state("waiting_for_external_gpu_user")
                    await asyncio.sleep(2)
                    continue
                self.current = self.cohort(selected, ready)
                old_model = self.model
                self.model = selected["model"]
                if old_model != self.model:
                    self.consecutive = 0
                    self.ready_at = None
                    self.store.event("model_switch", previous=old_model, model=self.model)
                self.store.event("dispatch", model=self.model, jobs=[j["id"] for j in self.current])
                try:
                    await self.stop_workers(self.model)
                    entry = self.store.models[self.model]
                    adapter = entry["adapter"]
                    if adapter == "omni":
                        await self.execute_omni(self.current[0])
                    elif adapter == "ic":
                        await self.execute_refiner(self.current)
                    elif adapter == "openai_llm":
                        await self.execute_llm(self.current, entry)
                    elif adapter == "blender_review":
                        await self.execute_blender(self.current[0])
                    if any(self.store.job_status(job["id"]) == "completed" for job in self.current):
                        if self.ready_at is None:
                            self.ready_at = time.time()
                        self.recovery.record_success()
                except InterruptedError:
                    break
                except QueueChanged:
                    # The transaction rolled back. Keep uncancelled siblings queued.
                    self.active_unit = None
                    self.current = []
                    continue
                except Exception as error:
                    message = type(error).__name__ + ": " + str(error)
                    for job in self.current:
                        self.store.change(job["id"], "failed", message, only_running=True)
                        # Startup/adaptation failures can precede a successful claim.
                        if self.store.job_status(job["id"]) == "queued":
                            self.store.change(job["id"], "failed", message)
                    self.store.event("execution_failed", model=self.model, error=message)
                    gpu_result = (await systemctl("show", "llmlab-fasth3-omni-bf16-worker.service", "-p", "Result", "--value", check=False)
                                  if self.model == OMNI else "")
                    isolated_llm = self.store.models[self.model].get("isolated_unit")
                    if isolated_llm:
                        gpu_result = await systemctl("show", isolated_llm, "-p", "Result", "--value", check=False)
                    memory_failure = isinstance(error, MemoryError) or "out of memory" in message.lower() or gpu_result == "oom-kill"
                    if memory_failure:
                        self.recovery.record_failure([j["id"] for j in self.current
                                                      if self.store.job_status(j["id"]) == "failed"], message,
                                                     [self.active_unit] + [j.get("unit") for j in self.current])
                    else:
                        if self.active_unit:
                            await systemctl("stop", self.active_unit, check=False)
                            self.active_unit = None
                        await self.release()
                self.consecutive += len(self.current)
                self.current = []
                self.last_job = time.monotonic()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            if self.active_unit:
                await systemctl("stop", self.active_unit, check=False)
            await self.release()
            for job in self.current:
                replayable = job["request"].get("task_kind", "video") == "video"
                self.store.change(job["id"], "queued" if replayable else "failed", "Interrupted by scheduler stop", only_running=True)
            self.current = []
            self.state("stopped")
            self.store.event("scheduler_stopped")
            singleton.close()


async def main():
    scheduler = Scheduler()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, scheduler.stop.set)
    await scheduler.run()


if __name__ == "__main__":
    asyncio.run(main())
