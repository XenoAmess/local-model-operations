#!/usr/bin/env python3
"""Reuse local BF16 weights with the pinned SGLang overlay's layout converters.

Uses two reviewed upstream materializers. No model download, no edits to the
source checkpoints, and no claim of bitwise equivalence across fused PDD heads.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/framework-comparison-20261117"


def module(path, name, digest):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Unexpected upstream helper bytes: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def links(source, target):
    """Link files into new real directories; mutable metadata is replaced later."""
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(path.resolve())


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    import torch
    torch.set_num_threads(4)
    source = ROOT / "models/FastH3-Omni-BF16"
    target = OUT / "FastH3-Omni-BF16-native-candidate"
    if target.exists():
        raise RuntimeError("Refusing to overwrite an existing candidate checkpoint")
    target.mkdir()
    v2 = module(OUT / "sglang-v2-materialize.py", "reviewed_v2_overlay",
                "c8d7dd538ceb768f98ba5410ec4bc12de3ae1ed3d43977755b68aab0999ec6af")
    omni = module(OUT / "sglang-overlay/_overlay/materialize.py", "reviewed_omni_overlay",
                  "8540879c1bd7dfeae0d978d79ff468794bc2a60baeeb0cb5bafa9f565c488d24")
    report = dict(started=time.time(), source=str(source), target=str(target),
                  no_model_download=True, source_checkpoints_modified=False,
                  pdd_head_fusion_changes_fp_rounding=True)
    for component in ("text_encoder", "tokenizer", "processor", "audio_vae"):
        links(source / component, target / component)
    links(source / "transformer_ref", target / "transformer")
    shutil.copyfile(OUT / "sglang-overlay/model_index.json", target / "model_index.json")
    shutil.copyfile(source / "fastvideo_inference.json", target / "fastvideo_inference.json")
    print("Converting original 36-layer FP32 video VAE layout", flush=True)
    v2._convert_video_vae(source_dir=str(source), output_dir=str(target))
    for component, source_name, class_name in (
        ("video_vae", "vae", "MiniMaxH3VideoVAE"),
        ("audio_vae", "audio_vae", "MiniMaxH3AudioVAE"),
    ):
        v2._write_patched_component_config(source_path=str(source / source_name / "config.json"),
            target_path=str(target / component / "config.json"), class_name=class_name)
    contract = omni._read_contract(str(source))
    pdd_steps = omni._write_transformer_config(str(target))
    omni._write_rope_inv_freq(source_dir=str(source), output_dir=str(target))
    print("Preparing native 8-step PDD heads", flush=True)
    omni._fuse_pdd_heads(contract=contract, pdd_steps=pdd_steps, output_dir=str(target))
    report.update(status="materialized_not_inference_validated", finished=time.time())
    (OUT / "sglang-checkpoint-preparation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
