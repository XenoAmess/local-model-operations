#!/usr/bin/env python3
"""Wait for the existing Base download, then download the local IC refiner; never launch inference."""

import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    base_manifest = json.loads((ROOT / "deployment/minimax-h3/download-manifest.json").read_text())
    report_path = ROOT / "deployment/minimax-h3/weight-verification.json"
    while True:
        result = subprocess.run(
            ["systemctl", "--user", "show", "llmlab-minimax-h3-download-20261116.service",
             "-p", "ActiveState", "-p", "Result"], capture_output=True, text=True, check=True)
        properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if properties.get("ActiveState") == "failed" or properties.get("Result", "success") != "success":
            raise RuntimeError("Base download failed; preserve files and inspect its log before resuming")
        verified = False
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
                verified = (report.get("status") == "verified"
                            and report.get("revision") == base_manifest["revision"]
                            and len(report.get("files", [])) == len(base_manifest["files"]))
            except (OSError, ValueError):
                pass
        if verified and properties.get("ActiveState") not in {"active", "activating", "deactivating"}:
            break
        time.sleep(10)
    print("Base download verified; starting the queued, isolated local 2K weight download", flush=True)
    subprocess.run([
        "/usr/bin/python3", str(ROOT / "llm-lab/scripts/run_isolated.py"),
        "--unit", "llmlab-open-h3-2k-download-20261116", "--memory-gib", "6", "--wait", "--",
        str(ROOT / "FastVideo/.venv/bin/python"), str(ROOT / "tools/download_minimax_h3.py"),
        "--manifest", "deployment/minimax-h3/open-2k-download-manifest.json",
        "--report", "deployment/minimax-h3/open-2k-weight-verification.json",
    ], check=True)


if __name__ == "__main__":
    main()
