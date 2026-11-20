#!/usr/bin/env python3
"""Native AOT FROST versus deployed Flash SDPA at H3 shapes; never fallback."""

import ctypes as C
import fcntl
import gc
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "outputs/video-queue/engineering-tests-after-S42-20261121"


class Desc(C.Structure):
    _fields_ = [("struct_size", C.c_uint32)] + [(n, C.c_int32) for n in
        ("head_dim", "q_dtype", "kv_dtype", "o_dtype", "mask", "window_left", "has_sinks", "gqa_ratio")]


class Knobs(C.Structure):
    _fields_ = [("struct_size", C.c_uint32)] + [(n, C.c_int32) for n in
        ("pack_gqa", "sched_policy", "split_kv", "tile_m", "tile_n")]


class Args(C.Structure):
    _fields_ = ([("struct_size", C.c_uint32)] + [(n, C.c_int32) for n in ("b", "h_q", "h_kv", "s_q", "s_kv")]
                + [(n, C.c_void_p) for n in ("q", "k", "v", "o")]
                + [(n, C.c_int64 * 3) for n in ("q_stride", "k_stride", "v_stride", "o_stride")]
                + [("scale", C.c_float), ("sinks", C.c_void_p), ("mask", C.c_void_p), ("mask_stride", C.c_int64 * 2)])


def setup_library():
    lib = C.CDLL(str(DIRECTORY / "frost-aot/lib/libcudnn_frontend_aot_sm120.so"))
    prefix = "cudnn_fe_aot_sm120_"
    signatures = {
        "abi_version": (C.c_uint32, []), "build_info": (C.c_char_p, []), "last_error": (C.c_char_p, []),
        "sdpa_plan_create": (C.c_int, [C.POINTER(Desc), C.POINTER(Knobs), C.c_int, C.POINTER(C.c_void_p)]),
        "sdpa_plan_destroy": (None, [C.c_void_p]),
        "sdpa_workspace_size": (C.c_int, [C.c_void_p, C.POINTER(Args), C.POINTER(C.c_size_t)]),
        "sdpa_execute": (C.c_int, [C.c_void_p, C.POINTER(Args), C.c_void_p, C.c_size_t, C.c_void_p]),
        "sdpa_query": (C.c_int, [C.c_void_p, C.POINTER(Args), C.POINTER(Knobs), C.POINTER(C.c_char_p)]),
        "sdpa_num_knob_sets": (C.c_int32, [C.POINTER(Desc)]),
        "sdpa_get_knob_set": (C.c_int, [C.POINTER(Desc), C.c_int32, C.POINTER(Knobs)])}
    for name, (result, arguments) in signatures.items():
        fn = getattr(lib, prefix + name)
        fn.restype, fn.argtypes = result, arguments
        setattr(lib, name, fn)
    return lib


def check(lib, status):
    if status:
        raise RuntimeError(f"FROST status {status}: {lib.last_error().decode()}")


def knob_tuple(knobs):
    return tuple(getattr(knobs, n) for n in ("pack_gqa", "sched_policy", "split_kv", "tile_m", "tile_n"))


class Plan:
    def __init__(self, lib, desc, knobs, q, k, v):
        import torch
        self.lib, self.plan = lib, C.c_void_p()
        check(lib, lib.sdpa_plan_create(C.byref(desc), C.byref(knobs) if knobs is not None else None, -1, C.byref(self.plan)))
        self.output = torch.empty_like(q)
        self.args = Args()
        self.args.struct_size = C.sizeof(Args)
        self.args.b, self.args.s_q, self.args.h_q, _ = q.shape
        self.args.h_kv, self.args.s_kv = k.shape[1:3]
        for name, tensor, order in (("q", q, (0, 1, 2)), ("k", k, (0, 2, 1)),
                                    ("v", v, (0, 2, 1)), ("o", self.output, (0, 1, 2))):
            setattr(self.args, name, tensor.data_ptr())
            setattr(self.args, name + "_stride", (C.c_int64 * 3)(*(tensor.stride(i) * tensor.element_size() for i in order)))
        self.args.scale = 128 ** -0.5
        self.size = C.c_size_t()
        check(lib, lib.sdpa_workspace_size(self.plan, C.byref(self.args), C.byref(self.size)))
        self.workspace = torch.empty(self.size.value, device="cuda", dtype=torch.uint8) if self.size.value else None
        selected, name = Knobs(), C.c_char_p()
        selected.struct_size = C.sizeof(Knobs)
        check(lib, lib.sdpa_query(self.plan, C.byref(self.args), C.byref(selected), C.byref(name)))
        self.knobs, self.kernel = knob_tuple(selected), name.value.decode()

    def __call__(self):
        import torch
        check(self.lib, self.lib.sdpa_execute(self.plan, C.byref(self.args),
                    self.workspace.data_ptr() if self.workspace is not None else None,
                    self.size.value, torch.cuda.current_stream().cuda_stream))
        return self.output

    def close(self):
        if self.plan:
            self.lib.sdpa_plan_destroy(self.plan)
            self.plan = C.c_void_p()


