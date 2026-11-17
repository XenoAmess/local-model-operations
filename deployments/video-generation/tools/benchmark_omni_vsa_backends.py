#!/usr/bin/env python3
"""Compare actual framework VSA kernels on identical logical tile selections.

This excludes projections, top-k selection, gate/compression, transfers and
complete model execution. It is not an end-to-end Omni benchmark.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("fastvideo", "uniserve", "sglang"), required=True)
    parser.add_argument("--tokens", type=int, default=65536)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU busy")
    os.environ.update(CUDA_HOME=str(ROOT / "tools/cuda"), CUDA_VISIBLE_DEVICES="0")
    os.environ["PATH"] = str(Path(sys.executable).parent) + ":" + str(ROOT / "tools/cuda/bin") + ":" + os.environ["PATH"]
    import torch
    torch.set_num_threads(8)
    torch.cuda.set_per_process_memory_fraction(.50)
    tile, heads, dim = 128, 56, 128
    if args.tokens % tile:
        raise ValueError("Use complete logical tiles")
    blocks = args.tokens // tile
    keep = max(1, round(blocks * .1))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    input_path = args.output_dir / f"vsa-inputs-{args.tokens}.pt"
    if input_path.exists():
        host = list(torch.load(input_path, map_location="cpu", mmap=True, weights_only=True)["inputs"])
    else:
        if args.backend != "fastvideo":
            raise RuntimeError("Run the baseline first to create shared inputs")
        torch.manual_seed(963021)
        host = [torch.randn(args.tokens, heads, dim, dtype=torch.bfloat16) for _ in range(3)]
        torch.save(dict(inputs=host), input_path)
    fingerprint = hashlib.sha256()
    for value in host:
        fingerprint.update(memoryview(value.view(torch.uint8).numpy()))
    q, k, v = [value.cuda() for value in host]
    del host
    indices = torch.empty(heads, blocks, blocks, dtype=torch.int32, device="cuda")
    counts = torch.full((heads, blocks), keep, dtype=torch.int32, device="cuda")
    keys = torch.arange(blocks, device="cuda", dtype=torch.int32)
    query = torch.arange(blocks, device="cuda", dtype=torch.int32)
    head = torch.arange(heads, device="cuda", dtype=torch.int32)
    indices.copy_((keys[None, None, :] + query[None, :, None] * 13 + head[:, None, None] * 17) % blocks)
    counts[:, :2] = blocks
    sizes = torch.full((blocks,), tile, dtype=torch.int32, device="cuda")
    if args.backend == "uniserve":
        sys.path.insert(0, str(ROOT / "tools/vendor/uniserve-candidate"))
        from uniserve.nn.attention.vsa.inputs import Pattern, BlockInput
        from uniserve.runtime.backends.attention import vsa as backends
        pattern = Pattern(((blocks, blocks, *((keep,) * (blocks - 2))),), 2, blocks, tile)
        batch = BlockInput(pattern, indices, counts, sizes, 0)
        backend = backends.resolve("auto", device=q.device, tile=tile)
        operator = backend.prepare(pattern, num_heads=heads, head_dim=dim, dtype=q.dtype, workspace={})
        out = torch.empty_like(q)
        def call():
            return operator(q, k, v, batch, scale=dim ** -.5, out=out)
        kernel_name = "uniserve " + backend.name + " (logical 128 split into native 64)"
    else:
        # Every logical 128-row query and selected key becomes two 64-row
        # kernel blocks, preserving the exact selected key set.
        half_indices = (indices.repeat_interleave(2, dim=1).unsqueeze(-1) * 2 +
                        torch.arange(2, device="cuda", dtype=torch.int32)).flatten(-2).unsqueeze(0).contiguous()
        half_counts = (counts.repeat_interleave(2, dim=1) * 2).unsqueeze(0).contiguous()
        half_sizes = sizes.repeat_interleave(2).clamp(max=64)
        packed = [value.permute(1, 0, 2).unsqueeze(0).contiguous() for value in (q, k, v)]
        if args.backend == "fastvideo":
            implementation = load_module(ROOT / "FastVideo/fastvideo-kernel/python/fastvideo_kernel/triton_kernels/block_sparse_attn_triton.py", "fastvideo_pinned_vsa")
            def call():
                output, _ = implementation.triton_block_sparse_attn_forward(*packed, half_indices, half_counts, half_sizes)
                return output.squeeze(0).permute(1, 0, 2)
            kernel_name = "FastVideo Triton split-64 fallback used on SM120"
        else:
            implementation = load_module(ROOT / "tools/vendor/sglang-candidate/python/sglang/multimodal_gen/runtime/layers/attention/backends/vsa_h3_kernels.py", "sglang_pinned_vsa")
            def call():
                return implementation.vsa_h3_block_sparse_attn_forward(*packed, half_indices, half_counts, half_sizes).squeeze(0).permute(1, 0, 2)
            kernel_name = "SGLang Triton descriptor split-64"
    report = dict(backend=args.backend, kernel=kernel_name, torch=torch.__version__, tokens=args.tokens,
                  heads=heads, head_dim=dim, dtype="bfloat16", logical_tile=tile, keep_fraction=.1,
                  dense_query_tiles=2, input_sha256=fingerprint.hexdigest(), samples_s=[], started=time.time(),
                  scope="Sparse attention kernel only; not complete Omni latency or a quality comparison")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        for repeat in range(4):
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            start = time.monotonic()
            output = call()
            torch.cuda.synchronize()
            elapsed = time.monotonic() - start
            report["samples_s"].append(elapsed)
            report["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
            print(args.backend, repeat, elapsed, flush=True)
        report["median_s_after_warmup"] = statistics.median(report["samples_s"][1:])
        baseline_path = args.output_dir / f"vsa-reference-{args.tokens}.pt"
        if args.backend == "fastvideo":
            torch.save(dict(input_sha256=report["input_sha256"], output=output.cpu().contiguous()), baseline_path)
            report.update(bit_equal=True, max_abs_diff=0.0, rms_diff=0.0)
        else:
            reference = torch.load(baseline_path, map_location="cpu", mmap=True, weights_only=True)
            if reference["input_sha256"] != report["input_sha256"]:
                raise RuntimeError("Cross-version CPU random inputs differ; comparison invalid")
            equal, max_abs, squared, count = True, 0.0, 0.0, 0
            for start in range(0, args.tokens, 512):
                target = reference["output"][start:start+512].cuda()
                actual = output[start:start+512]
                equal = equal and torch.equal(actual, target)
                delta = actual.float() - target.float()
                max_abs = max(max_abs, delta.abs().max().item())
                squared += delta.square().sum(dtype=torch.float64).item()
                count += delta.numel()
            report.update(bit_equal=equal, max_abs_diff=max_abs, rms_diff=(squared / count) ** .5)
        report.update(status="measured_kernel_only", finished=time.time())
    (args.output_dir / f"vsa-{args.backend}-{args.tokens}.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
