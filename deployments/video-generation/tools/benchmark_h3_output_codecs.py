#!/usr/bin/env python3
"""Bounded CPU-only codec probe using identical RGB frames from the delivered S48."""

import argparse
import json
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    directory = ROOT / "outputs/video-queue/engineering-cpu-codec-20261121"
    directory.mkdir(parents=True, exist_ok=True)
    source = ROOT / "outputs/video-queue/jobs/video_gen_505d3a78c78a42d7b933b6519e1007e9/full-sequence-4k.mkv"
    frames, width, height = 16, 3840, 2160
    raw = directory / "sample.rgb"
    report = {"status": "running", "scope": "CPU-only 16-frame prefix codec probe, not model inference, pipeline timing or output parity validation",
              "frames": frames, "width": width, "height": height, "fps": 24,
              "isolation": isolation, "gpu_model_loaded": False, "runs": {}}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    def run(command):
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.perf_counter()
        result = subprocess.run(command, capture_output=True, text=True, timeout=75)
        if result.returncode:
            raise RuntimeError(result.stderr[-1600:])
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"wall_seconds": time.perf_counter()-start,
                "cpu_seconds": after.ru_utime + after.ru_stime-before.ru_utime-before.ru_stime}

    save()
    try:
        report["decode_to_rgb"] = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-threads", "2",
            "-i", str(source), "-frames:v", str(frames), "-an", "-pix_fmt", "rgb24", "-threads", "1",
            "-f", "rawvideo", str(raw)])
        if raw.stat().st_size != frames * width * height * 3:
            raise RuntimeError("Incorrect decoded RGB frame count")
        for codec, settings, suffix in (("ffv1", ["-c:v", "ffv1", "-level", "3", "-threads", "2"], ".mkv"),
                                        ("x264", ["-c:v", "libx264", "-threads", "4", "-preset", "medium",
                                                  "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart"], ".mp4")):
            report["runs"][codec] = []
            for repeat in range(2):
                dest = directory / f"{codec}-{repeat}{suffix}"
                command = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-filter_threads", "1",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", "24",
                           "-i", str(raw), "-frames:v", str(frames), "-an", *settings, str(dest)]
                row = run(command)
                row["bytes"] = dest.stat().st_size
                report["runs"][codec].append(row)
                save()
            report[codec + "_median_seconds"] = statistics.median(x["wall_seconds"] for x in report["runs"][codec])
        report.update(status="measured_cpu_prefix_only", completed_at=time.time(),
                      full_336_frame_extrapolation_is_not_measurement=True,
                      zero_gpu_inference=True, production_changed=False)
    except Exception as error:
        report.update(status="failed_evidence_retained", error=type(error).__name__+": "+str(error))
        raise
    finally:
        save()
        raw.unlink(missing_ok=True)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
