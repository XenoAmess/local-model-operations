#!/usr/bin/env bash
set -euo pipefail
FASTH3_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export CUDA_HOME="$FASTH3_ROOT/tools/cuda"
export PATH="$CUDA_HOME/bin:$FASTH3_ROOT/tools/cuda-packages/bin:$FASTH3_ROOT/FastVideo/.venv/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_VISIBLE_DEVICES=0
export FASTVIDEO_H3_ADALN_TABLE="$FASTH3_ROOT/models/FastH3-V2-NVFP4/transformer/adaln_tables.pt"
export FASTVIDEO_H3_VSA_FP4=1
export FASTVIDEO_MINIMAX_H3_FUSIONS=all
export FASTVIDEO_NVFP4_MM_BACKEND=cutlass
export FASTVIDEO_H3_VAE_TILE_BATCH=8
export FASTVIDEO_H3_VAE_INT8_OVERLAY=0
export FASTVIDEO_VSA_TRITON=1
export FASTVIDEO_VSA_PTX_BLACKWELL=0
export FASTVIDEO_FA4=0
export FASTVIDEO_ATTENTION_BACKEND=VIDEO_SPARSE_ATTN_H3
export FASTVIDEO_STAGE_LOGGING=1
export HF_HUB_OFFLINE=1
export PYTHONUNBUFFERED=1
export MAX_JOBS=4
export OMP_NUM_THREADS=8
cd "$FASTH3_ROOT/FastVideo"
exec "$FASTH3_ROOT/FastVideo/.venv/bin/fastvideo" serve --config "$FASTH3_ROOT/fasth3-v2.yaml" "$@"
