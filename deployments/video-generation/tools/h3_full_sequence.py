# Decoder geometry adapted from Diffusers MiniMax-H3, MiniMax Team/HuggingFace, Apache-2.0.
"""Full-timeline IC helpers: exact frame geometry, resumable steps and original 36L streaming decode."""

import gc
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from plan_h3_2k_windows import WINDOW_FRAMES

ROOT = Path(__file__).resolve().parents[1]
VERSION = "full-sequence-dense-v1"
SINGLE_WINDOW_FRAMES = WINDOW_FRAMES
FPS = 24


def progress(path, stage, value, **extra):
    if path is None:
        return
    path = Path(path)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"stage": stage, "progress": value, "updated_at": time.time(),
                                "temporal_strategy": "full_sequence", **extra}, ensure_ascii=False) + "\n")
    temp.replace(path)


def padded_frames(frames):
    if not 113 <= frames <= 362:
        raise ValueError("Full-sequence input must contain 113–362 real frames at 24 fps")
    return 5 + math.ceil((frames - 5) / 17) * 17


def strategy(size, frames):
    return "full_sequence" if size == "3840x2160" and frames > SINGLE_WINDOW_FRAMES else "independent_windows"


def signature(job, seed, frames):
    source = Path(job["input"])
    st = source.stat()
    value = dict(version=VERSION, input=str(source.resolve()), bytes=st.st_size, mtime_ns=st.st_mtime_ns,
                 caption=job.get("caption", ""), seed=seed, processing_frames=frames)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def release_memory():
    import ctypes
    import torch
    gc.collect()
    ctypes.CDLL(None).malloc_trim(0)
    torch.cuda.empty_cache()


def atomic_torch_save(value, path):
    import torch
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".partial")
    torch.save(value, tmp)
    tmp.replace(path)


def load_encoded(jobs, seed, frames):
    import torch
    if len(jobs) != 1:
        raise ValueError("Full-sequence IC runs one complete clip per GPU task")
    path = Path(jobs[0]["output"]).with_suffix(".encoded.pt")
    key = signature(jobs[0], seed, frames)
    if not path.exists():
        return None
    cache = torch.load(path, map_location="cpu", weights_only=True)
    if cache.get("signature") != key:
        raise ValueError("Encoded full-sequence cache belongs to a different request")
    print("Full-sequence: reused verified draft/text encoding cache", flush=True)
    return cache["encoded"]


def save_encoded(encoded, jobs, seed, frames):
    atomic_torch_save({"signature": signature(jobs[0], seed, frames), "encoded": encoded},
                      Path(jobs[0]["output"]).with_suffix(".encoded.pt"))


def silence(frames, device):
    """Encode real zero waveform with the existing official audio VAE, posterior mean."""
    import torch
    from diffusers import AutoencoderKLMiniMaxH3Audio
    from safetensors.torch import load_file, save_file
    folder = ROOT / "outputs/h3-ic-cache"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"silence-{frames}-mode-v1.safetensors"
    if path.exists():
        return load_file(str(path))["audio_latents"]
    model = AutoencoderKLMiniMaxH3Audio.from_pretrained(
        str(ROOT / "models/MiniMax-H3-Ref2VA-BF16"), subfolder="audio_vae", torch_dtype=torch.float32,
        local_files_only=True).eval().requires_grad_(False).to(device)
    steps = math.ceil(frames * 5 / 3)
    samples = steps * 800
    with torch.inference_mode():
        z = model.encode(torch.zeros((2, 1, samples), device=device), return_dict=False)[0].mode()
        mean = torch.tensor(model.config.latents_mean, device=device).view(1, 32, 1)
        std = torch.tensor(model.config.latents_std, device=device).view(1, 32, 1)
        z = ((z.float() - mean) / std).bfloat16().cpu()
    if z.shape != (2, 32, steps) or not torch.isfinite(z).all():
        raise ValueError("Duration-matched encoded silence has incorrect geometry")
    save_file({"audio_latents": z}, str(path), metadata={"frames": str(frames), "method": "official_audio_vae_posterior_mode"})
    del model
    release_memory()
    print(f"Full-sequence internal silence: {frames} frames -> {steps} audio steps", flush=True)
    return z


def resume_step(job, sampler, x, seed, frames, sigmas):
    import torch
    path = Path(job["output"]).with_suffix(".sampling.pt")
    if not path.exists():
        return x, 0
    value = torch.load(path, map_location="cpu", weights_only=True)
    if (value.get("signature") != signature(job, seed, frames) or value.get("sampler") != sampler
            or value.get("sigmas") != sigmas or tuple(value["x"].shape) != tuple(x.shape)):
        raise ValueError("Sampling checkpoint does not match this full-sequence request")
    print(f"Full-sequence: resuming after {value['completed_steps']} completed steps", flush=True)
    return value["x"].to(x.device), int(value["completed_steps"])


