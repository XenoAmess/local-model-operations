#!/usr/bin/env python3
"""Run one official BF16 H3 reference-generation stage and release every model on exit."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    os.environ.update({"FASTVIDEO_H3_ADALN_CACHE": "1", "FASTVIDEO_H3_FFN_CHUNK_TOKENS": "8192",
                       "FASTVIDEO_MINIMAX_H3_FUSIONS": "all", "FASTVIDEO_ATTENTION_BACKEND": "TORCH_SDPA",
                       "FASTVIDEO_FA4": "0", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    os.environ.pop("FASTVIDEO_H3_ADALN_TABLE", None)
    os.environ.pop("FASTVIDEO_H3_ADALN_DUMP", None)
    from fastvideo import VideoGenerator
    from fastvideo.api import GenerationRequest, InputConfig, OutputConfig, SamplingConfig
    from fastvideo.api.parser import load_serve_config
    from fastvideo.pipelines.basic.minimax_h3 import MiniMaxH3Reference
    request = json.loads(args.request.read_text())
    references = [MiniMaxH3Reference(source=entry["path"], media_type=entry["kind"])
                  for entry in request["references"]]
    frames = 17 * ((int(request["seconds"]) * 24 - 5 + 16) // 17) + 5
    height, width = (1344, 768) if request["size"] == "1440x2560" else (768, 1344)
    generator = VideoGenerator.from_config(load_serve_config(ROOT / "minimax-h3.yaml").generator)
    try:
        result = generator.generate(GenerationRequest(
            prompt=request["prompt"], negative_prompt="", inputs=InputConfig(references=references),
            sampling=SamplingConfig(height=height, width=width, num_frames=frames, fps=24,
                                    num_inference_steps=50, guidance_scale=1.0, batch_cfg=False,
                                    seed=request["seed"]),
            output=OutputConfig(output_path=str(args.output.resolve()), save_video=True, return_frames=False)))
        print("H3-Base completed:", result.video_path, flush=True)
    finally:
        generator.shutdown()


if __name__ == "__main__":
    main()
