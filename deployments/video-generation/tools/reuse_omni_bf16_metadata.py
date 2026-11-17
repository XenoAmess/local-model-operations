#!/usr/bin/env python3
"""Reuse small pinned base files only after matching their publisher Git blob IDs."""

import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    manifest = json.loads((ROOT / "deployment/omni-bf16/base-download-manifest.json").read_text())
    reused = []
    for entry in manifest["files"]:
        if not entry.get("git_blob_id") or not entry.get("reuse_source"):
            continue
        source = ROOT / entry["reuse_source"]
        content = source.read_bytes()
        blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        if blob != entry["git_blob_id"] or len(content) != entry["size"]:
            continue
        target = ROOT / manifest["destination"] / entry["path"]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, target)
        reused.append({"path": entry["path"], "git_blob_id": blob,
                       "sha256": hashlib.sha256(content).hexdigest()})
    (ROOT / "deployment/omni-bf16/base-metadata-reuse.json").write_text(json.dumps(reused, indent=2) + "\n")
    print(f"Reused {len(reused)} metadata files matching the pinned publisher Git blob IDs")


if __name__ == "__main__":
    main()
