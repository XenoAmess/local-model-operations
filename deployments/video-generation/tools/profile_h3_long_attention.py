#!/usr/bin/env python3
"""Profile the deployed attention call shape, not a full DiT layer or video."""

import fcntl
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    directory = ROOT / "outputs/video-queue/engineering-tests-after-S42-20261121"
    delivery = json.loads((directory / "delivery-verification.json").read_text())
    assert delivery["full_decode"]
    import requests
    client = requests.Session()
    client.trust_env = False
    queue = client.get("http://127.0.0.1:8002/v1/queue", timeout=10).json()
    assert queue["maintenance"]["enabled"] and queue["maintenance"]["upgrade_id"] == "engineering-tests-after-S42-20261121"
    assert not queue["running"] and not queue["scheduler"]["running_jobs"] and not queue["recovery"]["paused"]
    lock = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
    import torch
    import torch.nn.functional as F
    from torch.nn.attention import SDPBackend, sdpa_kernel
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.cuda.set_per_process_memory_fraction(0.75)
    torch.manual_seed(20261121)
    q = torch.randn((1, 16384, 56, 128), device="cuda", dtype=torch.bfloat16)
    k = torch.randn((1, 56, 949232, 128), device="cuda", dtype=torch.bfloat16)
    v = torch.randn_like(k)

    def call():
        with sdpa_kernel(SDPBackend.FLASH_ATTENTION):
            return F.scaled_dot_product_attention(q.transpose(1, 2), k, v, dropout_p=0, is_causal=False)

    def timed(fn):
        torch.cuda.synchronize()
        begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        started = time.perf_counter()
        begin.record()
        result = fn()
        end.record()
        end.synchronize()
        return {"cuda_ms": begin.elapsed_time(end), "wall_ms": 1000 * (time.perf_counter()-started)}, result

    report = {"status": "running", "scope": "Synthetic inputs at deployed long SDPA call geometry; not complete layer or video profiling",
              "q_tokens": 16384, "kv_tokens": 949232, "heads": 56, "head_dim": 128, "dtype": "BF16",
              "torch": torch.__version__, "isolation": isolation, "runs": []}
    with torch.inference_mode():
        output = call()
        torch.cuda.synchronize()
        del output
        for _ in range(3):
            row, output = timed(call)
            report["runs"].append(row)
            del output
        # Traced wall time is deliberately not used as the benchmark result.
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]) as prof:
            output = call()
            torch.cuda.synchronize()
        del output
        prof.export_chrome_trace(str(directory / "current-flash-long-trace.json"))
        report["profile_events"] = [{"name": e.key, "count": e.count,
             "self_cpu_us": e.self_cpu_time_total,
             "self_device_us": getattr(e, "self_device_time_total", 0),
             "device_us": getattr(e, "device_time_total", 0)} for e in prof.key_averages()]
        report["attention_median_cuda_ms"] = statistics.median(r["cuda_ms"] for r in report["runs"])
        report["attention_median_wall_ms"] = statistics.median(r["wall_ms"] for r in report["runs"])
        # Transfer throughput only: this is not a measurement of real-layer overlap.
        report["h2d_probe"] = {"bytes": 256 * 1024**2, "runs": {}}
        for pinned in (False, True):
            host = torch.empty(256 * 1024**2, dtype=torch.uint8, pin_memory=pinned).fill_(17)
            target = torch.empty_like(host, device="cuda")
            target.copy_(host, non_blocking=True)
            torch.cuda.synchronize()
            rows = []
            for _ in range(3):
                row, _ = timed(lambda: target.copy_(host, non_blocking=True))
                rows.append(row)
            report["h2d_probe"]["runs"]["pinned" if pinned else "pageable"] = rows
            del host, target
    report.update(status="measured_representative_operator_and_synthetic_h2d", production_changed=False,
                  complete_layer_profile=False, real_weight_copy_overlap_measured=False, completed_at=time.time())
    path = ROOT / "deployment/minimax-h3/long-attention-profile-20261121.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
