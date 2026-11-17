#!/usr/bin/env bash
set -euo pipefail
H3_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export CUDA_HOME="$H3_ROOT/tools/cuda"
export PATH="$CUDA_HOME/bin:$H3_ROOT/.venv-h3-2k/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_VISIBLE_DEVICES=0
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
# Validated against the original IC block at 344064 tokens, with bitwise parity.
export H3_IC_EXACT_IO="${H3_IC_EXACT_IO:-1}"
export MAX_JOBS=2 FLASHINFER_NVCC_THREADS=1 NVCC_THREADS=1 TORCHINDUCTOR_COMPILE_THREADS=1
export CMAKE_BUILD_PARALLEL_LEVEL=2 OMP_NUM_THREADS=8 TOKENIZERS_PARALLELISM=false
cd "$H3_ROOT"
exec "$H3_ROOT/.venv-h3-2k/bin/python" "$@"
