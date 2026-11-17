"""Prove storage-only IC changes retain each original operation and its results."""

from pathlib import Path
import sys
import unittest

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "models/Open-H3-Regenerate-2K-IC/infer"))
from h3_ic_exact import chunk_forward_preallocated, precast_lora_compute_weights, readonly_block_offload
from h3_ic_runtime import chunk_forward
from ref2va_ic.lora import LoRALinear


class ExactIOTest(unittest.TestCase):
    def test_preallocation_keeps_gemm_shapes_and_bits_including_tail_and_batches(self):
        torch.manual_seed(1234)
        first = torch.nn.Linear(16, 64).bfloat16()
        second = torch.nn.Linear(32, 16).bfloat16()
        shapes = []

        def original(x):
            shapes.append(tuple(x.shape))
            value, gate = first(x).chunk(2, dim=-1)
            return second(torch.nn.functional.silu(gate) * value)

        with torch.inference_mode():
            for batch in (1, 2):
                for length in (1, 8, 9, 31, 65):
                    x = torch.randn(batch, length, 16).bfloat16()
                    baseline = chunk_forward(original, size=8)(x)
                    before = list(shapes)
                    shapes.clear()
                    result = chunk_forward_preallocated(original, size=8)(x)
                    self.assertTrue(torch.equal(result, baseline))
                    self.assertEqual(shapes, before)
                    shapes.clear()
                    self.assertTrue(result.is_contiguous())

    def test_lora_cast_cache_preserves_unmerged_math_and_rejects_other_dtypes(self):
        torch.manual_seed(1234)
        module = LoRALinear(torch.nn.Linear(16, 24, bias=False).bfloat16(),
                            torch.randn(8, 16), torch.randn(24, 8), 1.)
        x = torch.randn(2, 31, 16).bfloat16()
        with torch.inference_mode():
            expected = module(x)
            report = precast_lora_compute_weights(module)
            self.assertEqual(report["linears"], 1)
            self.assertFalse(report["lora_merged"])
            self.assertTrue(torch.equal(module(x), expected))
            with self.assertRaisesRegex(RuntimeError, "original BF16"):
                module(x.float())

    def test_offload_restores_original_host_storage_after_success_and_failure(self):
        class Block(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = torch.nn.Linear(4, 4)
                self.register_buffer("bias", torch.ones(4))
                self.fail = False

            def forward(self, x):
                if self.fail:
                    raise ValueError("deliberate diagnostic")
                return self.linear(x) + self.bias

        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.transformer_blocks = torch.nn.ModuleList([Block()])

            def forward(self, x):
                return self.transformer_blocks[0](x)

        model = Model().requires_grad_(False).eval()
        pointers = [p.data_ptr() for p in model.parameters()]
        values = [p.detach().clone() for p in model.parameters()]
        x = torch.randn(2, 4)
        with torch.inference_mode():
            expected = model(x)
            readonly_block_offload(model, "cpu")
            for _ in range(3):
                self.assertTrue(torch.equal(model(x), expected))
                self.assertEqual([p.data_ptr() for p in model.parameters()], pointers)
            model.transformer_blocks[0].fail = True
            with self.assertRaises(ValueError):
                model(x)
        self.assertEqual([p.data_ptr() for p in model.parameters()], pointers)
        self.assertTrue(all(torch.equal(p, v) for p, v in zip(model.parameters(), values)))


if __name__ == "__main__":
    unittest.main()
