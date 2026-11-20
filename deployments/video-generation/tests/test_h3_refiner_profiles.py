"""Verify native 4K reaches the real worker command and preserves existing 2K paths."""

import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from h3_refiner_profiles import PROFILES, get_profile, ic_command
from h3_2k_batch_worker import prepare
from h3_2k_worker import stitch_command
from serve_video_http import create_app
from video_gpu_scheduler import Scheduler
from video_queue import QueueStore, REFINER


class RefinerProfileTest(unittest.TestCase):
    def test_4k_matches_pinned_native_geometry_and_uses_bounded_cohorts(self):
        profile = get_profile("3840x2160")
        tree = ast.parse((ROOT / "models/Open-H3-Regenerate-2K-IC/infer/infer.py").read_text())
        resolutions = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == "RESOLUTIONS" for t in node.targets))
        self.assertEqual(resolutions["3840p"], (768, 1344, 2176, 3840, 2160))
        self.assertEqual((profile.native_width, profile.native_height), (3840, 2176))
        self.assertEqual((profile.width, profile.height), (3840, 2160))
        self.assertEqual(profile.native_height - profile.height, 16)
        self.assertEqual(profile.max_windows_per_load, 1)
        self.assertEqual(profile.max_jobs_per_cohort, 1)

    def test_all_worker_commands_pass_the_actual_size_and_keep_sampler_and_seed(self):
        for size in PROFILES:
            command = [str(value) for value in ic_command("fixture.jsonl", size=size, seed=5678, sampler="up3")]
            self.assertEqual(command[command.index("--size") + 1], size)
            self.assertEqual(command[command.index("--seed") + 1], "5678")
            self.assertEqual(command[command.index("--sampler") + 1], "up3")

    def test_legacy_2k_checkpoint_paths_remain_unchanged(self):
        for size in ["2560x1440", "1440x2560"]:
            self.assertEqual(get_profile(size).window_path(Path("fixture"), 0), Path("fixture/window-00-2k.mkv"))
        self.assertEqual(get_profile("1440x2560").resolution, "2k-portrait")
        self.assertEqual(get_profile("3840x2160").window_path(Path("fixture"), 0), Path("fixture/window-00-4k.mkv"))

    def test_original_124_frame_4k_window_is_preserved_and_strictly_longer_clips_use_full_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            request = {"mode": "regenerate", "input_video": "fixture.mp4", "size": "3840x2160", "prompt": "wave"}
            (folder / "request.json").write_text(json.dumps(request))
            metadata = {"streams": [{"codec_type": "video", "duration": str(124 / 24)}], "format": {"duration": str(124 / 24)}}
            with patch("h3_2k_batch_worker.probe", return_value=metadata), \
                    patch("h3_2k_batch_worker.complete_video", side_effect=[True, False]):
                _, windows = prepare(folder)
            self.assertEqual(windows[0]["width"], 3840)
            self.assertEqual(windows[0]["height"], 2160)
            command = stitch_command(folder, "fixture.mp4", [{"keep_local_start": 0, "keep_local_end": 124}], 124, "3840x2160")
            self.assertIn(windows[0]["output"], command)
            for count in (125, 126, 336, 362):
                metadata = {"streams": [{"codec_type": "video", "duration": str(count / 24)}], "format": {}}
                with patch("h3_2k_batch_worker.probe", return_value=metadata), patch("h3_2k_batch_worker.run") as run:
                    _, windows = prepare(folder)
                self.assertEqual(windows, [])
                run.assert_not_called()

    def test_http_accepts_native_4k_without_renaming_model_or_starting_gpu(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = QueueStore(temporary)
            with TestClient(create_app(store, REFINER)) as client:
                store.set_state(phase="idle", active_model=None, consecutive=0)
                upload = client.post("/v1/files", files={"file": ("draft.mp4", b"fixture", "video/mp4")}).json()["id"]
                body = {"model": REFINER, "input_video": {"file_id": upload}, "size": "3840x2160"}
                response = client.post("/v1/videos/regenerations", json=body)
                self.assertEqual(response.status_code, 202, response.text)
                self.assertEqual(response.json()["model"], REFINER)
                self.assertEqual(response.json()["size"], "3840x2160")
                self.assertEqual(store.get(response.json()["id"])["request"]["size"], "3840x2160")
                models = client.get("/v1/models").json()["data"][0]
                self.assertIn("3840x2160", models["sizes"])
                for bad in ["2160x3840", "3840x2176", "4096x2304"]:
                    self.assertEqual(client.post("/v1/videos/regenerations", json=dict(body, size=bad)).status_code, 422)

    def test_4k_dispatch_never_groups_two_large_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = QueueStore(temporary)
            store.initialize()
            payload = {"size": "3840x2160", "seed": 1234, "sampler": "up3"}
            jobs = [store.enqueue(REFINER, payload) for _ in range(2)]
            self.assertEqual(Scheduler(store).cohort(jobs[0], jobs), [jobs[0]])


if __name__ == "__main__":
    unittest.main()
