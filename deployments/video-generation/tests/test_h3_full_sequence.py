"""Frame/route boundaries and worker guarantees without allocating a model."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from h3_full_sequence import padded_frames, strategy
from h3_2k_worker import process
from h3_refiner_profiles import ic_command


class FullSequenceTest(unittest.TestCase):
    def test_full_14_seconds_are_covered_and_padding_is_only_at_the_end(self):
        for real in range(113, 363):
            padded = padded_frames(real)
            self.assertGreaterEqual(padded, real)
            self.assertLess(padded - real, 17)
            self.assertEqual((padded - 5) % 17, 0)
        self.assertEqual(padded_frames(336), 345)
        self.assertEqual((padded_frames(336) - 5) // 17 * 5 + 2, 102)

    def test_only_long_4k_uses_the_new_route_and_command_retains_seed_and_steps(self):
        for frames in (113, 120, 121, 123, 124):
            self.assertEqual(strategy("3840x2160", frames), "independent_windows")
        for frames in (125, 126, 336, 362):
            self.assertEqual(strategy("3840x2160", frames), "full_sequence")
        self.assertEqual(strategy("2560x1440", 336), "independent_windows")
        command = ic_command("real.jsonl", size="3840x2160", seed=1234, sampler="up3", full_frames=336)
        self.assertIn("--full-sequence", command)
        self.assertEqual(command[-1], "336")
        self.assertEqual(command[command.index("--sampler")+1], "up3")

    def test_long_4k_never_creates_or_stitches_independent_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "request.json").write_text(json.dumps({"mode": "regenerate", "input_video": "real.mp4",
                                                             "size": "3840x2160", "prompt": "keep motion"}))
            info = {"streams": [{"codec_type": "video", "duration": "14"}], "format": {}}
            with patch("h3_2k_worker.probe", return_value=info), \
                    patch("h3_2k_worker.process_full_sequence") as full, \
                    patch("h3_2k_worker.plan_windows") as windows, patch("h3_2k_worker.stitch_command") as stitch:
                process(folder)
            self.assertEqual(full.call_args.args[-1], 336)
            windows.assert_not_called()
            stitch.assert_not_called()
            with patch("h3_2k_worker.probe", return_value=info), \
                    patch("h3_2k_worker.process_full_sequence", side_effect=RuntimeError("inference failed")), \
                    patch("h3_2k_worker.plan_windows") as windows, patch("h3_2k_worker.stitch_command") as stitch:
                with self.assertRaisesRegex(RuntimeError, "inference failed"):
                    process(folder)
            windows.assert_not_called()
            stitch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
