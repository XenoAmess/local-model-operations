#!/usr/bin/env python3
"""Run the same real IC block benchmark with a selected offload implementation."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=["current", "diffusers", "diffusers-stream", "accelerate"], required=True)
    parser.add_argument("--tokens", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    import h3_ic_exact
    if args.strategy != "current":
        def place(model, device):
            import torch
            if args.strategy == "accelerate":
                from accelerate import cpu_offload
                return cpu_offload(model, execution_device=torch.device(device), offload_buffers=True,
                                   preload_module_classes=["MiniMaxH3TransformerBlock"])
            from diffusers.hooks import apply_group_offloading
            streamed = args.strategy == "diffusers-stream"
            apply_group_offloading(model, onload_device=torch.device(device), offload_device=torch.device("cpu"),
                offload_type="block_level", num_blocks_per_group=1, non_blocking=True,
                use_stream=streamed, record_stream=streamed, low_cpu_mem_usage=streamed)
            return model
        h3_ic_exact.readonly_block_offload = place
    sys.argv = [str(ROOT / "tools/benchmark_h3_ic_exact.py"), "--output", str(args.output),
                "--tokens", str(args.tokens), "--repeats", str(args.repeats), "--block-only"]
    try:
        runpy.run_path(str(ROOT / "tools/benchmark_h3_ic_exact.py"), run_name="__main__")
    finally:
        if args.output.exists():
            report = json.loads(args.output.read_text())
            report["offload_strategy"] = args.strategy
            report["versions"] = {name: importlib.metadata.version(name) for name in ("torch", "diffusers", "accelerate")}
            report["candidate_timing_key"] = "exact_io"
            report["baseline_timing_note"] = "Original unoptimized offload; compare candidate medians across strategy runs."
            args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
