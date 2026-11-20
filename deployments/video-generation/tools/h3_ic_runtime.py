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
    parser.add_argument("--full-sequence", action="store_true", help="One complete dense-attention trajectory; no temporal sampling windows")
    parser.add_argument("--frames", type=int, help="Real 24-fps output frames for full-sequence mode")
    parser.add_argument("--prepare-only", action="store_true", help="Cache the real full-sequence video/text encoding, then stop before DiT")
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
    if args.full_sequence and (size != "3840x2160" or args.frames is None):
        parser.error("Full-sequence mode requires --size 3840x2160 and --frames")
    if args.prepare_only and not args.full_sequence:
        parser.error("--prepare-only requires --full-sequence")
    if args.full_sequence and args.verify_first_block:
        parser.error("Full-sequence arithmetic is checked with validate_h3_full_sequence.py, not the legacy bitwise probe")
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    if args.prepare_only:
        import fcntl
        preparation_lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
        fcntl.flock(preparation_lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
                if args.full_sequence:
                    from h3_full_attention import install
                    first_job = next(json.loads(line) for line in args.jobs.read_text().splitlines() if line.strip())
                    install(self, progress_path=Path(first_job["output"]).parent / "progress.json")
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
    if args.full_sequence:
        from textwrap import indent
        import h3_full_sequence as full
        processing = full.padded_frames(args.frames)
        # Adapt only the already-checksummed runner. Keep the pinned package unchanged.
        first = adapted.index("    # 1. drafts ->")
        second = adapted.index("    # 2. Ref2VA")
        stage = adapted[first:second]
        adapted = (adapted[:first] + "    if world != 1:\n        raise ValueError('Local full-sequence mode requires one GPU')\n"
                   "    encoded = _full_load_encoded(jobs, args.seed, _full_frames)\n"
                   "    if encoded is None:\n" + indent(stage, "    ") +
                   "        _full_save_encoded(encoded, jobs, args.seed, _full_frames)\n"
                   "    if _full_prepare_only:\n        print('Full-sequence preparation complete; no DiT run', flush=True)\n        return\n\n" + adapted[second:])
        replacements = {
            "audio = load_file(str(W / config['components']['silence_audio']))['audio_latents']":
                "audio = _full_silence(_full_frames, device)",
            "            t0 = time.time()\n            with torch.inference_mode():":
                "            x, _resume_steps = _full_resume_step(job, name, x, args.seed, _full_frames, sigmas)\n"
                "            model._full_step = _resume_steps\n            model._full_total_steps = len(sigmas) - 1\n"
                "            t0 = time.time()\n            with torch.inference_mode():",
            "                for sigma, nxt in zip(sigmas[:-1], sigmas[1:]):":
                "                for _step, (sigma, nxt) in enumerate(zip(sigmas[:-1], sigmas[1:])):\n"
                "                    if _step < _resume_steps:\n                        continue",
            "                    x = x + (sigma - nxt) * v[:, n:].float()":
                "                    x = x + (sigma - nxt) * v[:, n:].float()\n"
                "                    _full_save_step(job, name, x, args.seed, _full_frames, sigmas, _step + 1)",
        }
        for before, after in replacements.items():
            if adapted.count(before) != 1:
                raise RuntimeError("Pinned full-sequence source adaptation anchor changed: " + before[:70])
            adapted = adapted.replace(before, after)
        decode_start = adapted.index("    # 4. decode:")
        entry = adapted.index("\n\nif __name__ == '__main__':")
        adapted = (adapted[:decode_start] + "    del model\n    _release_host()\n"
                   "    _full_decode_results(results, base, device, args.seed, _full_frames)\n" + adapted[entry:])
        namespace.update(_full_frames=processing, _full_prepare_only=args.prepare_only, _full_load_encoded=full.load_encoded,
                         _full_save_encoded=full.save_encoded, _full_silence=full.silence,
                         _full_resume_step=full.resume_step, _full_save_step=full.save_step,
                         _full_decode_results=full.decode_results)
    exec(compile(adapted, str(source / "infer.py"), "exec"), namespace)
    if args.full_sequence:
        namespace["media"].FRAMES = processing
        jobs = [json.loads(line) for line in args.jobs.read_text().splitlines() if line.strip()]
        if len(jobs) != 1:
            raise ValueError("Full-sequence runtime accepts exactly one complete video")
        latent_path = Path(jobs[0]["output"]).with_suffix(".latent.pt")
        if latent_path.exists():
            saved = torch.load(latent_path, map_location="cpu", weights_only=True)
            if (saved.get("signature") != full.signature(jobs[0], args.seed, processing)
                    or saved.get("sampler") != args.sampler or saved.get("output_frames") != args.frames):
                raise ValueError("Saved full-sequence latent does not match request")
            print("Full-sequence: resuming original 36L decode from completed latent", flush=True)
            with torch.inference_mode():
                full.decode_one(jobs[0], {"frames": args.frames}, args.sampler, jobs[0]["output"],
                                saved["video_latents"], weights / "base_model", torch.device("cuda"),
                                args.seed, processing, save_latent=False)
            return
        print(f"Full-sequence input: {args.frames} real frames, {processing} processing frames; no hard cuts", flush=True)
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
