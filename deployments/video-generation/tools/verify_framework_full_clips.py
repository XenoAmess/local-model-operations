#!/usr/bin/env python3
"""Verify complete IC comparison media, final latents and decoded pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def pixels(path):
    process = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
                                "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    digest = hashlib.sha256()
    for part in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(part)
    if process.wait() != 0:
        raise RuntimeError("Full media decode failed: " + str(path))
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "outputs/framework-comparison-20261117/full-video")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    import torch
    torch.set_num_threads(4)
    rows = []
    reference = reference_hash = None
    for strategy in ("current", "diffusers", "accelerate"):
        directory = args.directory / ("ic-" + strategy)
        receipt = directory / "measurement.json"
        if not receipt.exists():
            rows.append(dict(strategy=strategy, status="not_measured"))
            continue
        row = json.loads(receipt.read_text())
        if row["status"] != "completed":
            rows.append(row)
            continue
        media = directory / "result.mkv"
        row["ffprobe"] = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames",
            "-show_entries", "stream=codec_type,width,height,nb_read_frames,r_frame_rate:format=duration,size",
            "-of", "json", str(media)], text=True))
        row["decoded_rgb_sha256"] = pixels(media)
        latent = torch.load(directory / "result.latent.pt", map_location="cpu", weights_only=True)["video_latents"]
        row.update(latent_shape=list(latent.shape), latent_dtype=str(latent.dtype),
                   latent_sha256=hashlib.sha256(latent.contiguous().view(torch.uint8).numpy()).hexdigest())
        if strategy == "current":
            reference, reference_hash = latent, row["decoded_rgb_sha256"]
        row["latent_bit_equal_to_current"] = torch.equal(reference, latent) if reference is not None else None
        row["decoded_pixels_equal_to_current"] = row["decoded_rgb_sha256"] == reference_hash if reference_hash else None
        video = next(stream for stream in row["ffprobe"]["streams"] if stream["codec_type"] == "video")
        row["media_shape_verified"] = (video["width"], video["height"], int(video["nb_read_frames"])) == (2560, 1440, 124)
        rows.append(row)
    report = dict(scope="Complete IC model: 3 denoising steps, all 50 blocks, original 36L VAE; not one-block replay",
                  results=rows, all_three_completed_and_bit_equal=all(
                      row.get("status") == "completed" and row.get("media_shape_verified") and
                      row.get("latent_bit_equal_to_current") and row.get("decoded_pixels_equal_to_current") for row in rows))
    (args.directory / "ic-complete-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