def save_step(job, sampler, x, seed, frames, sigmas, completed):
    atomic_torch_save(dict(signature=signature(job, seed, frames), sampler=sampler, sigmas=sigmas,
                           completed_steps=completed, x=x.detach().cpu()),
                      Path(job["output"]).with_suffix(".sampling.pt"))


def decoded_uint8_chunks(vae, normalized, *, frames, keep_height, batch_frames=4):
    """Same temporal clips and _blend as the released decoder; never collect the full FP32 movie."""
    import torch
    from ref2va_ic.encode import _stats
    device = next(vae.parameters()).device
    mean, std, pm, ps = _stats(vae, device)
    z = normalized[None].to(device).float() * std + mean
    size, drop, ratio = vae.tokens_chunk_size, vae.config.token_drop, vae.temporal_compression_ratio
    pad = (-(z.shape[2] + drop)) % size
    if pad:
        raise ValueError("Full-sequence decoder expects the legal 17*n+5 frame grid")
    count = (z.shape[2] + drop) // size - int(drop > 0)
    pixel_chunk = size * ratio
    overlap, emitted = None, 0

    def convert(piece):
        nonlocal emitted
        top = (piece.shape[-2] - keep_height) // 2
        if top < 0:
            raise ValueError("Decoded canvas is shorter than target")
        take = min(piece.shape[2], frames - emitted)
        for start in range(0, take, batch_frames):
            x = piece[:, :, start:min(take, start + batch_frames), top:top + keep_height]
            x = ((x * ps + pm).clamp(0, 1) * 255).round().byte()
            array = x[0].permute(1, 2, 3, 0).cpu().numpy()
            emitted += len(array)
            yield array
    for index in range(count):
        clip = vae._decode_clip(z[:, :, index * size:index * size + size + vae.token_overlap])
        first = clip[:, :, :pixel_chunk][:, :, vae.frame_pre_padding:]
        if overlap is not None:
            first = vae._blend(overlap, first, vae.frame_overlap, dim=-3)
        yield from convert(first)
        if emitted >= frames:
            break
        overlap = clip[:, :, pixel_chunk:2 * pixel_chunk][:, :, vae.frame_pre_padding:].clone()
        del first, clip
    if emitted < frames and overlap is not None:
        yield from convert(overlap)
    if emitted != frames:
        raise ValueError(f"Streaming VAE returned {emitted} frames, expected {frames}")


def decode_one(job, enc, sampler, output, z, base, device, seed, frames, save_latent=True):
    import torch
    from ref2va_ic import encode
    output = Path(output)
    meta = {"signature": signature(job, seed, frames), "sampler": sampler, "seed": seed,
            "processing_frames": frames, "output_frames": enc["frames"], "video_latents": z}
    latent = output.with_suffix(".latent.pt")
    if save_latent:
        atomic_torch_save(meta, latent)
    release_memory()
    progress(output.parent / "progress.json", "原版 36 层 VAE 整段流式解码", 88)
    vae = encode.load_vae(base, device)
    width, keep = 3840, 2160
    temporary = output.with_name(output.stem + ".partial.mkv")
    command = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{width}x{keep}", "-r", "24", "-i", "-", "-an", "-c:v", "ffv1", "-level", "3",
               "-threads", "2", str(temporary)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    started, written = time.time(), 0
    try:
        with torch.inference_mode():
            for array in decoded_uint8_chunks(vae, z, frames=enc["frames"], keep_height=keep):
                for frame in array:
                    process.stdin.write(frame.tobytes())
                    written += 1
                print(f"Full-sequence original 36L decode: {written}/{enc['frames']} frames", flush=True)
                progress(output.parent / "progress.json", f"原版 36 层解码 {written}/{enc['frames']} 帧",
                         88 + int(8 * written / enc["frames"]), decoded_frames=written)
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Streaming full-sequence video encoding failed")
        temporary.replace(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        del vae
        release_memory()
    print(f"Full-sequence wrote {output}: {width}x{keep}, {written} frames, 36L decode {time.time()-started:.1f}s", flush=True)


def decode_results(results, base, device, seed, frames):
    for job, enc, sampler, output, z in results:
        decode_one(job, enc, sampler, output, z, base, device, seed, frames)
