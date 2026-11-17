#!/usr/bin/env python3
"""Benchmark a real IC block and same-kernel attention; require bitwise parity."""

import argparse
import ctypes
import gc
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokens", type=int, default=344064)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--query-chunks", type=int, nargs="*", default=[4096, 16384, 65536])
    parser.add_argument("--block-only", action="store_true", help="Skip unrelated attention kernel sweeps")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    import fcntl
    lock = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    import subprocess
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise SystemExit("GPU is busy; benchmark must wait for the active HTTP task")

    import torch
    from torch import nn
    from safetensors import safe_open
    from diffusers.models.attention import FeedForward
    from diffusers.models.transformers.transformer_minimax_h3 import MiniMaxH3TransformerBlock
    from diffusers.models.transformers import transformer_minimax_h3 as transformer_module
    from h3_ic_runtime import chunk_forward
    from h3_ic_exact import chunk_forward_preallocated, precast_lora_compute_weights, readonly_block_offload
    sys.path.insert(0, str(ROOT / "models/Open-H3-Regenerate-2K-IC/infer"))
    from ref2va_ic import sharp
    from ref2va_ic.lora import LoRALinear

    torch.set_num_threads(8)
    torch.cuda.set_per_process_memory_fraction(.95)
    torch.manual_seed(1234)
    weights = ROOT / "models/Open-H3-Regenerate-2K-IC"
    config = json.loads((weights / "config.json").read_text())
    base = weights / "base_model/transformer_ref"
    model_config = json.loads((base / "config.json").read_text())
    mapping = json.loads((base / "diffusion_pytorch_model.safetensors.index.json").read_text())["weight_map"]
    prefix = "transformer_blocks.0."
    report = {"started": time.time(), "torch": torch.__version__, "gpu": torch.cuda.get_device_name(),
              "tokens": args.tokens, "heads": 56, "head_dim": 128,
              "scope": "one real block with actual HyperFlow, Sharp and unmerged IC adapters; not a full-video speedup",
              "block": {}, "attention": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    def clear():
        gc.collect()
        ctypes.CDLL(None).malloc_trim(0)
        torch.cuda.empty_cache()

    with torch.device("meta"):
        block = MiniMaxH3TransformerBlock(hidden_size=model_config["hidden_size"],
            num_attention_heads=56, attention_head_dim=128, ffn_dim=model_config["ffn_dim"],
            time_embed_dim=model_config["time_embed_dim"], norm_eps=model_config["norm_eps"],
            qk_norm_eps=model_config["qk_norm_eps"])
    state = {}
    for name, filename in mapping.items():
        if name.startswith(prefix):
            with safe_open(base / filename, framework="pt", device="cpu") as archive:
                state[name[len(prefix):]] = archive.get_tensor(name).to(torch.bfloat16)
    block.load_state_dict(state, assign=True)
    del state
    block.requires_grad_(False).eval().to("cuda")
    # Use the production merge order and the exact same CUDA FP32 GEMM shapes.
    with torch.no_grad(), safe_open(weights / config["components"]["hyperflow"], framework="pt", device="cpu") as archive:
        metadata = archive.metadata()
        scale = float(metadata["lora_alpha"]) / int(metadata["lora_rank"])
        for name in archive.keys():
            if name.startswith("transformer." + prefix) and name.endswith(".lora_A.weight"):
                root = name[:-len(".lora_A.weight")]
                layer = block.get_submodule(root[len("transformer." + prefix):])
                a, b = archive.get_tensor(name).cuda().float(), archive.get_tensor(root + ".lora_B.weight").cuda().float()
                layer.weight.copy_((layer.weight.float() + scale * (b @ a)).to(layer.weight.dtype))
                del a, b
    linears, curves = sharp.convert(weights / config["components"]["sharp_lora"])
    context = sharp.CurveContext(weights / config["components"]["sharp_curve"], config["sampler"]["sharp"])
    with torch.no_grad():
        for name, (a, b) in linears.items():
            if name.startswith(prefix):
                layer = block.get_submodule(name[len(prefix):])
                layer.weight.copy_((layer.weight.float() + context.strength * (b.cuda() @ a.cuda())).to(layer.weight.dtype))
        for name, (a, b) in curves.items():
            if name.startswith(prefix):
                parent, child = name[len(prefix):].rsplit(".", 1)
                layer = block.get_submodule(parent)
                setattr(layer, child, sharp.CurveLinear(getattr(layer, child), a.cuda(), b.cuda(), context))
    del linears, curves, a, b
    with safe_open(weights / config["components"]["lora"], framework="pt", device="cpu") as archive:
        for name in archive.keys():
            if name.startswith("transformer." + prefix) and name.endswith(".lora_A.weight"):
                root = name[:-len(".lora_A.weight")]
                parent, child = root[len("transformer." + prefix):].rsplit(".", 1)
                layer = block.get_submodule(parent)
                base_layer = layer[int(child)] if child.isdigit() else getattr(layer, child)
                wrapped = LoRALinear(base_layer, archive.get_tensor(name).cuda().float(),
                                     archive.get_tensor(root + ".lora_B.weight").cuda().float(), 1.)
                if child.isdigit():
                    layer[int(child)] = wrapped
                else:
                    setattr(layer, child, wrapped)
    block.to("cpu")
    clear()
    original_ff = FeedForward.forward
    execution = {"kind": "baseline"}

    def bounded_ff(self, x, *ff_args, **ff_kwargs):
        function = chunk_forward if execution["kind"] == "baseline" else chunk_forward_preallocated
        return function(lambda part: original_ff(self, part, *ff_args, **ff_kwargs))(x)

    FeedForward.forward = bounded_ff

    class SingleBlock(nn.Module):
        def __init__(self, value):
            super().__init__()
            self.transformer_blocks = nn.ModuleList([value])

        def forward(self, x, temb, indices, rope):
            return self.transformer_blocks[0](x, temb, indices, rope)

    model = SingleBlock(block).eval().requires_grad_(False)
    component = {}
    pending = {}
    handles = []
    for name in ("attn", "ff", "adaln_proj", "norm1", "norm2", "attn.norm_q", "attn.norm_k",
                 "attn.to_q", "attn.to_k", "attn.to_v", "attn.to_out.0"):
        def before(module, inputs, tag=name):
            start = torch.cuda.Event(enable_timing=True)
            start.record()
            pending[tag] = start

        def after(module, inputs, output, tag=name):
            end = torch.cuda.Event(enable_timing=True)
            end.record()
            component[tag] = (pending[tag], end)

        handles.extend([block.get_submodule(name).register_forward_pre_hook(before),
                        block.get_submodule(name).register_forward_hook(after)])
    original_dispatch = transformer_module.dispatch_attention_fn

    def timed_dispatch(*call_args, **call_kwargs):
        begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        begin.record()
        value = original_dispatch(*call_args, **call_kwargs)
        end.record()
        component["sdpa"] = (begin, end)
        return value

    transformer_module.dispatch_attention_fn = timed_dispatch
    with torch.inference_mode():
        x = torch.randn(1, args.tokens, 5376, dtype=torch.bfloat16, device="cuda")
        temb = torch.randn(3, 2688, dtype=torch.float32, device="cuda")
        indices = torch.arange(args.tokens, device="cuda") % 9
        angles = torch.randn(args.tokens, 48, device="cuda")
        rope = (angles.cos(), angles.sin())
        del angles
        context.pre(None, (), {"timestep": torch.tensor([.165058, .999, 1.], device="cuda")})
        expected = None
        for kind in ("baseline", "exact_io"):
            execution["kind"] = kind
            if kind == "exact_io":
                report["cast_cache"] = precast_lora_compute_weights(model, "cuda")
                readonly_block_offload(model, "cuda")
            samples = []
            for repeat in range(args.repeats + 1):
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                start = time.monotonic()
                if kind == "baseline":
                    block.to("cuda")
                output = model(x, temb, indices, rope)
                if kind == "baseline":
                    block.to("cpu")
                torch.cuda.synchronize()
                elapsed = time.monotonic() - start
                equal = True if expected is None else torch.equal(expected, output)
                if expected is None:
                    if not bool(torch.isfinite(output).all()):
                        raise RuntimeError("Invalid non-finite baseline output")
                    expected = output
                timing = {"repeat": repeat, "wall_s": elapsed, "bit_equal": equal,
                          "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
                          "component_ms": {name: a.elapsed_time(b) for name, (a, b) in component.items()}}
                samples.append(timing)
                report["block"][kind] = samples
                save()
                print(kind, json.dumps(timing), flush=True)
                if not equal:
                    raise RuntimeError("Reject optimization: the actual IC block output changed")
                if output is not expected:
                    del output
        for handle in handles:
            handle.remove()
        report["block_speedup"] = statistics.median(x["wall_s"] for x in report["block"]["baseline"][1:]) / \
                                  statistics.median(x["wall_s"] for x in report["block"]["exact_io"][1:])
        del model, block, expected, x, temb, indices, rope
        clear()
        if args.block_only:
            report.update(status="block_exact_io_bitwise_verified", finished=time.time())
            save()
            return

        q, k, v = [torch.randn(1, args.tokens, 56, 128, device="cuda", dtype=torch.bfloat16) for _ in range(3)]

        def sdpa(query):
            return torch.nn.functional.scaled_dot_product_attention(query.transpose(1, 2), k.transpose(1, 2),
                                                                   v.transpose(1, 2)).transpose(1, 2)

        reference = sdpa(q)
        for chunk in (0, *args.query_chunks):
            def call():
                if not chunk:
                    return sdpa(q)
                result = torch.empty_like(q)
                for offset in range(0, args.tokens, chunk):
                    result[:, offset:offset + chunk].copy_(sdpa(q[:, offset:offset + chunk]))
                return result

            output = call()
            torch.cuda.synchronize()
            equal = torch.equal(reference, output)
            del output
            times = []
            for _ in range(args.repeats):
                begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                begin.record()
                result = call()
                end.record()
                end.synchronize()
                times.append(begin.elapsed_time(end))
                del result
            item = {"query_chunk": chunk, "bit_equal": equal, "median_ms": statistics.median(times)}
            report["attention"].append(item)
            save()
            print("attention", json.dumps(item), flush=True)
        report.update(status="block_exact_io_bitwise_verified", finished=time.time(),
                      peak_gpu_bytes=torch.cuda.max_memory_allocated())
        save()


if __name__ == "__main__":
    main()
