"""Check that bounded FFN execution preserves results and has no stateful cache."""

import importlib.util
from pathlib import Path
import sys
import unittest

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

SPEC = importlib.util.spec_from_file_location(
    "h3_ic_runtime", Path(__file__).resolve().parents[1] / "tools/h3_ic_runtime.py")
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


class ChunkingTest(unittest.TestCase):
    def test_swiglu_chunking_matches_unchunked_feed_forward(self):
        torch.manual_seed(1234)
        first, second = torch.nn.Linear(16, 64), torch.nn.Linear(32, 16)

        def original(value):
            gate, hidden = first(value).chunk(2, dim=-1)
            return second(torch.nn.functional.silu(gate) * hidden)

        bounded = RUNTIME.chunk_forward(original, size=8)
        with torch.inference_mode():
            for length in [1, 8, 9, 31, 65]:
                x = torch.randn(2, length, 16)
                torch.testing.assert_close(bounded(x), original(x), atol=1e-6, rtol=1e-5)


if __name__ == "__main__":
    unittest.main()
