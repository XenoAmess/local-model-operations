#!/usr/bin/env python3
"""Measure the loopback candidate on the existing private Omni workload."""
import hashlib
import json
import os
import statistics
from pathlib import Path
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("H3_FRAMEWORK_OUTPUT_DIR", str(ROOT / "outputs/framework-comparison-20261117")))
UNIT = os.environ.get("H3_FRAMEWORK_UNIT", "llmlab-sglang-omni-candidate-20261117.service")
BACKEND = os.environ.get("H3_FRAMEWORK_BACKEND", "sglang")
MAX_REQUEST_SECONDS = float(os.environ.get("H3_FRAMEWORK_MAX_REQUEST_SECONDS", "1500"))


def main():
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True)
    client = requests.Session()
    client.trust_env = False
    base = "http://127.0.0.1:" + {"uniserve": "18012", "sglang": "18011", "fastvideo": "18013"}[BACKEND]
    report = dict(status="waiting_for_candidate", started=time.time(), runs=[],
                  source_workload="outputs/omni-bf16-benchmark/request.json",
                  baseline_s=759.2129165099468, precision="BF16 DiT and text encoder, original 36L FP32 VAE",
                  numerical_note="SGLang fuses PDD heads and uses its native VSA; no claim of bitwise equivalence",
                  local_sm120_adapter=os.environ.get("H3_FRAMEWORK_EXPERIMENTAL_SM120") == "1")
    report["request_deadline_s"] = MAX_REQUEST_SECONDS
    warmup_count = int(os.environ.get("H3_FRAMEWORK_WARMUP_REQUESTS", "0"))
    report.update(warmup_requests=warmup_count,
                  steady_methodology="Exclude warmup requests; startup reported separately; complete sequential requests, not kernel-only time",
                  conditioning_cache_disabled=os.environ.get("H3_FRAMEWORK_DISABLE_CONDITIONING_CACHE") == "1")
    if BACKEND == "uniserve":
        report.update(precision="BF16 DiT and text encoder, native quality 36L VAE with FP16 projection storage",
                      numerical_note="Native PDD head fusion and kernels; local CPU-direct loading adapter. Not bitwise equivalent to FastVideo.",
                      local_cpu_load_adapter=True)
    elif BACKEND == "fastvideo":
        report.update(numerical_note="Unchanged production BF16 configuration with staged lazy loading; per-job internal reloads remain part of steady latency")

    def save():
        (OUT / f"{BACKEND}-http-benchmark.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    try:
        wait_started = time.monotonic()
        seen_started = False
        while time.monotonic() - wait_started < 1800:
            state = subprocess.run(["systemctl", "--user", "is-active", UNIT], capture_output=True, text=True).stdout.strip()
            if state in ("active", "activating"):
                seen_started = True
            if state == "failed" or (seen_started and state not in ("active", "activating")):
                raise RuntimeError("Candidate exited during initialization")
            try:
                ready = client.get(base + "/health", timeout=2)
                if ready.ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        else:
            raise TimeoutError("Candidate readiness timeout")
        report["readiness_wait_s"] = time.monotonic() - wait_started
        response = client.get(base + "/v1/models", timeout=10)
        response.raise_for_status()
        model = response.json()["data"][0]["id"]
        original = json.loads((ROOT / "outputs/omni-bf16-benchmark/request.json").read_text())
        conditions = []
        for key, kind, uri_key in (("image_reference", "image", "image_url"),
                                   ("video_reference", "video_audio", "video_url")):
            for value in original.get(key, []):
                path = Path(value[uri_key])
                conditions.append(dict(type=kind, role="reference", uri=path.resolve().as_uri() if BACKEND == "uniserve" else str(path)))
                report.setdefault("reference_sha256", {})[kind] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = dict(model=model, prompt=original["prompt"], task="ref2va", conditions=conditions,
                       target=dict(short_edge=768, aspect_ratio="16:9", duration_seconds=5.0),
                       seed=original["seed"], num_inference_steps=8, quality="exact")
        if BACKEND == "uniserve":
            del payload["num_inference_steps"], payload["quality"]
        elif BACKEND == "sglang":
            # The Omni subclass already defaults to this released policy;
            # pin it explicitly so generic H3 defaults cannot change it.
            payload["reference_resize_mode"] = "diffusers"
            report["reference_resize_mode"] = "diffusers"
        else:
            payload = {**original, "model": model}
        (OUT / f"{BACKEND}-private-request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        for repeat in range(int(os.environ.get("H3_FRAMEWORK_REPEATS", "2"))):
            seeds = json.loads(os.environ.get("H3_FRAMEWORK_SEEDS", "null"))
            payload["seed"] = seeds[repeat] if seeds is not None else original["seed"]
            started = time.monotonic()
            response = client.post(base + "/v1/videos", json=payload, timeout=60)
            if not response.ok:
                raise RuntimeError(f"POST {response.status_code}: {response.text[:2000]}")
            job = response.json()
            row = dict(repeat=repeat, id=job["id"], status=job["status"], elapsed_s=0,
                       seed=payload["seed"], warmup=repeat < warmup_count)
            report["runs"].append(row)
            report["status"] = "generating"
            while time.monotonic() - started < MAX_REQUEST_SECONDS:
                response = client.get(base + "/v1/videos/" + row["id"], timeout=10)
                response.raise_for_status()
                job = response.json()
                row.update(status=job["status"], elapsed_s=time.monotonic() - started)
                (OUT / f"{BACKEND}-job-{repeat}.json").write_text(json.dumps(job, indent=2) + "\n")
                save()
                if job["status"] == "completed":
                    break
                if job["status"] in ("failed", "cancelled"):
                    raise RuntimeError("Candidate inference failed: " + str(job.get("error")))
                state = subprocess.run(["systemctl", "--user", "is-active", UNIT], capture_output=True, text=True).stdout.strip()
                if state != "active":
                    raise RuntimeError("Candidate process exited during inference")
                time.sleep(3)
            else:
                raise TimeoutError(f"Candidate request exceeded the {MAX_REQUEST_SECONDS:g}-second measurement limit")
            row["wall_s"] = time.monotonic() - started
            row["server_reported_inference_s"] = job.get("inference_time_s")
            row["server_stage_durations"] = job.get("stage_durations")
            save()
            if os.environ.get("H3_FRAMEWORK_YIELD_TO_PRODUCTION") == "1":
                import sqlite3
                db = sqlite3.connect(ROOT / "outputs/video-queue/queue.sqlite3")
                waiting = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','in_progress')").fetchone()[0]
                db.close()
                if waiting or (OUT.parent / "suite.cancel").exists():
                    report.update(status="yielded_to_production", production_waiting=waiting)
                    return
        # Download after all submissions so validation does not insert idle
        # GPU gaps between the measured sequential production requests.
        for repeat, row in enumerate(report["runs"]):
            media = OUT / f"{BACKEND}-result-{repeat}.mp4"
            with client.get(base + "/v1/videos/" + row["id"] + "/content", timeout=120, stream=True) as response:
                response.raise_for_status()
                with media.open("wb") as output:
                    for data in response.iter_content(1024 * 1024):
                        output.write(data)
            row["ffprobe"] = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration,size", "-of", "json", str(media)], text=True))
            video = next(stream for stream in row["ffprobe"]["streams"] if stream["codec_type"] == "video")
            if (video["width"], video["height"], int(video["nb_frames"]), video["r_frame_rate"]) != (1344, 768, 124, "24/1"):
                raise RuntimeError("Candidate returned a different video workload")
            if not any(stream["codec_type"] == "audio" for stream in row["ffprobe"]["streams"]):
                raise RuntimeError("Candidate returned no soundtrack")
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(media), "-f", "null", "-"], check=True)
            save()
        measured = [row for row in report["runs"] if not row["warmup"]]
        if measured:
            report["steady"] = dict(samples=len(measured),
                median_request_s=statistics.median(row["wall_s"] for row in measured),
                total_request_s=sum(row["wall_s"] for row in measured),
                videos_per_hour=3600 * len(measured) / sum(row["wall_s"] for row in measured),
                generated_video_seconds_per_wall_minute=(124/24) * len(measured) * 60 / sum(row["wall_s"] for row in measured))
        report["status"] = "requests_measured_not_quality_equivalence_validated"
    except Exception as error:
        report.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        report["finished"] = time.time()
        save()
        subprocess.run(["systemctl", "--user", "stop", UNIT], check=False)
        journal = subprocess.run(["journalctl", "--user", "-u", UNIT, "--no-pager", "-o", "cat"], capture_output=True, text=True).stdout
        (OUT / f"{BACKEND}-server.log").write_text(journal)


if __name__ == "__main__":
    main()
