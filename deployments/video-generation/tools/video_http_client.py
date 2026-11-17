#!/usr/bin/env python3
"""Upload local references and submit BF16 Omni or local 2K tasks from another machine."""

import argparse
import json
from pathlib import Path
import sys
import time

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["omni", "2k"])
    parser.add_argument("--api", help="API root, e.g. http://192.168.1.11:8001")
    parser.add_argument("--image", action="append", type=Path, default=[])
    parser.add_argument("--video", action="append", type=Path, default=[])
    parser.add_argument("--audio", action="append", type=Path, default=[])
    parser.add_argument("--source-job", help="2K only: depend on an existing queued or completed Omni task")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--size", help="Refiner: 2560x1440, 1440x2560 or native 4K 3840x2160")
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--sampler", choices=["up3", "up4", "hf8"], default="up3")
    parser.add_argument("--wait", action="store_true", help="Poll until completion; otherwise return the task immediately")
    parser.add_argument("--output", type=Path, default=Path("result.mp4"))
    args = parser.parse_args()
    if args.kind == "2k" and (args.image or args.audio or (bool(args.source_job) == bool(args.video)) or len(args.video) > 1):
        parser.error("2k needs exactly one --video or --source-job, and accepts no image/audio references")
    if args.kind == "omni" and (not (args.image or args.video) or not args.prompt.strip() or args.source_job):
        parser.error("omni needs a prompt plus image/video references; --source-job is for 2k")
    api = (args.api or f"http://192.168.1.11:{8001 if args.kind == 'omni' else 8002}").rstrip("/")
    client = requests.Session()
    client.trust_env = False

    def check(response):
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1600]}")
        return response.json()

    def upload(path):
        with path.open("rb") as stream:
            result = check(client.post(api + "/v1/files", files={"file": (path.name, stream)}, timeout=300))
        return {"file_id": result["id"]}

    payload = {"prompt": args.prompt, "seed": args.seed}
    if args.kind == "omni":
        payload.update(model="fasth3-omni-bf16", task="ref2va", seconds=args.seconds,
                       size=args.size or "1344x768", num_inference_steps=8)
        for kind, paths in [("image", args.image), ("video", args.video), ("audio", args.audio)]:
            if paths:
                payload[kind + "_reference"] = [upload(path) for path in paths]
        endpoint = "/v1/videos"
    else:
        payload.update(model="open-h3-2k", size=args.size or "2560x1440", sampler=args.sampler,
                       input_video={"job_id": args.source_job} if args.source_job else upload(args.video[0]))
        endpoint = "/v1/videos/regenerations"
    job = check(client.post(api + endpoint, json=payload, timeout=90))
    print(json.dumps(job, ensure_ascii=False), flush=True)
    if not args.wait:
        return
    while job["status"] in {"queued", "in_progress"}:
        print(f"{job['id']}: {job['status']} {job.get('stage', '')}", file=sys.stderr, flush=True)
        time.sleep(5)
        job = check(client.get(api + "/v1/videos/" + job["id"], timeout=30))
    if job["status"] != "completed":
        raise RuntimeError(json.dumps(job.get("error") or job, ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with client.get(api + "/v1/videos/" + job["id"] + "/content", stream=True, timeout=300) as response:
        response.raise_for_status()
        with args.output.open("wb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)
    print(json.dumps({"job": job["id"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
