#!/usr/bin/env python3
"""Bounded two-request experiment for 4K IC's dominant dense attention.

This measures one attention call at the real packed length, not two complete
videos. It does not change the production queue or load a second model.
"""
import argparse
import fcntl
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokens", type=int, default=345843)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU busy; do not overlap this test with model inference")
    import torch
    from torch.nn.attention import SDPBackend, sdpa_kernel
    torch.set_num_threads(8)
    torch.cuda.set_per_process_memory_fraction(.80)
    report = dict(started=time.time(), status="running", torch=torch.__version__,
                  gpu=torch.cuda.get_device_name(), tokens=args.tokens, heads=56, head_dim=128,
                  dtype="bfloat16", backend="PyTorch FLASH_ATTENTION (FA2)",
                  scope="Two distinct synthetic inputs, one real-4K-length attention call each; NOT full videos",
                  runs={})
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    save()
    torch.manual_seed(74291)
    with torch.inference_mode(), sdpa_kernel(SDPBackend.FLASH_ATTENTION):
        # Allocate the two input batches once; item views avoid an extra 30 GB
        # concatenation when comparing the batch-2 path.
        q, k, v = [torch.randn(2, args.tokens, 56, 128, device="cuda", dtype=torch.bfloat16) for _ in range(3)]

        def one(index):
            return torch.nn.functional.scaled_dot_product_attention(
                q[index:index+1].transpose(1, 2), k[index:index+1].transpose(1, 2),
                v[index:index+1].transpose(1, 2)).transpose(1, 2)

        expected = [one(index) for index in range(2)]
        torch.cuda.synchronize()
        streams = [torch.cuda.Stream(), torch.cuda.Stream()]
        for mode in ("serial", "two_streams", "batch_two"):
            rows = []
            for repeat in range(args.repeats + 1):
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                main_stream = torch.cuda.current_stream()
                base = torch.cuda.Event(enable_timing=True)
                done = [torch.cuda.Event(enable_timing=True) for _ in range(2)]
                start = time.monotonic()
                base.record(main_stream)
                if mode == "serial":
                    outputs = []
                    for i in range(2):
                        outputs.append(one(i))
                        done[i].record(main_stream)
                elif mode == "two_streams":
                    outputs = []
                    for i, stream in enumerate(streams):
                        stream.wait_stream(main_stream)
                        with torch.cuda.stream(stream):
                            outputs.append(one(i))
                            done[i].record(stream)
                    for stream in streams:
                        main_stream.wait_stream(stream)
                else:
                    batch = torch.nn.functional.scaled_dot_product_attention(
                        q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2)).transpose(1, 2)
                    outputs = [batch[0:1], batch[1:2]]
                    for event in done:
                        event.record(main_stream)
                torch.cuda.synchronize()
                elapsed = time.monotonic() - start
                peak = torch.cuda.max_memory_allocated()
                equal = [torch.equal(actual, reference) for actual, reference in zip(outputs, expected)]
                row = dict(repeat=repeat, pair_wall_s=elapsed, bit_equal=equal,
                           job_completion_s=[base.elapsed_time(event) / 1000 for event in done],
                           peak_gpu_allocated_bytes=peak,
                           peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved())
                rows.append(row)
                report["runs"][mode] = rows
                save()
                print(mode, json.dumps(row), flush=True)
                del outputs
                if mode == "batch_two":
                    del batch
            torch.cuda.empty_cache()
        reference_s = statistics.median(row["pair_wall_s"] for row in report["runs"]["serial"][1:])
        report["summary"] = {mode: dict(
            pair_median_s=statistics.median(row["pair_wall_s"] for row in rows[1:]),
            throughput_ratio_vs_serial=reference_s / statistics.median(row["pair_wall_s"] for row in rows[1:]),
            all_bit_equal=all(all(row["bit_equal"]) for row in rows),
            peak_gpu_allocated_gib=max(row["peak_gpu_allocated_bytes"] for row in rows) / 2**30)
            for mode, rows in report["runs"].items()}
        report.update(status="measured_attention_only", finished=time.time())
        save()


if __name__ == "__main__":
    main()
