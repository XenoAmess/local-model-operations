#!/usr/bin/env python3
"""Check the unquantized tile-128 VSA kernel on this GPU before full-model inference."""

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    import torch
    from fastvideo.attention.backends.fp4_vsa_qat import load_qat_vsa_modules
    reference, kernel = load_qat_vsa_modules()
    torch.manual_seed(1234)
    torch.cuda.set_per_process_memory_fraction(.03)
    q, k, v = [torch.randn(1, 2, 512, 128, dtype=torch.bfloat16, device="cuda") for _ in range(3)]
    mask = torch.rand(1, 2, 4, 4, device="cuda") < .4
    mask[..., 0] = True
    valid = torch.full((4,), 128, dtype=torch.int32, device="cuda")
    indices, counts, valid = reference.tile128_mask_to_fp4_blocks(mask, valid)
    with torch.inference_mode():
        result = kernel.fp4_vsa_attn_qat(q, k, v, indices, counts, valid, quantize=False)
        wanted = reference.fp4_vsa_attention_reference(q, k, v, indices, counts, valid, quantize=False)
        delta = result.float() - wanted.float()
        torch.testing.assert_close(result.float(), wanted.float(), atol=.004, rtol=.02)
    report = {"status": "passed", "time": time.time(), "gpu": torch.cuda.get_device_name(),
              "dtype": "bfloat16", "attention_quantized": False, "tile_size": 128,
              "max_abs_error_vs_float_reference": delta.abs().max().item(),
              "relative_rmse": (delta.square().mean() / wanted.float().square().mean()).sqrt().item()}
    (ROOT / "deployment/omni-bf16/attention-preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
