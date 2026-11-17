#!/usr/bin/env python3
"""Measure the loopback candidate on the existing private Omni workload."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/framework-comparison-20261117"
UNIT = os.environ.get("H3_FRAMEWORK_UNIT", "llmlab-sglang-omni-candidate-20261117.service")


def main():
    client = requests.Session()
    client.trust_env = False
    base = "http://127.0.0.1:18011"
    report = dict(status="waiting_for_candidate", started=time.time(), runs=[],
                  source_workload="outputs/omni-bf16-benchmark/request.json",
                  baseline_s=759.2129165099468, precision="BF16 DiT and text encoder, original 36L FP32 VAE",
                  numerical_note="SGLang fuses PDD heads and uses its native VSA; no claim of bitwise equivalence")

    def save():
        (OUT / "sglang-http-benchmark.json").write_text(json.dumps(report, indent=2) + "\n")

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
                conditions.append(dict(type=kind, role="reference", uri=str(path)))
                report.setdefault("reference_sha256", {})[kind] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = dict(model=model, prompt=original["prompt"], task="ref2va", conditions=conditions,
                       target=dict(short_edge=768, aspect_ratio="16:9", duration_seconds=5.0),
                       seed=original["seed"], num_inference_steps=8, quality="exact")
        (OUT / "sglang-private-request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        for repeat in range(2):
            started = time.monotonic()
            response = client.post(base + "/v1/videos", json=payload, timeout=60)
            if not response.ok:
                raise RuntimeError(f"POST {response.status_code}: {response.text[:2000]}")
            job = response.json()
            row = dict(repeat=repeat, id=job["id"], status=job["status"], elapsed_s=0)
            report["runs"].append(row)
            report["status"] = "generating"
            while time.monotonic() - started < 1500:
                response = client.get(base + "/v1/videos/" + row["id"], timeout=10)
                response.raise_for_status()
                job = response.json()
                row.update(status=job["status"], elapsed_s=time.monotonic() - started)
                (OUT / f"sglang-job-{repeat}.json").write_text(json.dumps(job, indent=2) + "\n")
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
                raise TimeoutError("Candidate request exceeded 25 minutes")
            row["wall_s"] = time.monotonic() - started
            media = OUT / f"sglang-result-{repeat}.mp4"
            with client.get(base + "/v1/videos/" + row["id"] + "/content", timeout=120, stream=True) as response:
                response.raise_for_status()
                with media.open("wb") as output:
                    for data in response.iter_content(1024 * 1024):
                        output.write(data)
            row["ffprobe"] = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration,size", "-of", "json", str(media)], text=True))
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(media), "-f", "null", "-"], check=True)
            save()
        report["status"] = "two_requests_measured_not_quality_equivalence_validated"
    except Exception as error:
        report.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        report["finished"] = time.time()
        save()
        if (OUT / "sglang-server-launch.log").exists():
            subprocess.run(["systemctl", "--user", "stop", UNIT], check=False)
        journal = subprocess.run(["journalctl", "--user", "-u", UNIT, "--no-pager", "-o", "cat"], capture_output=True, text=True).stdout
        (OUT / "sglang-server.log").write_text(journal)


if __name__ == "__main__":
    main()
