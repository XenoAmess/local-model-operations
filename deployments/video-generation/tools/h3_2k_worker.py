#!/usr/bin/env python3
"""Checkpointed full-H3 -> local IC -> frame-exact 2K video pipeline."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from plan_h3_2k_windows import plan_windows
from h3_refiner_profiles import get_profile, ic_command
from h3_full_sequence import padded_frames, strategy

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv-h3-2k/bin/python"


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)
    ], text=True))


def complete_video(path, width=None, height=None, frames=None):
    try:
        video = next(item for item in probe(path)["streams"] if item["codec_type"] == "video")
        return ((width is None or video["width"] == width) and (height is None or video["height"] == height)
                and (frames is None or int(video["nb_read_frames"]) == frames))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration):
        return False


def run(command, log):
    with log.open("ab") as stream:
        result = subprocess.run([str(part) for part in command], stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 4000))
            tail = stream.read().decode(errors="replace")
        raise RuntimeError(f"Stage failed ({result.returncode}): {tail[-2500:]}")


def stitch_command(job_dir, draft, plan, frames, size="2560x1440"):
    profile = get_profile(size)
    command = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    for index in range(len(plan)):
        command += ["-i", str(profile.window_path(job_dir, index))]
    command += ["-i", str(draft)]
    graph = ";".join(f"[{i}:v]trim=start_frame={part['keep_local_start']}:end_frame={part['keep_local_end']},"
                     f"setpts=PTS-STARTPTS[v{i}]" for i, part in enumerate(plan))
    graph += ";" + "".join(f"[v{i}]" for i in range(len(plan))) + f"concat=n={len(plan)}:v=1:a=0[out]"
    command += ["-filter_complex", graph, "-map", "[out]", "-map", f"{len(plan)}:a:0?",
                "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-r", "24", "-frames:v", str(frames),
                "-t", str(frames / 24), "-movflags", "+faststart", str(job_dir / "result.mp4")]
    return command


def process_full_sequence(job_dir, request, draft, frames):
    """One source, one denoising trajectory, one decode; never falls back to stitching."""
    profile = get_profile(request["size"])
    log = job_dir / "worker.log"
    plan = {"fps": 24, "frames": frames, "processing_frames": padded_frames(frames),
            "latent_frames": (padded_frames(frames) - 5) // 17 * 5 + 2,
            "temporal_strategy": "full_sequence", "global_attention": True, "windows": 1, "hard_cuts": 0}
    write_json(job_dir / "full-sequence-plan.json", plan)
    output = job_dir / "full-sequence-4k.mkv"
    marker = job_dir / "full-sequence.complete"
    if not marker.exists() or not complete_video(output, profile.width, profile.height, frames):
        write_json(job_dir / "progress.json", {"stage": "准备完整时间轴 4K 重生成", "progress": 10,
                                               "updated_at": time.time(), **plan})
        jobs = job_dir / "full-sequence.jsonl"
        jobs.write_text(json.dumps({"input": str(draft), "output": str(output), "caption": request["prompt"]},
                                   ensure_ascii=False) + "\n")
        run(ic_command(jobs, size=request["size"], seed=request["seed"], sampler=request["sampler"], full_frames=frames), log)
        if not complete_video(output, profile.width, profile.height, frames):
            raise RuntimeError("Full-sequence output failed frame/dimension validation; no window fallback")
        marker.write_text("verified full sequence\n")
    write_json(job_dir / "progress.json", {"stage": "保存完整视频与源音轨", "progress": 97, "updated_at": time.time()})
    final = job_dir / "result.mp4"
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", output, "-i", draft,
         "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-threads", "4", "-preset", "medium",
         "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-r", "24",
         "-frames:v", str(frames), "-t", str(frames / 24), "-movflags", "+faststart", final], log)
    if not complete_video(final, profile.width, profile.height, frames):
        raise RuntimeError("Full-sequence final video has incorrect geometry")
    write_json(job_dir / "result.json", {**plan, "width": profile.width, "height": profile.height,
               "duration": frames / 24, "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
               "model": request.get("model", "open-h3-2k"), "mode": request["mode"],
               "refiner_base": "official full BF16 Ref2VA", "refiner": "Open-H3-Regenerate-2K-IC",
               "sampler": request["sampler"], "decoder_layers": 36, "decoder_dtype": "FP32",
               "attention": "dense_full_sequence_query_chunked", "cpu_weight_offload": True,
               "independent_window_fallback": False, "cloud_used": False})
    write_json(job_dir / "progress.json", {"stage": "生成完成", "progress": 100, "updated_at": time.time()})


def process(job_dir):
    request = json.loads((job_dir / "request.json").read_text())
    caption = request["prompt"]
    profile = get_profile(request["size"])
    width, height = profile.width, profile.height
    portrait = height > width
    low_width, low_height = profile.low_width, profile.low_height
    log = job_dir / "worker.log"

    def state(stage, progress, **extra):
        write_json(job_dir / "progress.json", {"stage": stage, "progress": progress,
                                                "updated_at": time.time(), **extra})

    if request["mode"] == "generate":
        draft = job_dir / "draft.mp4"
        if not (job_dir / "draft.complete").exists() or not complete_video(draft):
            state("正在使用完整 H3 生成草稿", 5)
            run([PYTHON, ROOT / "tools/h3_base_runtime.py", "--request", job_dir / "request.json",
                 "--output", draft], log)
            if not complete_video(draft):
                raise RuntimeError("H3-Base did not produce a readable draft")
            (job_dir / "draft.complete").write_text("verified\n")
        frames = request["seconds"] * 24
    else:
        draft = Path(request["input_video"])
        metadata = probe(draft)
        video = next(item for item in metadata["streams"] if item["codec_type"] == "video")
        frames = round(float(video.get("duration") or metadata["format"]["duration"]) * 24)
    if not 113 <= frames <= 362:
        raise ValueError("Input must contain about 4.7–15.1 seconds at 24 FPS")
    if strategy(request["size"], frames) == "full_sequence":
        process_full_sequence(job_dir, request, draft, frames)
        return
    plan = plan_windows(frames)
    write_json(job_dir / "window-plan.json", {"fps": 24, "frames": frames, "windows": plan})
    for index, part in enumerate(plan):
        source = job_dir / f"window-{index:02d}-input.mkv"
        output = profile.window_path(job_dir, index)
        expected_frames = part["source_end_frame"] - part["source_start_frame"]
        if not complete_video(source, low_width, low_height, expected_frames):
            state(f"准备重生成片段 {index + 1}/{len(plan)}", 15 + index * 70 // len(plan))
            filters = (f"fps=24,trim=start_frame={part['source_start_frame']}:end_frame={part['source_end_frame']},"
                       f"setpts=PTS-STARTPTS,scale={low_width}:{low_height}:force_original_aspect_ratio=increase,"
                       f"crop={low_width}:{low_height},setsar=1")
            run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", draft, "-vf", filters,
                 "-an", "-c:v", "ffv1", "-threads", "2", source], log)
        if not (job_dir / f"window-{index:02d}.complete").exists() or not complete_video(output, width, height, expected_frames):
            state(f"本地 {profile.label} 重生成 {index + 1}/{len(plan)}", 20 + index * 65 // len(plan))
            jobs = job_dir / f"window-{index:02d}.jsonl"
            jobs.write_text(json.dumps({"input": str(source), "output": str(output), "caption": caption}) + "\n")
            command = ic_command(jobs, size=request["size"], seed=request["seed"], sampler=request["sampler"])
            run(command, log)
            if not complete_video(output, width, height, expected_frames):
                raise RuntimeError(f"{profile.label} window {index + 1} has incorrect resolution or frame count")
            (job_dir / f"window-{index:02d}.complete").write_text("verified\n")
    state("对齐时间轴并保存完整音轨", 92)
    final = job_dir / "result.mp4"
    run(stitch_command(job_dir, draft, plan, frames, request["size"]), log)
    if not complete_video(final, width, height, frames):
        raise RuntimeError(f"Final {profile.label} video has an incorrect resolution or timeline")
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    write_json(job_dir / "result.json", {"width": width, "height": height, "frames": frames, "fps": 24,
                                         "duration": frames / 24, "sha256": digest, "windows": len(plan),
                                         "model": request.get("model", "minimax-h3-2k"), "mode": request["mode"],
                                         "draft_model": "official full BF16 Ref2VA" if request["mode"] == "generate" else "caller-supplied draft",
                                         "refiner_base": "official full BF16 Ref2VA",
                                         "refiner": "Open-H3-Regenerate-2K-IC", "cloud_used": False})
    state("生成完成", 100)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    try:
        process(args.job_dir.resolve())
    except Exception as error:
        write_json(args.job_dir / "error.json", {"type": type(error).__name__, "message": str(error),
                                                "time": time.time()})
        raise


if __name__ == "__main__":
    main()
