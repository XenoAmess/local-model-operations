#!/usr/bin/env python3
"""Resume two-lane verified downloads, then compose the official BF16 Omni stack."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    from download_minimax_h3 import main as download
    for kind in ["export", "base"]:
        if kind == "base":
            from reuse_omni_bf16_metadata import main as reuse_metadata
            reuse_metadata()
        sys.argv = ["download_minimax_h3.py", "--manifest", f"deployment/omni-bf16/{kind}-download-manifest.json",
                    "--report", f"deployment/omni-bf16/{kind}-weight-verification.json"]
        download()
    export = ROOT / "models/FastH3-Omni-BF16-Export"
    base = ROOT / "models/FastH3-Omni-BF16-Base"
    destination = ROOT / "models/FastH3-Omni-BF16"
    destination.mkdir(exist_ok=True)
    links = {name: export / name for name in ["transformer_ref", "scheduler", "audio_scheduler",
                                             "fastvideo_inference.json", "modular_model_index.json"]}
    links.update({name: base / name for name in ["text_encoder", "tokenizer", "processor", "vae", "audio_vae"]})
    for name, source in links.items():
        target = destination / name
        if target.is_symlink() and target.resolve() == source.resolve():
            continue
        if target.exists() or target.is_symlink():
            raise RuntimeError(f"Refusing to replace existing composed component {name}")
        target.symlink_to(source.resolve(), target_is_directory=source.is_dir())
    report = {"status": "composed", "directory": str(destination),
              "transformer_quantized": False, "components": {name: str(path) for name, path in links.items()}}
    (ROOT / "deployment/omni-bf16/composition.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Official BF16 Omni stack composed and verified", flush=True)


if __name__ == "__main__":
    main()