def metrics(actual, expected):
    import torch
    a, e = actual.float(), expected.float()
    delta = a-e
    finite = bool(torch.isfinite(a).all().item())
    return {"all_finite": finite, "raw_bits_equal": torch.equal(actual.view(torch.int16), expected.view(torch.int16)),
            "different_elements": torch.count_nonzero(actual != expected).item(), "elements": actual.numel(),
            "max_abs": delta.abs().max().item(),
            "relative_l2": (torch.linalg.vector_norm(delta)/torch.linalg.vector_norm(e).clamp_min(1e-30)).item(),
            "cosine": torch.nn.functional.cosine_similarity(a.flatten(), e.flatten(), dim=0).item()}


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    assert json.loads((DIRECTORY / "delivery-verification.json").read_text())["full_decode"]
    import requests
    client = requests.Session(); client.trust_env = False
    queue = client.get("http://127.0.0.1:8002/v1/queue", timeout=10).json()
    assert queue["maintenance"]["enabled"] and queue["maintenance"]["upgrade_id"] == "engineering-tests-after-S42-20261121"
    assert not queue["running"] and not queue["scheduler"]["running_jobs"] and not queue["recovery"]["paused"]
    lock = (ROOT / "outputs/h3-2k-gpu.lock").open("a"); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
    import torch
    import torch.nn.functional as F
    from torch.nn.attention import SDPBackend, sdpa_kernel
    torch.set_num_threads(4)
    torch.cuda.set_per_process_memory_fraction(0.80)
    torch.backends.cuda.matmul.allow_tf32 = False
    lib = setup_library()
    desc = Desc(C.sizeof(Desc), 128, 1, 1, 1, 0, -1, 0, 1)
    choices = [("auto", None)]
    for index in range(lib.sdpa_num_knob_sets(C.byref(desc))):
        knobs = Knobs(); knobs.struct_size = C.sizeof(Knobs)
        check(lib, lib.sdpa_get_knob_set(C.byref(desc), index, C.byref(knobs)))
        if knobs.pack_gqa == 0 and knobs.split_kv == 1:
            choices.append((f"unsplit_m{knobs.tile_m}_sched{knobs.sched_policy}", knobs))
    report = {"status": "running", "isolation": isolation, "torch": torch.__version__, "source_commit": "9638468d752dbc97fc252be3a973855a0c4e9651",
              "abi_version": lib.abi_version(), "build_info": lib.build_info().decode(), "dtype": "BF16",
              "scope": "Synthetic operator comparison; no full model or video quality validation", "new_gpu_tests": True,
              "fallback_allowed": False, "production_changed": False, "cases": []}
    path = ROOT / "deployment/minimax-h3/frost-quick-benchmark-20261121.json"

    def save():
        temporary = path.with_suffix(".tmp"); temporary.write_text(json.dumps(report, indent=2)+"\n"); temporary.replace(path)

    def timed(fn):
        torch.cuda.synchronize()
        begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        started = time.perf_counter(); begin.record(); output = fn(); end.record(); end.synchronize()
        return {"cuda_ms": begin.elapsed_time(end), "wall_ms": 1000*(time.perf_counter()-started)}, output

    save()
    with torch.inference_mode():
        for name, queries, keys, heads in (("small_fp64_reference", 97, 1009, 2),
                ("single_window_4k", 16384, 345843, 56), ("full_14s_4k", 16384, 949232, 56)):
            torch.manual_seed(20261121); gc.collect(); torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
            q = torch.randn((1, queries, heads, 128), device="cuda", dtype=torch.bfloat16)
            k = torch.randn((1, heads, keys, 128), device="cuda", dtype=torch.bfloat16); v = torch.randn_like(k)
            def baseline():
                with sdpa_kernel(SDPBackend.FLASH_ATTENTION):
                    return F.scaled_dot_product_attention(q.transpose(1, 2), k, v, dropout_p=0, is_causal=False).transpose(1, 2)
            reference = baseline(); torch.cuda.synchronize()
            case = {"name": name, "q_tokens": queries, "kv_tokens": keys, "heads": heads, "head_dim": 128,
                    "query_layout": "BTHD", "kv_layout": "BHND", "candidates": {}, "current_runs": []}
            report["cases"].append(case); save()
            graph = graph_output = None
            if name != "small_fp64_reference":
                # This captures only SDPA with fixed buffers, not offloaded DiT.
                stream = torch.cuda.Stream()
                stream.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(stream):
                    warm = baseline()
                torch.cuda.current_stream().wait_stream(stream)
                del warm
                graph = torch.cuda.CUDAGraph()
                with torch.cuda.graph(graph):
                    graph_output = baseline()
                graph.replay(); torch.cuda.synchronize()
                case["sdpa_only_cuda_graph"] = {"comparison_to_current": metrics(graph_output, reference), "runs": [],
                                                "scope": "Fixed-buffer single SDPA only; not complete model/offload capture"}
            if name == "small_fp64_reference":
                scores = (q.transpose(1, 2).double() @ k.double().transpose(-1, -2))*(128**-0.5)
                exact = (scores.softmax(-1) @ v.double()).transpose(1, 2)
                case["current_vs_fp64"] = metrics(reference.double(), exact)
                del scores
            plans, seen = {}, set()
            for label, knobs in choices:
                try:
                    plan = Plan(lib, desc, knobs, q, k, v)
                    if plan.knobs in seen:
                        plan.close(); continue
                    seen.add(plan.knobs)
                    output = plan(); torch.cuda.synchronize()
                    comparison = metrics(output, reference)
                    row = {"knobs": plan.knobs, "kernel": plan.kernel, "workspace_bytes": plan.size.value,
                           "comparison_to_current": comparison, "runs": []}
                    case["candidates"][label] = row
                    if name == "small_fp64_reference": row["comparison_to_fp64"] = metrics(output.double(), exact)
                    if not comparison["all_finite"] or comparison["relative_l2"] >= 0.02:
                        row["rejected"] = "non-finite or large error"; plan.close()
                    else:
                        plans[label] = plan
                except Exception as error:
                    case["candidates"][label] = {"error": type(error).__name__+": "+str(error)}
                save()
            if name != "small_fp64_reference":
                for _ in range(3):
                    row, output = timed(baseline); case["current_runs"].append(row); del output
                    row, _ = timed(graph.replay)
                    case["sdpa_only_cuda_graph"]["runs"].append(row)
                    for label, plan in plans.items():
                        row, output = timed(plan); case["candidates"][label]["runs"].append(row)
                    save()
                case["current_median_cuda_ms"] = statistics.median(r["cuda_ms"] for r in case["current_runs"])
                graph_ms = statistics.median(r["cuda_ms"] for r in case["sdpa_only_cuda_graph"]["runs"])
                case["sdpa_only_cuda_graph"].update(median_cuda_ms=graph_ms,
                    speedup_vs_current=case["current_median_cuda_ms"]/graph_ms)
                for label, plan in plans.items():
                    row = case["candidates"][label]
                    row["median_cuda_ms"] = statistics.median(r["cuda_ms"] for r in row["runs"])
                    row["speedup_vs_current"] = case["current_median_cuda_ms"]/row["median_cuda_ms"]
                    before = plan().clone(); after = plan(); torch.cuda.synchronize()
                    row["repeat_raw_bits_equal"] = torch.equal(before.view(torch.int16), after.view(torch.int16))
                    del before
            del reference
            q[0, :4, -1].fill_(1); k[0, -1, -1].fill_(64)
            marker = torch.arange(128, device="cuda", dtype=torch.float32).div(128).to(torch.bfloat16)
            v[0, -1, -1].copy_(marker)
            output = baseline(); torch.cuda.synchronize()
            case["current_last_head_final_kv_sentinel"] = torch.equal(output[0, :4, -1], marker.expand(4, -1)); del output
            for label, plan in plans.items():
                output = plan(); torch.cuda.synchronize()
                row = case["candidates"][label]
                row["last_head_final_kv_sentinel_passed"] = torch.equal(output[0, :4, -1], marker.expand(4, -1))
                plan.close()
            case["peak_gpu_allocated_gib"] = torch.cuda.max_memory_allocated()/2**30
            plans.clear(); del q, k, v, marker
            del graph, graph_output
            if name == "small_fp64_reference": del exact
            save(); print(json.dumps({"case": name, "current_ms": case.get("current_median_cuda_ms"),
                "candidates": {label: {key: row.get(key) for key in ("median_cuda_ms", "speedup_vs_current", "last_head_final_kv_sentinel_passed", "error")}
                               for label, row in case["candidates"].items()}}), flush=True)
    report.update(status="measured_operator_only", completed_at=time.time(), full_video_generated=False)
    save()


if __name__ == "__main__":
    main()
