#!/usr/bin/env python3
"""Check the actual GPU provider for Omni's trained VSA tile before loading."""
from collections.abc import Mapping
import dataclasses
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def serializable(value):
    if dataclasses.is_dataclass(value):
        return {field.name: serializable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU busy")
    os.environ.update(HF_HUB_OFFLINE="1", CUDA_VISIBLE_DEVICES="0")
    os.environ.pop("ALL_PROXY", None)
    os.environ.pop("all_proxy", None)
    sys.path.insert(0, str(ROOT / "tools/vendor/uniserve-candidate"))
    import torch
    from uniserve_models import loading
    from uniserve_models.minimax_h3 import weight_config
    from uniserve.runtime.backends.attention import vsa
    config = loading.read_config(ROOT / "outputs/framework-comparison-20261117/uniserve-omni-local")
    weights = weight_config(config.model)
    report = dict(started=time.time(), torch=torch.__version__, gpu=torch.cuda.get_device_name(),
                  capability=list(torch.cuda.get_device_capability()), config=serializable(config.model),
                  versions={name: importlib.metadata.version(name) for name in ("torch", "diffusers", "flashinfer-python", "uniserve-kernels")},
                  source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT / "tools/vendor/uniserve-candidate", text=True).strip(),
                  scope="Real GPU backend selection, real checkpoint configuration and meta-device memory budget; no full-video timing")
    with torch.device("meta"):
        model = config.model_class(config.model)
    sizes = {}
    for name, parameter in model.named_parameters():
        component = name.split(".")[0]
        choices = [(len(prefix), dtype) for prefix, dtype in weights.dtypes.items()
                   if name == prefix or name.startswith(prefix + ".")]
        dtype = max(choices, default=(-1, weights.dtype), key=lambda item: item[0])[1]
        sizes[component] = sizes.get(component, 0) + parameter.numel() * torch.empty((), dtype=dtype).element_size()
    report["parameter_gib_by_component"] = {name: size / 2**30 for name, size in sizes.items()}
    report["provider_tests"] = {}
    for tile in (128, 64):
        try:
            provider = vsa.resolve("auto", device=torch.device("cuda", 0), tile=tile)
            report["provider_tests"][str(tile)] = dict(status="available", provider=provider.name)
        except Exception as error:
            report["provider_tests"][str(tile)] = dict(status="unavailable", error=type(error).__name__ + ": " + str(error))
    report.update(status="trained_tile_unsupported" if report["provider_tests"]["128"]["status"] == "unavailable"
                  else "trained_tile_available_not_yet_benchmarked", finished=time.time())
    output = ROOT / "outputs/framework-comparison-20261117/uniserve-gpu-probe.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "gpu", "parameter_gib_by_component", "provider_tests")}), flush=True)


if __name__ == "__main__":
    main()
