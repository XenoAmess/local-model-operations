#!/usr/bin/env python3
"""Run the unchanged production BF16 configuration on a private benchmark port."""
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
        raise RuntimeError("GPU busy")
    import yaml
    out = ROOT / "outputs/framework-comparison-20261117/steady/fastvideo"
    out.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load((ROOT / "fasth3-omni-bf16.yaml").read_text())
    config["server"].update(host="127.0.0.1", port=18013, output_dir=str(out / "api"))
    path = out / "private-server.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    os.environ.update(CUDA_HOME=str(ROOT / "tools/cuda"), CUDA_VISIBLE_DEVICES="0",
        FASTVIDEO_SERVE_CONFIG=str(path), FASTVIDEO_H3_ADALN_CACHE="1", FASTVIDEO_H3_VSA_FP4="0",
        FASTVIDEO_H3_VSA_FINE_ATTENTION="emulator-bf16", FASTVIDEO_ATTENTION_BACKEND="VIDEO_SPARSE_ATTN_H3",
        FASTVIDEO_VSA_TRITON="1", FASTVIDEO_VSA_PTX_BLACKWELL="0", FASTVIDEO_FA4="0",
        FASTVIDEO_MINIMAX_H3_FUSIONS="all", FASTVIDEO_H3_GATE_CHUNK_ROWS="8192",
        FASTVIDEO_H3_FFN_CHUNK_TOKENS="16384", FASTVIDEO_STAGE_LOGGING="1", FASTVIDEO_H3_SP_PROFILE="0",
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="8")
    for name in ("FASTVIDEO_H3_ADALN_TABLE", "FASTVIDEO_H3_ADALN_DUMP", "FASTVIDEO_H3_VAE_NVFP4_DECODER"):
        os.environ.pop(name, None)
    os.environ["PATH"] = str(ROOT / "tools/cuda/bin") + ":" + str(ROOT / "FastVideo/.venv/bin") + ":" + os.environ["PATH"]
    os.environ["LD_LIBRARY_PATH"] = str(ROOT / "tools/cuda/lib64") + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    runpy.run_path(str(ROOT / "tools/serve_fasth3_omni.py"), run_name="__main__")


if __name__ == "__main__":
    main()
