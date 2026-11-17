#!/usr/bin/env python3
"""Run one complete native IC clip with a selected offload controller."""
import argparse
import fcntl
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("current", "diffusers", "accelerate"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU busy")
    import h3_ic_exact
    import torch
    torch.cuda.set_per_process_memory_fraction(.94)
    def progress(model):
        step = {"number": 0}
        def begin(module, inputs):
            step["number"] += 1
            print(f"IC {args.strategy} denoising step {step['number']} started", flush=True)
        model.register_forward_pre_hook(begin)
        for index, block in enumerate(model.transformer_blocks):
            if index % 10 == 0:
                def entered(module, inputs, block_index=index):
                    print(f"IC {args.strategy} step {step['number']}: block {block_index+1}/50", flush=True)
                block.register_forward_pre_hook(entered)
        return model
    if args.strategy == "accelerate":
        def place(model, device):
            from accelerate import cpu_offload
            return progress(cpu_offload(model, execution_device=torch.device(device), offload_buffers=True,
                                        preload_module_classes=["MiniMaxH3TransformerBlock"]))
        h3_ic_exact.readonly_block_offload = place
    elif args.strategy == "diffusers":
        def place(model, device):
            from diffusers.hooks import apply_group_offloading
            apply_group_offloading(model, onload_device=torch.device(device), offload_device=torch.device("cpu"),
                                  offload_type="block_level", num_blocks_per_group=1, non_blocking=True)
            return progress(model)
        h3_ic_exact.readonly_block_offload = place
    args.output_dir.mkdir(parents=True, exist_ok=True)
    request = json.loads(args.request.read_text())
    jobs = args.output_dir / "jobs.jsonl"
    output = args.output_dir / "result.mkv"
    jobs.write_text(json.dumps(dict(input=str(args.input.resolve()), output=str(output.resolve()),
                                    caption=request["prompt"])) + "\n")
    report = dict(strategy=args.strategy, started=time.time(), size="2560x1440", sampler="up3", seed=request["seed"],
                  steps=3, precision="BF16 DiT, unmerged IC LoRA, original 36L FP32 tiled VAE",
                  scope="Complete IC clip: encode, load, 3 denoising steps and original decoder", status="running")
    receipt = args.output_dir / "measurement.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    started = time.monotonic()
    try:
        sys.argv = [str(ROOT / "tools/h3_ic_runtime.py"), "--jobs", str(jobs), "--size", "2560x1440",
                    "--sampler", "up3", "--seed", str(request["seed"]), "--exact-io", "--save-latent"]
        runpy.run_path(str(ROOT / "tools/h3_ic_runtime.py"), run_name="__main__")
        report.update(status="completed", wall_s=time.monotonic()-started,
                      peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
                      peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved())
    except BaseException as error:
        report.update(status="failed", wall_s=time.monotonic()-started, error=type(error).__name__+": "+str(error))
        raise
    finally:
        report["finished"] = time.time()
        receipt.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
