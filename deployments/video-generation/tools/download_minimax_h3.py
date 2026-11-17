#!/usr/bin/env python3
"""Download the pinned official BF16 Ref2VA components with two bounded lanes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
from resource_guard import require_isolation


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    isolation = require_isolation()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="deployment/minimax-h3/download-manifest.json")
    parser.add_argument("--report", default="deployment/minimax-h3/weight-verification.json")
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_XET_HIGH_PERFORMANCE"] = "0"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "120"
    from huggingface_hub import hf_hub_download

    manifest = json.loads((ROOT / args.manifest).read_text())
    destination = ROOT / manifest["destination"]
    destination.mkdir(parents=True, exist_ok=True)

    def fetch(entry):
        target = destination / entry["path"]
        expected = entry.get("sha256")
        reuse = ROOT / entry["reuse_source"] if entry.get("reuse_source") else None
        if not target.exists() and reuse and reuse.is_file():
            if reuse.stat().st_size == entry["size"] and digest(reuse) == expected:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(reuse, target)
                print("Reused " + entry["path"], flush=True)
        if not target.is_file() or target.stat().st_size != entry["size"]:
            print("Downloading " + entry["path"], flush=True)
            for attempt in range(5):
                try:
                    hf_hub_download(repo_id=manifest["repository"], revision=manifest["revision"],
                                    filename=entry["path"], local_dir=str(destination))
                    break
                except Exception as error:
                    print(f"Retry {attempt + 1}: {entry['path']} ({type(error).__name__})", flush=True)
                    if attempt == 4:
                        raise
                    time.sleep(min(30, 2 ** attempt))
        if target.stat().st_size != entry["size"]:
            raise RuntimeError("Incorrect file size: " + str(target))
        actual = digest(target)
        if expected and actual != expected:
            raise RuntimeError("SHA-256 mismatch: " + str(target))
        print("Verified " + entry["path"], flush=True)
        return {"path": entry["path"], "size": target.stat().st_size, "sha256": actual,
                "official_lfs_hash_checked": bool(expected)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        verified = list(pool.map(fetch, manifest["files"]))
    for entry in manifest.get("tensor_ranges", []):
        fetch_tensor_range(entry, destination)
    for index_path in destination.rglob("*.safetensors.index.json"):
        for shard in set(json.loads(index_path.read_text())["weight_map"].values()):
            if not (index_path.parent / shard).is_file():
                raise RuntimeError("Missing indexed shard: " + shard)
    report = {"status": "verified", "completed_at": datetime.now(timezone.utc).isoformat(),
              "repository": manifest["repository"], "revision": manifest["revision"],
              "files": verified, "isolation": isolation, "inference_run": False}
    report["tensor_ranges"] = manifest.get("tensor_ranges", [])
    (ROOT / args.report).write_text(
        json.dumps(report, indent=2) + "\n")
    print("All pinned checkpoint components verified", flush=True)


def fetch_tensor_range(entry, destination):
    """Fetch one small safetensors tensor without downloading its large source checkpoint."""
    import requests
    from huggingface_hub import hf_hub_url

    target = destination / entry["destination"]
    if target.is_file() and digest(target) == entry["sha256"]:
        return
    url = hf_hub_url(entry["repository"], entry["file"], revision=entry["revision"])

    def read_range(start, size):
        headers = {"Range": f"bytes={start}-{start + size - 1}", "Accept-Encoding": "identity"}
        with requests.get(url, headers=headers, stream=True, timeout=120) as response:
            if response.status_code != 206:
                raise RuntimeError("Server ignored byte range; refusing full checkpoint download")
            if not response.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                raise RuntimeError("Unexpected byte range response")
            data = response.raw.read(size + 1)
        if len(data) != size:
            raise RuntimeError("Truncated or oversized byte range response")
        return data

    header_size, = struct.unpack("<Q", read_range(0, 8))
    if not 0 < header_size < 16 * 1024 * 1024:
        raise RuntimeError("Invalid safetensors header size")
    tensor = json.loads(read_range(8, header_size))[entry["tensor"]]
    if tensor["dtype"] != "F32" or tensor["shape"] != [1025, 8]:
        raise RuntimeError("Unexpected Sharp timestep curve shape or dtype")
    start, end = tensor["data_offsets"]
    if end - start != 1025 * 8 * 4:
        raise RuntimeError("Unexpected Sharp timestep curve length")
    data = read_range(8 + header_size + start, end - start)
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise RuntimeError("Sharp timestep curve SHA-256 mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    print("Verified tensor range " + entry["destination"], flush=True)


if __name__ == "__main__":
    main()
