#!/usr/bin/env python3
"""Run the pinned IC refiner with lossless intermediates and bounded single-GPU placement."""

import argparse
from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types

from h3_refiner_profiles import PROFILES, get_profile

ROOT = Path(__file__).resolve().parents[1]


def chunk_forward(original, size=2048):
    def forward(hidden_states, *args, **kwargs):
        import torch
        if hidden_states.shape[1] <= size:
            return original(hidden_states, *args, **kwargs)
        return torch.cat([original(part, *args, **kwargs) for part in hidden_states.split(size, dim=1)], dim=1)
    return forward


def block_offload(model, device):
    """Keep complete weights on the host; transfer one block for its exact forward."""
    import torch
    for name, module in model.named_children():
        if name != "transformer_blocks":
            module.to(device)
    step = {"number": 0}

    def begin(module, args, kwargs):
        step["number"] += 1
        print(f"IC denoising step {step['number']} started", flush=True)

    model.register_forward_pre_hook(begin, with_kwargs=True)
    for index, block in enumerate(model.transformer_blocks):
        def onload(module, args, block_index=index):
            if block_index % 10 == 0:
                print(f"IC step {step['number']}: block {block_index + 1}/50", flush=True)
            module.to(device)

        def unload(module, args, output):
            module.to("cpu")

        block.register_forward_pre_hook(onload)
        block.register_forward_hook(unload, always_call=True)
    gc.collect()
    import ctypes
    ctypes.CDLL(None).malloc_trim(0)
    torch.cuda.empty_cache()
    print("IC placement: full BF16 base and full IC LoRA; CPU block offload, FFN chunks 2048", flush=True)
    return model


