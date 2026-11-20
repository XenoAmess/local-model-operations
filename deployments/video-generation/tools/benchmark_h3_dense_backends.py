#!/usr/bin/env python3
"""Quick isolated BF16 dense-attention comparison, not a full-video quality test."""

import argparse
import fcntl
import gc
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def classify(case):
    """A finite fast output is insufficient: reject large errors or wrong final-key lookup."""
    valid = []
    for name in case.get("median_cuda_ms", {}):
        comparison = case.get("comparison", {}).get(name, {})
        sentinel = case.get("last_key_last_head_sentinel", {}).get(name, {})
        close = name == "current_flash" or comparison.get("sampled_relative_l2", float("inf")) < 0.02
        if close and sentinel.get("bitwise_equal_expected"):
            valid.append(name)
    case["valid_numerical_candidates"] = valid
    case["fastest_valid_backend_nominal"] = min(valid, key=case["median_cuda_ms"].get) if valid else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    # The thin IC environment reuses FastVideo's libraries, whose build tools
    # are outside its bin directory. Keep this fix local to the benchmark.
    os.environ["PATH"] = str(ROOT / "FastVideo/.venv/bin") + os.pathsep + os.environ["PATH"]
    lock = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    active = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
    if active:
        raise RuntimeError("GPU is occupied; benchmark must wait for current video delivery")
    verification = json.loads((ROOT / "outputs/video-queue/full-sequence-validation-20261120/verification.json").read_text())
    if verification.get("task_status") != "completed" or not verification.get("full_decode"):
        raise RuntimeError("The authorized S48 complete-video delivery has not passed verification")
    import torch
    import torch.nn.functional as F
    from torch.nn.attention import SDPBackend, sdpa_kernel
    torch.set_num_threads(8)
    torch.cuda.set_per_process_memory_fraction(0.75)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    report = {"status": "running", "started_at": time.time(), "torch": torch.__version__,
              "cudnn": torch.backends.cudnn.version(), "gpu": torch.cuda.get_device_name(),
              "dtype": "bfloat16", "precision": "BF16 Q/K/V and output; no FP8/FP4, no reduced-precision QK reduction",
              "scope": "Synthetic attention-only quick estimate at production query/KV shapes; NOT model or video quality validation",
              "warmup_calls_per_backend": 1, "measured_repeats": 3, "seed": 20261120,
              "isolation": isolation, "fallback_allowed": False, "cases": [], "errors": {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(args.output)

    save()
    flashinfer_call = None
    try:
        import flashinfer
        from flashinfer.prefill import get_single_prefill_module
        started = time.perf_counter()
        get_single_prefill_module("fa2", torch.bfloat16, torch.bfloat16, torch.bfloat16,
                                 128, 128, 0, False, False, False)
        report["flashinfer"] = {"version": flashinfer.__version__, "backend": "fa2",
                                "prepare_seconds_excluded_from_steady_timing": time.perf_counter()-started}
        flashinfer_call = flashinfer.single_prefill_with_kv_cache
    except Exception as error:
        report["errors"]["flashinfer_prepare"] = type(error).__name__ + ": " + str(error)[-1800:]
    save()
    for label, keys in (("single_window_4k", 345843), ("full_14s_4k", 949232)):
        torch.manual_seed(20261120)
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        queries, heads, dim = 16384, 56, 128
        q = torch.randn((1, queries, heads, dim), device="cuda", dtype=torch.bfloat16)
        k = torch.randn((1, heads, keys, dim), device="cuda", dtype=torch.bfloat16)
        v = torch.randn_like(k)
        case = {"name": label, "q_tokens": queries, "kv_tokens": keys, "heads": heads, "head_dim": dim,
                "query_layout": "BTHD contiguous, transposed view for SDPA", "kv_layout": "BHND contiguous",
                "q_stride": list(q.stride()), "k_stride": list(k.stride()), "runs": {}, "comparison": {}, "errors": {}}
        report["cases"].append(case)
        functions = {}

        def sdpa(backend):
            with sdpa_kernel(backend):
                return F.scaled_dot_product_attention(q.transpose(1, 2), k, v,
                    dropout_p=0.0, is_causal=False).transpose(1, 2)[0]

        functions["current_flash"] = lambda: sdpa(SDPBackend.FLASH_ATTENTION)
        functions["cudnn"] = lambda: sdpa(SDPBackend.CUDNN_ATTENTION)
        if flashinfer_call is not None:
            functions["flashinfer_fa2"] = lambda: flashinfer_call(q[0], k[0], v[0], causal=False,
                kv_layout="HND", pos_encoding_mode="NONE", use_fp16_qk_reduction=False,
                sm_scale=dim**-0.5, window_left=-1, backend="fa2")
        with torch.inference_mode():
            reference = None
            valid = {}
            for name, fn in functions.items():
                try:
                    output = fn()
                    torch.cuda.synchronize()
                    if not torch.isfinite(output).all().item():
                        raise RuntimeError("non-finite attention output")
                    if name == "current_flash":
                        reference = output
                    elif reference is not None:
                        actual, expected = output[::128].float(), reference[::128].float()
                        delta = actual - expected
                        case["comparison"][name] = {
                            "bitwise_equal_to_current": torch.equal(output, reference),
                            "sampled_max_abs": delta.abs().max().item(),
                            "sampled_relative_l2": (delta.norm() / expected.norm()).item(),
                            "sampled_cosine": F.cosine_similarity(actual.flatten(), expected.flatten(), dim=0).item()}
                        del actual, expected, delta
                    if name != "current_flash":
                        del output
                    valid[name] = fn
                    case["runs"][name] = []
                except Exception as error:
                    case["errors"][name] = type(error).__name__ + ": " + str(error)[-1800:]
                save()
            # Interleave the steady measurements to reduce clock/order bias.
            for repeat in range(3):
                for name, fn in valid.items():
                    torch.cuda.synchronize()
                    begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                    started = time.perf_counter()
                    begin.record()
                    output = fn()
                    end.record()
                    end.synchronize()
                    case["runs"][name].append({"repeat": repeat, "cuda_ms": begin.elapsed_time(end),
                                              "wall_ms": 1000 * (time.perf_counter()-started)})
                    del output
                    save()
            case["median_cuda_ms"] = {name: statistics.median(r["cuda_ms"] for r in rows)
                                       for name, rows in case["runs"].items() if rows}
            baseline = case["median_cuda_ms"].get("current_flash")
            case["speedup_vs_current"] = {name: baseline/value for name, value in case["median_cuda_ms"].items()} if baseline else {}
            # A distinctive final K/V at the last head checks very large strides,
            # including offsets beyond 32-bit indexing. Same shapes as timed calls.
            if reference is not None:
                del reference
            q[0, :4, -1].fill_(1)
            k[0, -1, -1].fill_(64)
            marker = torch.arange(dim, device="cuda", dtype=torch.float32).div(dim).to(torch.bfloat16)
            v[0, -1, -1].copy_(marker)
            case["last_key_last_head_sentinel"] = {}
            for name, fn in valid.items():
                output = fn()
                torch.cuda.synchronize()
                row = output[:4, -1]
                case["last_key_last_head_sentinel"][name] = {
                    "bitwise_equal_expected": torch.equal(row, marker.expand_as(row)),
                    "max_abs": (row.float()-marker.float()).abs().max().item()}
                del output, row
            case["peak_allocated_gib"] = torch.cuda.max_memory_allocated()/2**30
            case["peak_reserved_gib"] = torch.cuda.max_memory_reserved()/2**30
            classify(case)
            del q, k, v, marker
        gc.collect()
        torch.cuda.empty_cache()
        print(json.dumps({"case": label, "median_cuda_ms": case["median_cuda_ms"],
                          "speedup": case["speedup_vs_current"], "errors": case["errors"]}), flush=True)
        save()
    report.update(status="measured_attention_only", completed_at=time.time(), production_backend_changed=False)
    save()


if __name__ == "__main__":
    main()
