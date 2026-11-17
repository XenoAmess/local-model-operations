#!/usr/bin/env python3
"""Plan complete long-video coverage using the IC runtime's fixed 124-frame windows."""

import argparse
import json
import math


def plan_windows(total_frames, window=124, minimum_overlap=24):
    if type(total_frames) is not int or total_frames < 113:
        raise ValueError("The upstream IC reader requires at least 113 real frames")
    if not 0 < minimum_overlap < window:
        raise ValueError("Overlap must be positive and smaller than the window")
    count = max(1, math.ceil(max(0, total_frames - window) / (window - minimum_overlap)) + 1)
    last = max(0, total_frames - window)
    starts = [round(i * last / (count - 1)) for i in range(count)] if count > 1 else [0]
    boundaries = [0] + [(starts[i - 1] + window + starts[i]) // 2 for i in range(1, count)] + [total_frames]
    return [{"source_start_frame": start, "source_end_frame": min(start + window, total_frames),
             "pad_tail_frames": max(0, window - total_frames),
             "keep_global_start": boundaries[i], "keep_global_end": boundaries[i + 1],
             "keep_local_start": boundaries[i] - start, "keep_local_end": boundaries[i + 1] - start}
            for i, start in enumerate(starts)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=360)
    args = parser.parse_args()
    print(json.dumps({"fps": 24, "total_frames": args.frames, "windows": plan_windows(args.frames),
                      "model_inference_validated": False, "stitch_quality_validated": False}, indent=2))
