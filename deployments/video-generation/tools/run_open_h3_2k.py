#!/usr/bin/env python3
"""Manual isolated local 2K regeneration with the same bounded worker as the HTTP service."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil

from h3_refiner_profiles import PROFILES

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--caption-file", type=Path, required=True)
    parser.add_argument("--sampler", choices=["up3", "up4", "hf8"], default="up3")
    parser.add_argument("--size", choices=list(PROFILES), default="2560x1440")
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    for name in ["fasth3-omni.service", "fasth3-omni-bf16-worker.service", "fasth3-v2.service", "qwen38-coder.service", "minimax-h3.service", "h3-2k-http.service"]:
        state = subprocess.run(["systemctl", "--user", "is-active", name], capture_output=True, text=True)
        if state.stdout.strip() in {"active", "activating"}:
            raise SystemExit(f"GPU model {name} is active; this entry will not stop or switch it")
    manifest = json.loads((ROOT / "deployment/minimax-h3/open-2k-download-manifest.json").read_text())
    report = json.loads((ROOT / "deployment/minimax-h3/open-2k-weight-verification.json").read_text())
    if (report.get("status") != "verified" or report.get("revision") != manifest["revision"]
            or len(report.get("files", [])) != len(manifest["files"])):
        raise SystemExit("The local 2K weight bundle has not been completely verified")
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false",
                       "MAX_JOBS": "2", "FLASHINFER_NVCC_THREADS": "1", "NVCC_THREADS": "1",
                       "TORCHINDUCTOR_COMPILE_THREADS": "1"})
    folder = args.output.resolve().parent / ("." + args.output.stem + ".h3-2k")
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"model": "minimax-h3-2k", "mode": "regenerate", "input_video": str(args.input.resolve()),
               "prompt": args.caption_file.read_text(), "size": args.size, "seed": args.seed, "sampler": args.sampler}
    request = folder / "request.json"
    if request.exists() and json.loads(request.read_text()) != payload:
        raise SystemExit("This output already has another request checkpoint; choose a new output path")
    request.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    with (ROOT / "outputs/h3-2k-gpu.lock").open("a") as gpu_lease:
        fcntl.flock(gpu_lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from h3_2k_worker import process
        process(folder)
        shutil.copyfile(folder / "result.mp4", args.output.resolve())


if __name__ == "__main__":
    main()
