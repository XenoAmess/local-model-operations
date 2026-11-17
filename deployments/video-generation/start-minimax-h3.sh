#!/usr/bin/env bash
set -euo pipefail
MINIMAX_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export CUDA_HOME="$MINIMAX_ROOT/tools/cuda"
export PATH="$CUDA_HOME/bin:$MINIMAX_ROOT/FastVideo/.venv/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_VISIBLE_DEVICES=0
export FASTVIDEO_SERVE_CONFIG="$MINIMAX_ROOT/minimax-h3.yaml"
# Retain the official full-rank BF16 projection weights on the host. Every
# requested timestep is computed exactly; no distilled-model table is reused.
export FASTVIDEO_H3_ADALN_CACHE=1
unset FASTVIDEO_H3_ADALN_TABLE FASTVIDEO_H3_ADALN_DUMP
export FASTVIDEO_H3_VSA_FP4=0
export FASTVIDEO_H3_VAE_INT8_OVERLAY=0
export FASTVIDEO_H3_VAE_TILE_BATCH=1
export FASTVIDEO_H3_GATE_CHUNK_ROWS=8192
export FASTVIDEO_H3_FFN_CHUNK_TOKENS=8192
export FASTVIDEO_MINIMAX_H3_FUSIONS=all
export FASTVIDEO_ATTENTION_BACKEND=TORCH_SDPA
export FASTVIDEO_FA4=0
export FASTVIDEO_STAGE_LOGGING=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONUNBUFFERED=1
export MAX_JOBS=2
export FLASHINFER_NVCC_THREADS=1
export NVCC_THREADS=1
export CMAKE_BUILD_PARALLEL_LEVEL=2
export TORCHINDUCTOR_COMPILE_THREADS=1
export OMP_NUM_THREADS=8
export TOKENIZERS_PARALLELISM=false
cd "$MINIMAX_ROOT/FastVideo"
exec "$MINIMAX_ROOT/FastVideo/.venv/bin/python" "$MINIMAX_ROOT/tools/serve_fasth3_omni.py"
