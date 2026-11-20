#!/usr/bin/env python3
"""Isolated admission checks: BF16 full-context math, real 36L stream parity, long-KV capacity."""

import argparse
import copy
import fcntl
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lock = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    import numpy as np
    import torch
    import torch.nn.functional as F
    from torch.nn.attention import SDPBackend, sdpa_kernel
    from diffusers import MiniMaxH3Transformer3DModel
    from h3_full_attention import install
    import h3_full_sequence as full
    torch.set_num_threads(8)
    device = torch.device("cuda")
    report = {"status": "in_progress", "complete_video_qualified": False, "started_at": time.time()}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    save()
    torch.manual_seed(1)
    model = MiniMaxH3Transformer3DModel(num_attention_heads=4, attention_head_dim=16, hidden_size=48,
        num_layers=2, num_refiner_layers=1, ffn_dim=96, text_dim=32, time_embed_hidden_dim=48,
        time_embed_dim=24, freq_dim=16, rope_freq_dim=2).eval().requires_grad_(False).to(device, dtype=torch.bfloat16)
    for name in ("proj_in", "audio_proj_in", "time_embedder", "proj_out", "audio_proj_out", "rope"):
        model.get_submodule(name).float()
    candidate = copy.deepcopy(model)
    install(candidate, chunk=7, ff_chunk=5)
    n = 25
    kwargs = dict(hidden_states=torch.randn(1, 19, 96, device=device),
        audio_hidden_states=torch.randn(1, 2, 32, device=device), encoder_hidden_states=torch.randn(1, 4, 32, device=device),
        timestep=torch.tensor([0.2, 0.9], device=device), timestep_indices=torch.arange(n, device=device) % 2,
        token_tags=torch.tensor([1]*4+[0]*19+[2]*2, device=device),
        position_ids=torch.stack([torch.arange(n, device=device), torch.zeros(n, device=device), torch.ones(n, device=device)], 1),
        video_indices=torch.arange(4, 23, device=device), audio_indices=torch.tensor([23, 24], device=device),
        text_indices=torch.arange(4, device=device), return_dict=False)
    with torch.inference_mode():
        old, new = model(**kwargs), candidate(**kwargs)
    for a, b in zip(old, new):
        torch.testing.assert_close(a, b, rtol=0.01, atol=0.008)
    report["bf16_math"] = {"max_video_abs": (old[0]-new[0]).abs().max().item(),
                           "max_audio_abs": (old[1]-new[1]).abs().max().item(),
                           "bitwise_equal": all(torch.equal(a, b) for a, b in zip(old, new))}
    del model, candidate, old, new, kwargs
    full.release_memory()
    save()
    sys.path.insert(0, str(ROOT / "models/Open-H3-Regenerate-2K-IC/infer"))
    from ref2va_ic import encode
    vae = encode.load_vae(ROOT / "models/Open-H3-Regenerate-2K-IC/base_model", device)
    assert len(vae.decoder.transformer_blocks) == 36
    z = torch.randn(24, 102, 4, 4, dtype=torch.bfloat16)
    with torch.inference_mode():
        original = encode.vae_decode(vae, z)[:336]
        streamed = np.concatenate(list(full.decoded_uint8_chunks(vae, z, frames=336, keep_height=64)), axis=0)
    if not np.array_equal(original, streamed):
        raise AssertionError(f"Original 36L streamed pixels differ: max {np.abs(original.astype(int)-streamed.astype(int)).max()}")
    report["original_36l_stream"] = {"frames": len(streamed), "processing_latent_frames": 102,
                                     "size": "64x64", "pixel_bitwise_equal": True, "decoder_layers": 36}
    del vae, z, original, streamed
    full.release_memory()
    save()
    audio = full.silence(345, device)
    assert audio.shape == (2, 32, 575)
    report["matched_silence"] = {"shape": list(audio.shape), "method": "official_vae_posterior_mode"}
    del audio
    full.release_memory()
    save()
    # One actual-sized query batch sees the complete K/V document. Reserve the
    # three residual-width buffers the bounded block needs; this is capacity,
    # not a fake whole-video performance result.
    tokens, heads, dim, queries = 960000, 56, 128, 16384
    torch.cuda.reset_peak_memory_stats()
    reserve = torch.empty((3, 1, tokens, 5376), device=device, dtype=torch.bfloat16)
    keys = torch.randn((1, heads, tokens, dim), device=device, dtype=torch.bfloat16)
    values = torch.randn_like(keys)
    query = torch.randn((1, heads, queries, dim), device=device, dtype=torch.bfloat16)
    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode(), sdpa_kernel(SDPBackend.FLASH_ATTENTION):
        out = F.scaled_dot_product_attention(query, keys, values, dropout_p=0.0, is_causal=False)
    torch.cuda.synchronize()
    assert torch.isfinite(out).all()
    report["long_kv_capacity"] = {"kv_tokens": tokens, "query_tokens": queries, "heads": heads,
        "head_dim": dim, "residual_buffers_reserved": 3, "seconds_one_query_batch": time.perf_counter()-started,
        "gpu_allocated_peak_gib": torch.cuda.max_memory_allocated()/2**30, "finite": True,
        "full_model_or_video_test": False}
    del reserve, keys, values, query, out
    full.release_memory()
    report.update(status="passed", completed_at=time.time())
    save()
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
