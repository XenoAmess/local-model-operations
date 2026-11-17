#!/usr/bin/env python3
"""Acquire the shared GPU lease for one bounded real-input IC parity check."""

import argparse
import fcntl
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lock = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise SystemExit("GPU is busy; real-input parity check must wait")
    return subprocess.call([sys.executable, str(ROOT / "tools/h3_ic_runtime.py"),
        "--jobs", str(args.jobs.resolve()), "--size", "3840x2160", "--sampler", "up3", "--seed", "1234",
        "--exact-io", "--verify-first-block", str(args.report.resolve())])


if __name__ == "__main__":
    raise SystemExit(main())
