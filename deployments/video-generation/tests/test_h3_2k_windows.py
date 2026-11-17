"""A long-video plan must neither drop nor duplicate any output timestamp."""

import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "h3_windows", Path(__file__).resolve().parents[1] / "tools/plan_h3_2k_windows.py")
WINDOWS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WINDOWS)


class WindowPlanTest(unittest.TestCase):
    def test_all_supported_base_lengths_preserve_every_frame_once(self):
        for total in range(113, 363):
            windows = WINDOWS.plan_windows(total)
            retained = []
            for part in windows:
                self.assertLessEqual(part["source_end_frame"] - part["source_start_frame"], 124)
                self.assertGreaterEqual(part["source_end_frame"] - part["source_start_frame"], 113)
                self.assertGreaterEqual(part["keep_local_start"], 0)
                self.assertLessEqual(part["keep_local_end"], 124)
                retained.extend(range(part["keep_global_start"], part["keep_global_end"]))
            self.assertEqual(retained, list(range(total)))
            for left, right in zip(windows, windows[1:]):
                self.assertGreaterEqual(left["source_end_frame"] - right["source_start_frame"], 24)

    def test_fifteen_seconds_use_four_overlapping_windows(self):
        self.assertEqual(len(WINDOWS.plan_windows(360)), 4)
        self.assertEqual(len(WINDOWS.plan_windows(362)), 4)

    def test_shorter_than_upstream_minimum_is_rejected(self):
        with self.assertRaises(ValueError):
            WINDOWS.plan_windows(112)


if __name__ == "__main__":
    unittest.main()
