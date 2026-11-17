#!/usr/bin/env python3
"""Download the pinned FastH3 Omni checkpoint and verify files without loading models."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "models/FastH3-Omni-NVFP4-QAD.download-manifest.json"
REPORT = ROOT / "models/FastH3-Omni-NVFP4-QAD.verification.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    manifest = json.loads(MANIFEST.read_text())
    destination = Path(manifest["destination"])
    destination.mkdir(parents=True, exist_ok=True)
    reused = []
    verified_hashes = {}
    download_paths = [item["path"] for item in manifest["download_files"]]

    for entry in manifest["reuse_candidates"]:
        source = Path(entry["source"])
        print(f"Verifying reusable file: {entry['path']}", flush=True)
        if source.stat().st_size != entry["size"] or sha256_file(source) != entry["sha256"]:
            print(f"Local hash differs; downloading official file: {entry['path']}", flush=True)
            download_paths.append(entry["path"])
            continue
        target = destination / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            os.link(source, target)
        if not os.path.samefile(source, target):
            # A previous download may have produced a separate, valid copy.
            if target.stat().st_size != entry["size"] or sha256_file(target) != entry["sha256"]:
                raise RuntimeError(f"Existing file differs: {target}")
        verified_hashes[entry["path"]] = entry["sha256"]
        reused.append(entry["path"])

    print(f"Reused {len(reused)} verified files. Downloading pinned revision {manifest['revision']}.", flush=True)
    snapshot_download(
        repo_id=manifest["repository"],
        revision=manifest["revision"],
        local_dir=str(destination),
        allow_patterns=download_paths,
        max_workers=8,
    )

    # Both official directories contain the same tensors. Keep their layouts
    # available while storing the large weights only once.
    alias = destination / "transformer"
    if not alias.exists():
        alias.symlink_to("transformer_ref", target_is_directory=True)
    if alias.resolve() != (destination / "transformer_ref").resolve():
        raise RuntimeError("Unexpected transformer alias; refusing to overwrite it")

    print("Download finished. Verifying official sizes and SHA-256 hashes.", flush=True)

    def verify(entry):
        path = destination / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise RuntimeError(f"Missing or incomplete file: {path}")
        digest = verified_hashes.get(entry["path"]) or sha256_file(path)
        if entry.get("sha256") and digest != entry["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch: {path}")
        print(f"Verified: {entry['path']}", flush=True)
        return {"path": entry["path"], "size": entry["size"], "sha256": digest,
                "official_lfs_hash_checked": bool(entry.get("sha256"))}

    with ThreadPoolExecutor(max_workers=2) as pool:
        verified = list(pool.map(verify, manifest["files"]))

    # Check the sharded-weight indexes without deserializing any tensors.
    for index_path in destination.rglob("*.safetensors.index.json"):
        index = json.loads(index_path.read_text())
        for filename in set(index["weight_map"].values()):
            if not (index_path.parent / filename).is_file():
                raise RuntimeError(f"Missing indexed shard: {index_path.parent / filename}")
    contract = json.loads((destination / "fastvideo_inference.json").read_text())
    if contract.get("model_type") != "ref2va" or contract.get("transformer_component") != "transformer_ref":
        raise RuntimeError("Downloaded checkpoint is not the expected Ref2VA model")

    report = {
        "status": "verified",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": manifest["repository"],
        "revision": manifest["revision"],
        "destination": str(destination),
        "unique_component_bytes": sum(item["size"] for item in verified),
        "reused_files": reused,
        "aliases": manifest["aliases"],
        "files": verified,
        "validation_scope": "Files, official LFS SHA-256, shard indexes, and JSON metadata only.",
        "model_loaded": False,
        "inference_run": False,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Complete: {destination}", flush=True)
    print(f"Verification report: {REPORT}", flush=True)


if __name__ == "__main__":
    main()
