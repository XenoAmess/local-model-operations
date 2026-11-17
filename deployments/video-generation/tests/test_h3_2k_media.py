"""Exercise the actual FFmpeg stitch on a 15-second frame-coded clip with audio."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("h3_worker", ROOT / "tools/h3_2k_worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class StitchTest(unittest.TestCase):
    def test_fifteen_second_stitch_preserves_timeline_and_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / "source.mkv"
            frames = np.zeros((360, 32, 64, 3), dtype=np.uint8)
            frames[..., 0] = (np.arange(360) % 256)[:, None, None]
            frames[..., 1] = ((np.arange(360) // 256) * 60)[:, None, None]
            frames[..., 2] = 128
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", "64x32", "-r", "24", "-i", "-", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000",
                "-t", "15", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(source)], input=frames.tobytes(), check=True)
            plan = WORKER.plan_windows(360)
            for index, part in enumerate(plan):
                subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source), "-vf",
                    f"trim=start_frame={part['source_start_frame']}:end_frame={part['source_end_frame']},setpts=PTS-STARTPTS",
                    "-an", "-c:v", "ffv1", str(folder / f"window-{index:02d}-2k.mkv")], check=True)
            subprocess.run(WORKER.stitch_command(folder, source, plan, 360), check=True)
            self.assertTrue(WORKER.complete_video(folder / "result.mp4", 64, 32, 360))
            metadata = WORKER.probe(folder / "result.mp4")
            self.assertTrue(any(stream["codec_type"] == "audio" for stream in metadata["streams"]))
            self.assertAlmostEqual(float(metadata["format"]["duration"]), 15, delta=.05)
            decoded = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(folder / "result.mp4"),
                                               "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
            decoded = np.frombuffer(decoded, dtype=np.uint8).reshape(360, 32, 64, 3)
            for index in [0, 100, 101, 179, 180, 257, 258, 359]:
                self.assertLess(np.abs(decoded[index].astype(float) - frames[index]).mean(), 4)


if __name__ == "__main__":
    unittest.main()
