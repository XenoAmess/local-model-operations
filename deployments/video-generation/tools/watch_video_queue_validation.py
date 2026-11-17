#!/usr/bin/env python3
"""Finish the already-submitted validation receipt; never submit, restart or stop models."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = json.loads(args.run.read_text())
    output = args.run.parent
    client = requests.Session()
    client.trust_env = False
    report_path = ROOT / "deployment/video-queue/validation.json"
    while True:
        try:
            statuses = []
            for job in run["requested_submission_order"]:
                response = client.get(job["api"] + "/v1/videos/" + job["id"], timeout=15)
                response.raise_for_status()
                statuses.append(response.json())
            if all(job["status"] in {"completed", "failed", "cancelled"} for job in statuses):
                break
            if any(job["status"] == "failed" for job in statuses):
                break
        except requests.RequestException:
            # An operator may stop either HTTP frontend. This watcher never restarts it.
            pass
        time.sleep(25)
    report = json.loads(report_path.read_text())
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["jobs"] = [{key: job.get(key) for key in ("id", "model", "status", "error")} for job in statuses]
    try:
        if not all(job["status"] == "completed" for job in statuses):
            raise RuntimeError("A long GPU validation task failed or was cancelled; inspect retained task logs")
        verified = []
        for submitted, status in zip(run["requested_submission_order"], statuses):
            path = output / (status["id"] + ".mp4")
            digest = hashlib.sha256()
            with client.get(submitted["api"] + "/v1/videos/" + status["id"] + "/content",
                            stream=True, timeout=180) as response:
                response.raise_for_status()
                with path.open("wb") as stream:
                    for block in response.iter_content(1024 * 1024):
                        stream.write(block)
                        digest.update(block)
            if digest.hexdigest() != status["result"]["sha256"]:
                raise RuntimeError("LAN download checksum differs from server receipt")
            metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration,size", "-of", "json", str(path)], text=True))
            video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
            expected = (832, 480) if submitted["kind"] == "omni" else (2560, 1440)
            if (video["width"], video["height"]) != expected or int(video["nb_frames"]) != 124:
                raise RuntimeError("Unexpected dimensions or frame count")
            if video["r_frame_rate"] != "24/1" or not any(s["codec_type"] == "audio" for s in metadata["streams"]):
                raise RuntimeError("Unexpected frame rate or missing audio")
            verified.append({"id": status["id"], "model": status["model"], "sha256": digest.hexdigest(),
                             "probe": metadata, "result": status["result"]})
        db = sqlite3.connect(ROOT / "outputs/video-queue/queue.sqlite3")
        units = [db.execute("SELECT unit FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
                 for job in statuses if job["model"] == "open-h3-2k"]
        events = [{"time": row[0], "detail": json.loads(row[1])} for row in
                  db.execute("SELECT created,detail FROM events WHERE event='dispatch' ORDER BY sequence")]
        db.close()
        if len(set(units)) != 1:
            raise RuntimeError("The two 2K jobs were not dispatched in one cohort")
        batch = ROOT / "outputs/video-queue/batches" / units[0].removesuffix(".service")
        log = (batch / "worker.log").read_text()
        if "encoded 2 draft(s)" not in log or log.count("model ready in") != 1:
            raise RuntimeError("Missing evidence of two-clip component reuse")
        report.update(status="gpu_validation_completed_lan_download_and_batch_reuse_verified",
                      outputs=verified, dispatch_events=events, two_2k_jobs_share_one_worker=True,
                      two_2k_windows_share_one_dit_load=True,
                      batch_resources=json.loads((batch / "resources.json").read_text()),
                      visual_quality_ranking="Not evaluated; these checks verify transport, batching, dimensions, frames and audio")
    except Exception as error:
        report.update(status="long_gpu_validation_failed_evidence_preserved", error=type(error).__name__ + ": " + str(error))
    atomic_json(report_path, report)
    atomic_json(output / "verification.json", report)
    subprocess.run(["/usr/bin/python3", str(ROOT / "tools/package_video_http_client.py")], check=True)
    print(json.dumps({"status": report["status"], "report": str(report_path)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
