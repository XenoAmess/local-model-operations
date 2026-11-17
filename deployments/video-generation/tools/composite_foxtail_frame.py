"""Keep a foxtail in front of a fixed white border in a generated video."""

import argparse
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np


def compose(frame, border_width=80, vertical_offset=0):
    # Remove the model's thin baked-in frame before adding a stable wider one.
    # Keep the aspect ratio while giving the foreground room to reach the canvas edge.
    height, width = frame.shape[:2]
    crop_width = width - 48
    crop_height = round(crop_width * height / width)
    top = (height - crop_height) // 2
    frame = cv2.resize(frame[top:top + crop_height, 24:24 + crop_width], (width, height), interpolation=cv2.INTER_LANCZOS4)
    if vertical_offset:
        if abs(vertical_offset) > border_width:
            raise ValueError("Vertical shift must remain within the opaque border")
        shifted = np.full_like(frame, 255)
        if vertical_offset < 0:
            shifted[:vertical_offset] = frame[-vertical_offset:]
        else:
            shifted[vertical_offset:] = frame[:-vertical_offset]
        frame = shifted
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (25, 25, 115), (85, 255, 255))
    # Separate the pale-green grass from blue butterfly wings and gold accessories.
    blue, green_channel, red = cv2.split(frame.astype(np.int16))
    green[(green_channel < red + 3) | (green_channel < blue + 3)] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(green)
    components = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] > 300]
    core = np.isin(labels, components).astype(np.uint8) * 255
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    expanded = cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (27, 27)))
    fringe = cv2.GaussianBlur(expanded, (17, 17), 4).astype(np.float32) / 255
    # Keep bright wispy hairs while suppressing the blue/gray stage around them.
    brightness = np.clip((frame[:, :, 2].astype(np.float32) - 85) / 110, 0, 1)
    alpha = np.maximum(cv2.GaussianBlur(core, (3, 3), .65).astype(np.float32) / 255, fringe * brightness)
    border = np.zeros(frame.shape[:2], np.float32)
    border[:border_width] = border[-border_width:] = 1
    border[:, :border_width] = border[:, -border_width:] = 1
    shadow = cv2.warpAffine(alpha, np.float32([[1, 0, 5], [0, 1, 7]]), (frame.shape[1], frame.shape[0]))
    shadow = cv2.GaussianBlur(shadow, (25, 25), 6) * .12
    paper = 255 * (1 - shadow)
    overlap = border * alpha
    result = frame.astype(np.float32) * (1 - border[..., None])
    result += border[..., None] * (frame * alpha[..., None] + paper[..., None] * (1 - alpha[..., None]))
    return np.rint(np.clip(result, 0, 255)).astype(np.uint8), int(np.count_nonzero(overlap > .5))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--border", type=int, default=80)
    parser.add_argument("--vertical-offset", type=int, default=0)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    cap = cv2.VideoCapture(str(args.input))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {args.input}")
    if args.preview:
        tiles = []
        for seconds in (2, 3, 6, 8, 12):
            cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Cannot read frame at {seconds}")
            result, overlap = compose(frame, args.border, args.vertical_offset)
            tiles.append(cv2.resize(result, (256, 448)))
            print(seconds, "foreground border pixels", overlap)
        cv2.imwrite(str(args.output), np.concatenate(tiles, axis=1))
        cap.release()
        return
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pixel_format", "bgr24",
               "-video_size", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0"]
    if args.audio:
        command += ["-i", str(args.audio), "-map", "0:v:0", "-map", "1:a:0"]
    command += ["-t", "15", "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(args.output)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    overlaps = []
    try:
        for index in range(round(fps * 15)):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Missing input frame {index}")
            result, overlap = compose(frame, args.border, args.vertical_offset)
            encoder.stdin.write(result.tobytes())
            overlaps.append(overlap)
            if (index + 1) % 60 == 0:
                print(f"Composited {index + 1} frames", flush=True)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("ffmpeg encoding failed")
    finally:
        cap.release()
        if encoder.poll() is None:
            encoder.terminate()
            encoder.wait()
    metadata = {"source": str(args.input), "border_width": args.border, "vertical_offset": args.vertical_offset,
                "reframing": "Remove 24px on each side and proportionate top/bottom, then resize to original canvas, eliminating the generated thin frame without changing aspect ratio",
                "frame_count": len(overlaps),
                "frames_with_foreground_over_border": sum(n > 100 for n in overlaps),
                "max_foreground_border_pixels": max(overlaps), "foreground_border_pixels_by_frame": overlaps}
    args.output.with_suffix(".compositing.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
