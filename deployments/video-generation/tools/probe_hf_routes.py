#!/usr/bin/env python3
"""Bounded, sequential byte-range checks for the pinned public checkpoint."""

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    import requests
    manifest = json.loads((ROOT / "deployment/omni-bf16/export-download-manifest.json").read_text())
    entry = next(f for f in manifest["files"] if f["size"] > 1024**3)
    results = []
    size = 4 * 1024**2
    for host, proxy in [("huggingface.co", True), ("huggingface.co", False),
                        ("hf-mirror.com", True), ("hf-mirror.com", False)]:
        session = requests.Session()
        session.trust_env = proxy
        item = {"host": host, "proxy": proxy}
        url = f"https://{host}/{manifest['repository']}/resolve/{manifest['revision']}/{entry['path']}"
        started = time.monotonic()
        try:
            with session.get(url, headers={"Range": f"bytes=0-{size - 1}", "Accept-Encoding": "identity"},
                             timeout=(8, 20), stream=True) as response:
                item["status"] = response.status_code
                if response.status_code == 206 and response.headers.get("Content-Range", "").startswith("bytes 0-"):
                    data = response.raw.read(size + 1)
                    item["bytes"] = len(data)
                    item["mib_s"] = round(len(data) / 1024**2 / (time.monotonic() - started), 3)
                else:
                    item["range_rejected"] = True
        except Exception as error:
            item["error"] = type(error).__name__
        item["seconds"] = round(time.monotonic() - started, 2)
        results.append(item)
        print(json.dumps(item), flush=True)
    (ROOT / "deployment/omni-bf16/download-route-probe.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
