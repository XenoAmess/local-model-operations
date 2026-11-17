#!/usr/bin/env python3
"""Control one isolated BF16 Omni test, then restore the previous NVFP4 services."""

from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/omni-bf16-benchmark"
UNIT = "llmlab-h3-2k-omni-bf16-benchmark-20261116.service"
BASELINE = ROOT / "outputs/omni-restored-20261116"


def systemctl(*args, check=True):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=check)


def active(unit):
    return systemctl("is-active", unit, check=False).stdout.strip() == "active"


def collect_runtime_metrics(report):
    """Use stage peaks: the API's final memory statistic resets between stages."""
    journal = subprocess.run(["journalctl", "--user", "-u", UNIT, "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, check=False).stdout
    (OUT / "worker.log").write_text(journal)
    peaks = [float(value) for value in re.findall(r"Memory peak_allocated=([\d.]+) GiB", journal)]
    if peaks:
        report["maximum_stage_peak_allocated_gib"] = max(peaks)
    profiles = [json.loads(value) for value in re.findall(r"H3_STAGE_MS (\{[^\n]+\})", journal)]
    report["forward_cuda_profiles_ms"] = profiles
    starts, durations = {}, {}
    for clock, event, name in re.findall(
            r"INFO \d\d-\d\d (\d\d:\d\d:\d\d\.\d+) \[lazy_module.py:\d+\] "
            r"(Loading deferred module|Loaded deferred module) ([a-z_]+)", journal):
        timestamp = datetime.strptime(clock, "%H:%M:%S.%f")
        if event == "Loading deferred module":
            starts[name] = timestamp
        elif name in starts:
            elapsed = (timestamp - starts.pop(name)).total_seconds() % 86400
            durations[name] = durations.get(name, 0.0) + elapsed
    report["module_loading_intervals_s"] = durations


def main():
    for kind in ["export", "base"]:
        verification = json.loads((ROOT / f"deployment/omni-bf16/{kind}-weight-verification.json").read_text())
        if verification["status"] != "verified":
            raise RuntimeError("Complete verified BF16 weights are required")
    if not (ROOT / "deployment/omni-bf16/composition.json").is_file():
        raise RuntimeError("BF16 model composition has not completed")
    OUT.mkdir(parents=True, exist_ok=True)
    client = requests.Session()
    client.trust_env = False
    original = {name: active(name) for name in ["fasth3-omni.service", "fasth3-omni-web.service"]}
    baseline = json.loads((BASELINE / "status.json").read_text())
    report = {"status": "preparing", "started_at": datetime.now(timezone.utc).isoformat(),
              "unit": UNIT, "original_services": original, "baseline": baseline["inference_time_s"],
              "baseline_stage_durations": baseline["stage_durations"],
              "baseline_stack": "NVFP4 QAD DiT and encoder, NVFP4 quality-36L decoder; GPU-resident before request",
              "sampling_steps": 8, "size": "1344x768", "requested_seconds": 5,
              "attention": "BF16 tile-128 VSA Triton kernel, trained sparsity 0.9 and reference keep rate 0.1",
              "text_encoder": "BF16", "denoiser": "BF16, no NVFP4 export",
              "decoder": "original 36-layer VAE, FP32 weights with released FP16 decode autocast; no NVFP4 decoder",
              "loading_policy": "lazy staged load; encoder, VAE and DiT load on demand and release at final use",
              "cancelled_by_signal": False, "model_process": None}

    def save():
        temporary = OUT / "run-status.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(OUT / "run-status.json")

    def interrupt(signum, frame):
        report["cancelled_by_signal"] = True
        raise KeyboardInterrupt("Benchmark was interrupted; do not automatically restart models")

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    launch = None
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    save()
    try:
        # Do not interrupt a generation somebody already submitted to Omni.
        if original["fasth3-omni.service"]:
            while True:
                response = client.get("http://127.0.0.1:8001/v1/videos?limit=100", timeout=10)
                response.raise_for_status()
                pending = [j for j in response.json()["data"] if j["status"] in {"queued", "in_progress"}]
                if not pending:
                    break
                report.update(status="waiting_for_existing_omni_jobs", pending_jobs=len(pending))
                save()
                time.sleep(10)
        systemctl("stop", "fasth3-omni-web.service", "fasth3-omni.service")
        started = time.monotonic()
        with (OUT / "launcher.log").open("ab") as log:
            launch = subprocess.Popen(["/usr/bin/python3", str(ROOT / "llm-lab/scripts/run_isolated.py"),
                                       "--unit", UNIT.removesuffix(".service"), "--memory-gib", "80", "--wait", "--",
                                       str(ROOT / "start-omni-bf16-benchmark.sh")], stdout=log, stderr=subprocess.STDOUT)
        report.update(status="starting_bf16", model_process=launch.pid)
        save()
        for attempt in range(180):
            if launch.poll() is not None:
                raise RuntimeError("BF16 service exited during startup; inspect its journal")
            try:
                response = client.get("http://127.0.0.1:8001/v1/models", timeout=2)
                if response.ok and response.json()["data"][0]["id"] == "fasth3-omni-bf16":
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("BF16 HTTP startup did not complete")
        report["api_startup_s"] = time.monotonic() - started
        payload = json.loads((BASELINE / "request.json").read_text())
        payload.update(model="fasth3-omni-bf16", size="1344x768")
        (OUT / "request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        response = client.post("http://127.0.0.1:8001/v1/videos", json=payload, timeout=90)
        response.raise_for_status()
        job = response.json()
        job_started = time.monotonic()
        report.update(status="generating", job=job["id"])
        save()
        while True:
            response = client.get("http://127.0.0.1:8001/v1/videos/" + job["id"], timeout=10)
            response.raise_for_status()
            job = response.json()
            (OUT / "job-status.json").write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n")
            report.update(job_status=job["status"], elapsed_generation_s=time.monotonic() - job_started)
            save()
            if job["status"] == "completed":
                break
            if job["status"] in {"failed", "cancelled"}:
                raise RuntimeError("BF16 generation failed: " + str(job.get("error")))
            if launch.poll() is not None or time.monotonic() - job_started > 7200:
                raise RuntimeError("BF16 process exited or exceeded the two-hour observation limit")
            time.sleep(10)
        with client.get("http://192.168.1.11:8001/v1/videos/" + job["id"] + "/content", stream=True, timeout=180) as response:
            response.raise_for_status()
            with (OUT / "result-lan.mp4").open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    stream.write(chunk)
        media = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration,size", "-of", "json", str(OUT / "result-lan.mp4")], text=True))
        video = next(s for s in media["streams"] if s["codec_type"] == "video")
        if (video["width"], video["height"], int(video["nb_frames"])) != (1344, 768, 124):
            raise RuntimeError("BF16 result has unexpected media geometry")
        report.update(status="measured", inference_time_s=job["inference_time_s"],
                      stage_durations=job["stage_durations"], api_memory_metric_mb=job.get("peak_memory_mb"),
                      api_memory_metric_note="Final-stage counter; not the global GPU peak. Use stage log peaks.",
                      ffprobe=media, sha256=hashlib.sha256((OUT / "result-lan.mp4").read_bytes()).hexdigest())
        copy = ROOT / "omni-web/outputs/omni-bf16-768p-5s-20261116.mp4"
        shutil.copyfile(OUT / "result-lan.mp4", copy)
        report["download_url"] = "http://192.168.1.11:7860/gradio_api/file=" + str(copy)
    except BaseException as error:
        report.update(status="interrupted" if report["cancelled_by_signal"] else "failed",
                      error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        try:
            collect_runtime_metrics(report)
        except Exception as error:
            report["metric_collection_error"] = type(error).__name__ + ": " + str(error)
        report["unit_resources"] = systemctl("show", UNIT, "-p", "MemoryPeak", "-p", "MemorySwapPeak", "-p", "Result", check=False).stdout.strip()
        systemctl("stop", UNIT, check=False)
        if launch is not None:
            try:
                launch.wait(timeout=45)
            except subprocess.TimeoutExpired:
                launch.terminate()
        if not report["cancelled_by_signal"] and not (OUT / "do-not-restore").exists():
            restore = [name for name, running in original.items() if running]
            if restore:
                restored = systemctl("start", *restore, check=False)
                report["restore_requested"] = restored.returncode == 0
                for _ in range(180):
                    try:
                        response = client.get("http://127.0.0.1:8001/v1/models", timeout=2)
                        if response.ok and response.json()["data"][0]["id"] == "fasth3-omni":
                            report["nvfp4_restored"] = True
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
        report["ended_at"] = datetime.now(timezone.utc).isoformat()
        save()
        lease.close()


if __name__ == "__main__":
    main()
