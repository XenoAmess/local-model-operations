#!/usr/bin/env python3
"""Group compatible IC windows so upstream loads each component once per pair."""

import argparse
import json
from pathlib import Path
import sys
import time

from h3_2k_worker import ROOT, PYTHON, complete_video, probe, process, run, write_json
from plan_h3_2k_windows import plan_windows
from h3_refiner_profiles import get_profile, ic_command
from h3_full_sequence import strategy


def prepare(folder):
    request = json.loads((folder / "request.json").read_text())
    if request["mode"] != "regenerate":
        raise ValueError("The shared queue only supports existing-video 2K regeneration")
    profile = get_profile(request["size"])
    width, height = profile.width, profile.height
    low_width, low_height = profile.low_width, profile.low_height
    source_video = Path(request["input_video"])
    metadata = probe(source_video)
    video = next(item for item in metadata["streams"] if item["codec_type"] == "video")
    frames = round(float(video.get("duration") or metadata["format"]["duration"]) * 24)
    if not 113 <= frames <= 362:
        raise ValueError("Input must be about 4.7–15.1 seconds at 24 FPS")
    if strategy(request["size"], frames) == "full_sequence":
        # The finalizer owns this entire clip, with no independent windows.
        return request, []
    plan = plan_windows(frames)
    write_json(folder / "window-plan.json", {"fps": 24, "frames": frames, "windows": plan})
    pending = []
    for index, part in enumerate(plan):
        source = folder / f"window-{index:02d}-input.mkv"
        output = profile.window_path(folder, index)
        count = part["source_end_frame"] - part["source_start_frame"]
        write_json(folder / "progress.json", {"stage": "准备同模型批量重生成", "progress": 10, "updated_at": time.time()})
        if not complete_video(source, low_width, low_height, count):
            filters = (f"fps=24,trim=start_frame={part['source_start_frame']}:end_frame={part['source_end_frame']},"
                       f"setpts=PTS-STARTPTS,scale={low_width}:{low_height}:force_original_aspect_ratio=increase,"
                       f"crop={low_width}:{low_height},setsar=1")
            run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", source_video, "-vf", filters,
                 "-an", "-c:v", "ffv1", "-threads", "2", source], folder / "worker.log")
        marker = folder / f"window-{index:02d}.complete"
        if not marker.exists() or not complete_video(output, width, height, count):
            pending.append({"input": str(source), "output": str(output), "caption": request["prompt"],
                            "folder": folder, "marker": marker, "frames": count,
                            "width": width, "height": height})
    return request, pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    folders = [Path(name) for name in json.loads(args.batch.read_text())]
    requests, windows = [], []
    for folder in folders:
        request, pending = prepare(folder)
        requests.append(request)
        windows.extend(pending)
    keys = {(r["seed"], r["sampler"], r["size"]) for r in requests}
    if len(keys) != 1:
        raise ValueError("A 2K cohort needs the same seed, sampler and orientation")
    seed, sampler, size = keys.pop()
    profile = get_profile(size)
    # Keep CPU pixel stacks bounded; never concatenate attention batches.
    for offset in range(0, len(windows), profile.max_windows_per_load):
        chunk = windows[offset:offset + profile.max_windows_per_load]
        jobs_file = args.batch.parent / f"ic-{offset:03d}.jsonl"
        jobs_file.write_text("".join(json.dumps({key: item[key] for key in ("input", "output", "caption")}) + "\n"
                                    for item in chunk))
        for item in chunk:
            write_json(item["folder"] / "progress.json", {
                "stage": f"{profile.label} 同模型计算（本次 {len(chunk)} 个窗口）", "progress": 35,
                "updated_at": time.time(), "batch_windows": len(chunk)})
        command = ic_command(jobs_file, size=size, seed=seed, sampler=sampler)
        log = args.batch.parent / "worker.log"
        run(command, log)
        for item in chunk:
            if not complete_video(item["output"], item["width"], item["height"], item["frames"]):
                raise RuntimeError("A batched IC window has incorrect dimensions or frame count")
            item["marker"].write_text("verified\n")
    for folder in folders:
        # Existing finalizer validates every window and preserves the full audio timeline.
        process(folder)
        receipt_path = folder / "result.json"
        receipt = json.loads(receipt_path.read_text())
        receipt.update(cohort_jobs=len(folders), ic_max_windows_per_load=profile.max_windows_per_load,
                       native_resolution=profile.resolution,
                       native_compute_size=f"{profile.native_width}x{profile.native_height}")
        write_json(receipt_path, receipt)


if __name__ == "__main__":
    main()
