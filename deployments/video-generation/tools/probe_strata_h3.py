#!/usr/bin/env python3
"""Build and try the two distinct Strata projects against local H3 weights."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/framework-comparison-20261117"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("niko-import", "ro99-build", "ro99-admission"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    ro99 = args.action.startswith("ro99")
    source = ROOT / "tools/vendor" / ("strata-ro99-candidate" if ro99 else "strata-candidate")
    env = os.environ.copy()
    env.update(CUDA_HOME=str(ROOT / "tools/cuda"), CUDA_VISIBLE_DEVICES="", STRATA_PYTHON=sys.executable)
    env["PATH"] = str(ROOT / "FastVideo/.venv/bin") + ":" + str(ROOT / "tools/cuda/bin") + ":" + env["PATH"]
    # Keep every candidate's mutable application state out of user settings.
    for kind in ("CACHE", "CONFIG", "DATA", "STATE"):
        env[f"XDG_{kind}_HOME"] = str(OUT / "strata-private-state" / kind.lower())
    report = dict(action=args.action, started=time.time(), runs=[],
                  source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
                  scope="H3 model import/admission, not inference timing", production_changed=False)
    if args.action == "ro99-build":
        build = source / "build-codex"
        commands = [[str(ROOT / "FastVideo/.venv/bin/cmake"), "-S", str(source), "-B", str(build),
                     "-DCMAKE_BUILD_TYPE=Release", "-DSTRATA_ENABLE_CUDA=ON",
                     "-DCMAKE_CXX_FLAGS=-fno-thread-jumps",
                     "-DCMAKE_CUDA_COMPILER=" + str(ROOT / "tools/cuda/bin/nvcc"),
                     "-DCUDAToolkit_ROOT=" + str(ROOT / "tools/cuda"),
                     "-DCMAKE_CUDA_FLAGS=-I" + str(source / "build-toolchain/nvidia/cu13/include")],
                    [str(ROOT / "FastVideo/.venv/bin/cmake"), "--build", str(build),
                     "--target", "strata-chat", "strata-server", "--parallel", "2"]]
    elif args.action == "niko-import":
        cli = str(source / "bin/strata")
        commands = [[cli, "models", "import", str(ROOT / "models" / model), "--plan", "--output", "json"]
                    for model in ("FastH3-Omni-BF16", "Open-H3-Regenerate-2K-IC")]
        commands.append([cli, "launch", "--family", "minimax-h3", "--model", str(ROOT / "models/FastH3-Omni-BF16"),
                         "--plan", "--output", "json"])
    else:
        commands = [[str(source / "build-codex" / binary), "--model", str(ROOT / "models" / model),
                     "--model-type", "minimax-h3", "--devices", "0", "--dry-run"]
                    for binary, model in (("strata-chat", "FastH3-Omni-BF16"),
                                           ("strata-server", "Open-H3-Regenerate-2K-IC"))]
    try:
        for index, command in enumerate(commands):
            started = time.monotonic()
            log = OUT / f"strata-{args.action}-{index}.log"
            with log.open("w") as stream:
                run = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1500)
            row = dict(command=[v.replace(str(ROOT), "$VIDEO_ROOT") for v in command], returncode=run.returncode,
                       wall_s=time.monotonic()-started, log=log.name)
            if args.action != "ro99-build":
                row["response"] = log.read_text().replace(str(ROOT), "$VIDEO_ROOT")[:12000]
            report["runs"].append(row)
            print(json.dumps(row), flush=True)
            if args.action == "ro99-build" and run.returncode:
                raise RuntimeError("Build failed; inspect " + str(log))
        report["status"] = "build_completed" if args.action == "ro99-build" else "attempts_recorded"
    finally:
        report["finished"] = time.time()
        (OUT / f"strata-{args.action}.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
