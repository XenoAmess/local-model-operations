#!/usr/bin/env python3
"""Probe CPU-loaded layer streaming, then run the private native UniServe HTTP candidate."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/framework-comparison-20261117/full-video"


def probe():
    import torch
    from torch import nn
    from uniserve.nn import Linear, MergedColumnParallelLinear
    from uniserve.runtime.layer_weights import LayerWeights

    class Layer(nn.Module):
        def __init__(self):
            super().__init__()
            self.projection = MergedColumnParallelLinear(64, {"a": 192, "b": 192}, bias=True, dtype=torch.bfloat16)
            self.up = Linear(64, 192, dtype=torch.bfloat16)
            self.down = Linear(192, 64, bias=False, dtype=torch.bfloat16)

        def chunks(self, upstream):
            projected = [(value, self.projection(value)) for value in upstream]
            mixed = sum(out["a"].float().mean(0) for _, out in projected)
            for value, out in projected:
                gated = (out["b"] + mixed.to(out["b"].dtype)) * self.up(value)
                yield value + self.down(torch.tanh(gated))

    def evaluate(layers, inputs, stop=10):
        chunks = iter(inputs)
        for layer in layers[:stop]:
            chunks = layer.chunks(chunks)
        return torch.cat(list(chunks))

    with torch.inference_mode():
        torch.manual_seed(3)
        host = nn.ModuleList(Layer() for _ in range(10))
        for parameter in host.parameters():
            parameter.normal_(0, .2)
        resident = nn.ModuleList(Layer() for _ in range(10))
        resident.load_state_dict(host.state_dict())
        resident.to("cuda")
        inputs = [torch.randn(96, 64, device="cuda", dtype=torch.bfloat16) for _ in range(3)]
        expected = evaluate(resident, inputs)
        partial = evaluate(resident, inputs, 6)
        streamed = LayerWeights(host, execution_device="cuda:0")
        try:
            for parameter in host.parameters():
                if parameter.device.type == "cpu":
                    parameter.data = parameter.data.to("cuda")
            equal = [torch.equal(evaluate(host, inputs), expected) for _ in range(3)]
            partial_equal = torch.equal(evaluate(host, inputs, 6), partial)
            resumed_equal = torch.equal(evaluate(host, inputs), expected)
            report = dict(status="passed" if all(equal) and partial_equal and resumed_equal else "failed",
                          started=time.time(), scope="Ten-layer CPU-loaded streaming adapter; not a full H3 result",
                          complete_passes_equal=equal, interrupted_pass_equal=partial_equal,
                          resumed_pass_equal=resumed_equal, slots=streamed.slots,
                          copied_bytes=streamed.copied_bytes)
            (OUT / "uniserve-cpu-stream-probe.json").write_text(json.dumps(report, indent=2) + "\n")
            if report["status"] != "passed":
                raise RuntimeError("CPU-loaded streaming changes the probe output")
        finally:
            streamed.close()
        # Also exercise a CPU-streamed prefix followed by resident layers,
        # the exact placement pattern used by the text encoder candidate.
        partial_host = nn.ModuleList(Layer() for _ in range(10))
        partial_host.load_state_dict(resident.state_dict())
        for layer in partial_host[8:]:
            layer.to("cuda")
        partial_stream = LayerWeights(partial_host[:8], execution_device="cuda:0")
        try:
            for parameter in partial_host.parameters():
                if parameter.device.type == "cpu":
                    parameter.data = parameter.data.to("cuda")
            prefix_equal = [torch.equal(evaluate(partial_host, inputs), expected) for _ in range(3)]
            prefix_partial = torch.equal(evaluate(partial_host, inputs, 6), partial)
            prefix_resumed = torch.equal(evaluate(partial_host, inputs), expected)
            report["mixed_residency_prefix"] = dict(host_layers=8, resident_layers=2,
                complete_passes_equal=prefix_equal, interrupted_equal=prefix_partial, resumed_equal=prefix_resumed)
            if not (all(prefix_equal) and prefix_partial and prefix_resumed):
                report["status"] = "failed"
            (OUT / "uniserve-cpu-stream-probe.json").write_text(json.dumps(report, indent=2) + "\n")
            if report["status"] != "passed":
                raise RuntimeError("Partial CPU streaming changed the probe output")
        finally:
            partial_stream.close()
    del resident, host, expected, partial, inputs, streamed
    import gc
    gc.collect()
    torch.cuda.empty_cache()
    print("UNISERVE_CPU_STREAM_PROBE_PASSED", flush=True)


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    if "--probe-only" not in sys.argv:
        # Let the diagnostic process exit before loading the real workers.
        # Keeping its CUDA context alive consumed about 684 MiB outside the
        # native worker grants and caused a reproducible startup OOM.
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--probe-only"], check=True)
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU busy")
    source = ROOT / "tools/vendor/uniserve-candidate"
    os.environ.update(H3_UNISERVE_CPU_LOAD="1", H3_UNISERVE_TEXT_HOST_LAYERS="16", CUDA_HOME=str(ROOT / "tools/cuda"),
                      CUDA_VISIBLE_DEVICES="0", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      OMP_NUM_THREADS="8", PYTHONUNBUFFERED="1",
                      PYTORCH_ALLOC_CONF="expandable_segments:True")
    os.environ["PATH"] = ":".join((str(source / ".venv/bin"), str(ROOT / "tools/cuda/bin"), os.environ["PATH"]))
    os.environ.pop("ALL_PROXY", None)
    os.environ.pop("all_proxy", None)
    sys.path.insert(0, str(source))
    OUT.mkdir(parents=True, exist_ok=True)
    if "--probe-only" in sys.argv:
        probe()
        return
    command = [str(source / ".venv/bin/uniserve"), "serve",
               str(ROOT / "outputs/framework-comparison-20261117/uniserve-omni-local"),
               "--workers", str(ROOT / "deployment/framework-comparison-20261117/uniserve-single-gpu-host-weights.experimental.json"),
               "--served-model-name", "fasth3-omni-bf16-uniserve-candidate",
               "--host", "127.0.0.1", "--port", "18012", "--max-running-requests", "1",
               "--max-video-seconds", "5", "--max-model-len", "11264",
               "--video-text-capacities", "11264", "--max-condition-rows", "49152",
               "--video-resolutions", "768p", "--video-aspect-ratios", "16:9",
               "--mm-processor-kwargs", '{"enlarge_references":true}',
               "--quantization-config", '{"mode":"quality"}',
               "--graph-policy", "off", "--load-threads", "1", "--remote-media", "false",
               "--media-directory", "/home/ubuntu", "--watchdog-timeout", "900",
               "--max-video-job-bytes", "33554432", "--shutdown-timeout", "0"]
    print("UNISERVE_EXPERIMENTAL_CPU_LOAD native PDD8; original 36L VAE, native quality FP16 projection storage", flush=True)
    raise SystemExit(subprocess.call(command, cwd=source))


if __name__ == "__main__":
    main()
