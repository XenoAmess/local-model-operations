#!/usr/bin/env python3
"""Observe one already-submitted native-4K job and verify its actual LAN output."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = json.loads(args.run.read_text())
    output = args.run.parent
    report_path = ROOT / "deployment/video-queue/4k-validation.json"
    client = requests.Session()
    client.trust_env = False
    peak_gpu = 0
    # An observer restart must not discard earlier samples or affect the GPU job.
    monitor = output / "monitor.jsonl"
    if monitor.exists():
        for line in monitor.read_text().splitlines():
            try:
                previous = json.loads(line)
                if previous["job"]["status"] == "in_progress" and previous.get("gpu"):
                    peak_gpu = max(peak_gpu, int(previous["gpu"].split(",")[0]))
            except (KeyError, ValueError):
                pass
    with monitor.open("a") as log:
        while True:
            try:
                response = client.get(run["api"] + "/v1/videos/" + run["id"], timeout=15)
                response.raise_for_status()
                job = response.json()
                gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu,power.draw",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
                if job["status"] == "in_progress" and gpu:
                    peak_gpu = max(peak_gpu, int(gpu.split(",")[0]))
                log.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "job": job, "gpu": gpu}) + "\n")
                log.flush()
                save(output / "job-status.json", job)
                if job["status"] in {"completed", "failed", "cancelled"}:
                    break
            except requests.RequestException:
                pass
            time.sleep(20)
    report = json.loads(report_path.read_text())
    report.update(finished_at=datetime.now(timezone.utc).isoformat(), terminal_job_status=job["status"],
                  sampled_gpu_peak_mib=peak_gpu, sample_interval_seconds=20)
    try:
        if job["status"] != "completed":
            raise RuntimeError(str(job.get("error") or job["status"]))
        path = output / "result-lan.mp4"
        with client.get(run["api"] + "/v1/videos/" + run["id"] + "/content", stream=True, timeout=300) as response:
            response.raise_for_status()
            with path.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    stream.write(block)
        metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration,size", "-of", "json", str(path)], text=True))
        video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
        if (video["width"], video["height"], int(video["nb_frames"])) != (3840, 2160, 124):
            raise RuntimeError("The result is not the requested native 4K / 124-frame video")
        if video["r_frame_rate"] != "24/1" or not any(s["codec_type"] == "audio" for s in metadata["streams"]):
            raise RuntimeError("Wrong frame rate or missing audio")
        digest = digest_file(path)
        if digest != job["result"]["sha256"]:
            raise RuntimeError("LAN download SHA-256 does not match server receipt")
        with sqlite3.connect(ROOT / "outputs/video-queue/queue.sqlite3") as db:
            folder, unit, created, updated = db.execute("SELECT directory,unit,created,updated FROM jobs WHERE id=?",
                                                      (run["id"],)).fetchone()
        folder = Path(folder)
        batch = ROOT / "outputs/video-queue/batches" / unit.removesuffix(".service")
        worker_log = (batch / "worker.log").read_text()
        if "IC native target 3840x2160: compute 3840x2176" not in worker_log:
            raise RuntimeError("Missing native 4K route evidence")
        latent = folder / "window-00-4k.latent.pt"
        if not latent.exists():
            raise RuntimeError("Missing 4K denoised-latent checkpoint")
        # Validate actual media decoding, not just container metadata. CPU only,
        # isolated from the API and bounded by the same workload launcher.
        def media_check(suffix, command):
            subprocess.run(["/usr/bin/python3", str(ROOT / "llm-lab/scripts/run_isolated.py"),
                            "--unit", f"llmlab-4k-{suffix}-{run['id'][-10:]}",
                            "--memory-gib", "2", "--wait", "--", *command], check=True)

        media_check("decode-check", ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2",
                    "-i", str(path), "-map", "0", "-f", "null", "-"])
        contact = output / "contact-sheet.png"
        media_check("contact-sheet", ["ffmpeg", "-nostdin", "-y", "-v", "error", "-threads", "2",
                    "-i", str(path), "-vf", "select=eq(n\\,0)+eq(n\\,60)+eq(n\\,123),scale=640:-1,tile=3x1",
                    "-filter_threads", "2", "-frames:v", "1", "-threads", "2", str(contact)])
        sampling = re.findall(r"up3: 3 steps in ([\d.]+) s", worker_log)
        decoding = re.findall(r"H3 VAE decode (\d+) s", worker_log)
        report.update(status="native_4k_generation_and_lan_download_verified", sha256=digest,
                      ffprobe=metadata, result=job["result"], submitted_to_completed_s=updated - created,
                      denoise_s=float(sampling[-1]) if sampling else None,
                      decode_s=float(decoding[-1]) if decoding else None,
                      latent_checkpoint={"path": str(latent), "bytes": latent.stat().st_size, "sha256": digest_file(latent)},
                      resources=json.loads((batch / "resources.json").read_text()),
                      submitted_at=datetime.fromtimestamp(created, timezone.utc).isoformat(),
                      complete_video_audio_decode_verified=True,
                      contact_sheet=str(contact),
                      visual_check="Contact sheet prepared; human inspection pending; no comparative quality claim",
                      tested_duration_seconds=124 / 24, longer_4k_clips_validated=False,
                      download_url=run["api"] + "/v1/videos/" + run["id"] + "/content")
    except Exception as error:
        report.update(status="4k_validation_failed_evidence_preserved", error=type(error).__name__ + ": " + str(error))
    save(report_path, report)
    save(output / "verification.json", report)
    subprocess.run(["/usr/bin/python3", str(ROOT / "tools/package_video_http_client.py")], check=True)
    print(json.dumps({"status": report["status"], "report": str(report_path)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
