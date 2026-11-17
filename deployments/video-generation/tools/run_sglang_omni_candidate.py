#!/usr/bin/env python3
"""Start the isolated, loopback-only SGLang BF16 comparison server."""
import fcntl
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    lease = (ROOT / "outputs/h3-2k-gpu.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU busy; candidate must run alone")
    os.environ.update(CUDA_HOME=str(ROOT / "tools/cuda"), CUDA_VISIBLE_DEVICES="0",
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="8",
                      SGLANG_DIFFUSION_TEST_CAP_DEVICE_MEMORY_GIB="79",
                      PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    os.environ["PATH"] = str(Path(sys.executable).parent) + ":" + str(ROOT / "tools/cuda/bin") + ":" + os.environ["PATH"]
    # The candidate Hub client lacks the optional SOCKS extra. Offline loading
    # must not construct a SOCKS transport just by inheriting ALL_PROXY.
    os.environ.pop("ALL_PROXY", None)
    os.environ.pop("all_proxy", None)
    sys.path.insert(0, str(ROOT / "tools/vendor/sglang-candidate/python"))
    # Child workers inherit this explicitly; production import paths stay intact.
    os.environ["PYTHONPATH"] = str(ROOT / "tools/vendor/sglang-candidate/python")
    checkpoint = ROOT / "outputs/framework-comparison-20261117/FastH3-Omni-BF16-native-candidate"
    sys.argv = ["sglang", "serve", "--model-path", str(checkpoint), "--num-gpus", "1",
                "--model-id", "FastVideo-FastH3-Omni-8-Step-V1",
                "--host", "127.0.0.1", "--port", "18011", "--backend", "sglang",
                "--performance-mode", "memory",
                "--component-attention-backends", "transformer=video_sparse_attn_h3",
                "--attention-backend-config", '{"VSA_sparsity":0.9,"vsa_tile_size":128,"vsa_ref_keep_rate":0.1}',
                "--layerwise-offload-components", "dit,text_encoder,vae",
                "--dit-layerwise-resident-layers", "36",
                "--layerwise-resident-layers", "video_vae=36",
                "--component-precisions.video_vae", "fp32",
                "--component-precisions.audio_vae", "fp32",
                "--enable-torch-compile", "false", "--warmup-mode", "off"]
    from sglang.multimodal_gen.runtime.entrypoints.cli import serve as entry
    from sglang.multimodal_gen.configs.pipeline_configs.minimax_h3 import FastH3OmniPipelineConfig
    dispatch = entry.dispatch_launch
    def verified_dispatch(args):
        print("CANDIDATE_PIPELINE_CONFIG", type(args.pipeline_config).__name__,
              args.component_attention_backends, flush=True)
        if not isinstance(args.pipeline_config, FastH3OmniPipelineConfig):
            raise RuntimeError("Wrong pipeline config; refusing an invalid comparison")
        return dispatch(args)
    entry.dispatch_launch = verified_dispatch
    runpy.run_module("sglang.cli.main", run_name="__main__")


if __name__ == "__main__":
    main()