def lossless_write(frames, path, audio_from=None, crf=12):
    """Write an intermediate without introducing another H.264 compression pass."""
    import numpy as np
    count, height, width, _ = frames.shape
    command = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{width}x{height}", "-r", "24", "-i", "-", "-an", "-c:v", "ffv1",
               "-level", "3", "-threads", "2", str(path)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in frames:
            process.stdin.write(np.ascontiguousarray(frame).tobytes())
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Lossless intermediate encoding failed")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--portrait", action="store_true")
    parser.add_argument("--size", choices=list(PROFILES), help="Native target size; legacy --portrait remains supported")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--sampler", choices=["up3", "up4", "hf8"], default="up3")
    parser.add_argument("--save-latent", action="store_true", help="Save the normalized latent for full-video comparisons")
    parser.add_argument("--exact-io", action="store_true", default=os.environ.get("H3_IC_EXACT_IO") == "1",
                        help="Use validated immutable weight storage, cached LoRA casts and bounded FFN output storage")
    parser.add_argument("--verify-first-block", type=Path,
                        help="Standalone diagnostic: compare actual first-block output to original math, write JSON, stop without video")
    args = parser.parse_args()
    if args.verify_first_block and not args.exact_io:
        parser.error("--verify-first-block requires --exact-io")
    size = args.size or ("1440x2560" if args.portrait else "2560x1440")
    if args.portrait and size != "1440x2560":
        parser.error("--portrait cannot be combined with a different --size")
    profile = get_profile(size)
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    for name in ["fasth3-omni.service", "fasth3-omni-bf16-worker.service", "fasth3-v2.service", "qwen38-coder.service", "minimax-h3.service"]:
        status = subprocess.run(["systemctl", "--user", "is-active", name], capture_output=True, text=True)
        if status.stdout.strip() in {"active", "activating"}:
            raise SystemExit(f"Cannot start the refiner while {name} is active")
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
    import torch
    from diffusers import MiniMaxH3Transformer3DModel
    from diffusers.models.attention import FeedForward

    torch.set_num_threads(8)
    original_ff = FeedForward.forward
    bounded_forward = chunk_forward
    if args.exact_io:
        from h3_ic_exact import chunk_forward_preallocated
        bounded_forward = chunk_forward_preallocated

    def chunked_ff(self, hidden_states, *ff_args, **ff_kwargs):
        return bounded_forward(lambda part: original_ff(self, part, *ff_args, **ff_kwargs))(hidden_states)

    @contextmanager
    def legacy_ff():
        nonlocal bounded_forward
        previous = bounded_forward
        bounded_forward = chunk_forward
        try:
            yield
        finally:
            bounded_forward = previous

    FeedForward.forward = chunked_ff
    original = MiniMaxH3Transformer3DModel.from_pretrained

    @classmethod
    def load_with_offload(cls, *load_args, **kwargs):
        model = original(*load_args, **kwargs)
        original_to = model.to

        def placed_to(self, device, *to_args, **to_kwargs):
            if torch.device(device).type == "cuda" and not to_args and not to_kwargs:
                # Restore class dispatch immediately; retaining this bound method
                # on the instance would keep the model alive through a cycle.
                del self.to
                if args.exact_io:
                    from h3_ic_exact import precast_lora_compute_weights, readonly_block_offload
                    cache_report = precast_lora_compute_weights(self, device)
                    if cache_report["linears"] != 312:
                        raise RuntimeError("Expected all 312 pinned IC LoRA linears before exact I/O placement")
                    print("IC exact I/O:", json.dumps(cache_report), flush=True)
                    result = readonly_block_offload(self, device)
                    if args.verify_first_block:
                        from h3_ic_exact import install_real_input_diagnostic
                        install_real_input_diagnostic(self, args.verify_first_block, legacy_ff)
                    return result
                return block_offload(self, device)
            return original_to(device, *to_args, **to_kwargs)

        model.to = types.MethodType(placed_to, model)
        return model

    MiniMaxH3Transformer3DModel.from_pretrained = load_with_offload
    weights = ROOT / "models/Open-H3-Regenerate-2K-IC"
    source = weights / "infer"
    sys.path.insert(0, str(source))
    # Free the full-resolution CPU pixel stack after both encoders consumed it.
    # Execute a guarded source adaptation without modifying the pinned bundle.
    original_source = (source / "infer.py").read_text()
    report = json.loads((ROOT / "deployment/minimax-h3/open-2k-weight-verification.json").read_text())
    expected = next(item["sha256"] for item in report["files"] if item["path"] == "infer/infer.py")
    if hashlib.sha256(original_source.encode()).hexdigest() != expected:
        raise RuntimeError("Pinned IC inference source differs from its verified checksum")
    anchor = "    # 2. Ref2VA transformer + HyperFlow + IC LoRA\n"
    if original_source.count(anchor) != 1:
        raise RuntimeError("Pinned IC stage boundary changed")

    def release_host():
        import ctypes
        gc.collect()
        ctypes.CDLL(None).malloc_trim(0)
        torch.cuda.empty_cache()

    adapted = original_source.replace(anchor, "    if rank == 0:\n        del drafts, pixels\n    _release_host()\n\n" + anchor)
    namespace = {"__name__": "h3_pinned_ic", "__file__": str(source / "infer.py"), "_release_host": release_host}
    exec(compile(adapted, str(source / "infer.py"), "exec"), namespace)
    original_vae = namespace["encode"].load_vae

    def cleaned_vae(*vae_args, **vae_kwargs):
        import ctypes
        gc.collect()
        ctypes.CDLL(None).malloc_trim(0)
        torch.cuda.empty_cache()
        return original_vae(*vae_args, **vae_kwargs)

    namespace["encode"].load_vae = cleaned_vae
    namespace["media"].write_video = lossless_write
    namespace["RESOLUTIONS"]["2k-portrait"] = (1344, 768, 2560, 1440, 2560)
    if profile.resolution == "2k-portrait":
        from ref2va_ic import upscale
        upscale.STAGE = (160, 90)
    print(f"IC native target {size}: compute {profile.native_width}x{profile.native_height}; "
          "BF16 denoiser, full FP32 tiled VAE", flush=True)
    sys.argv = [str(source / "infer.py"), "--weights", str(weights), "--jobs", str(args.jobs.resolve()),
                "--resolution", profile.resolution, "--attention", "native",
                "--vae", "standard", "--sampler", args.sampler, "--seed", str(args.seed)]
    if profile.label == "4K" or args.save_latent:
        # Preserve the exact denoised latent before the more demanding decode stage.
        sys.argv.append("--save-latent")
    from h3_ic_exact import ExactDiagnosticComplete
    try:
        namespace["main"]()
    except ExactDiagnosticComplete:
        if not args.verify_first_block:
            raise
        print("IC diagnostic complete; no output video was generated", flush=True)


if __name__ == "__main__":
    main()
