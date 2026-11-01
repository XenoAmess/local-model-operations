"""Offline daily-maintenance tests; pnpm and OpenCode subprocesses are mocked."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock
import datetime
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("daily_opencode", ROOT / "scripts/check_opencode.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class DailyCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name)
        self.config = check.read_json(check.DEFAULT_CONFIG)
        self.day = datetime.datetime(2026, 11, 1, 10, tzinfo=datetime.timezone.utc)
        self.installed = "1.18.31"
        self.latest = "1.19.5"
        self.calls = []
        self.paths = {"pnpm": "fake-pnpm", "opencode": "fake-opencode"}
        environment = mock.patch.dict(os.environ, {"LOCAL_MODEL_AI_REPAIR_COMMAND": ""})
        environment.start()
        self.addCleanup(environment.stop)
        patcher = mock.patch.object(check.shutil, "which", side_effect=lambda name: self.paths[name])
        patcher.start()
        self.addCleanup(patcher.stop)

    def runner(self, args, **kwargs):
        self.calls.append(args)
        if args[0] == "fake-opencode":
            output = self.installed + "\n"
        elif args[1] == "view":
            output = json.dumps(self.latest)
        else:
            self.assertEqual(args[1:4], ["add", "--global", "opencode-ai@" + max(
                (self.latest, self.config["client_maintenance"]["opencode"]["minimum_version"]), key=check.version_key)])
            self.installed = args[-1].split("@")[-1]
            self.paths["opencode"] = "fake-opencode"
            output = "updated"
        return subprocess.CompletedProcess(args, 0, output, "")

    def ensure(self, runner=None):
        return check.ensure_current(self.config, state_dir=self.state, runner=runner or self.runner,
                                    clock=lambda: self.day)

    def test_old_version_updates_only_opencode_and_same_day_is_cached(self):
        first = self.ensure()
        self.assertTrue(first["updated"])
        self.assertEqual(first["installed_version"], "1.19.5")
        count = len(self.calls)
        second = self.ensure()
        self.assertTrue(second["cached"])
        self.assertEqual(len(self.calls), count)
        self.assertEqual(sum(args[1] == "view" for args in self.calls), 1)
        self.assertEqual(sum(args[1] == "add" for args in self.calls), 1)

    def test_calendar_rollover_rechecks_but_newer_install_is_not_downgraded(self):
        self.installed = "1.20.0"
        self.assertFalse(self.ensure()["updated"])
        self.day += datetime.timedelta(days=1)
        self.latest = "1.20.1"
        result = self.ensure()
        self.assertTrue(result["updated"])
        self.assertEqual(result["date"], "2026-11-02")
        self.assertEqual(sum(args[1] == "view" for args in self.calls), 2)

    def test_missing_install_uses_pnpm_and_records_new_command_identity(self):
        self.paths["opencode"] = None
        result = self.ensure()
        self.assertIsNone(result["installed_before"])
        self.assertTrue(result["updated"])
        self.assertTrue(self.ensure()["cached"])

    def test_registry_failure_is_not_cached_as_success(self):
        def fail(args, **kwargs):
            if args[1] == "view":
                return subprocess.CompletedProcess(args, 1, "", "offline registry error")
            return self.runner(args, **kwargs)
        with self.assertRaises(check.PreflightError):
            self.ensure(fail)
        self.assertFalse((self.state / "daily.json").exists())
        self.assertIn("CHECK_FAILED", (self.state / "checks.jsonl").read_text(encoding="utf-8"))
        self.assertTrue(self.ensure()["updated"])

    def test_update_failure_or_shadowed_old_binary_does_not_mark_day_ready(self):
        for mode in ("update-fails", "shadowed-cli"):
            with self.subTest(mode=mode):
                def fail(args, **kwargs):
                    if args[1] == "add":
                        return subprocess.CompletedProcess(args, 1 if mode == "update-fails" else 0, "", "")
                    return self.runner(args, **kwargs)
                with self.assertRaises(check.PreflightError):
                    self.ensure(fail)
                self.assertFalse((self.state / "daily.json").exists())

    def test_policy_and_path_changes_invalidate_same_day_cache(self):
        self.ensure()
        self.config["client_maintenance"]["opencode"]["minimum_version"] = "1.20.0"
        self.assertTrue(self.ensure()["updated"])
        self.paths["pnpm"] = "other-pnpm"
        def moved(args, **kwargs):
            mapped = ["fake-pnpm" if args[0] == "other-pnpm" else args[0], *args[1:]]
            return self.runner(mapped, **kwargs)
        self.assertFalse(self.ensure(moved)["cached"])

    def test_parallel_clients_share_one_check_and_update(self):
        entered = threading.Event()
        release = threading.Event()
        def slow(args, **kwargs):
            if args[1] == "view":
                entered.set()
                self.assertTrue(release.wait(2))
            return self.runner(args, **kwargs)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.ensure, slow)
            self.assertTrue(entered.wait(2))
            second = pool.submit(self.ensure, slow)
            time.sleep(0.05)
            release.set()
            results = [first.result(timeout=3), second.result(timeout=3)]
        self.assertEqual(sum(not result["cached"] for result in results), 1)
        self.assertEqual(sum(args[1] == "add" for args in self.calls), 1)

    def test_semver_order_and_malformed_registry_versions(self):
        self.assertGreater(check.version_key("1.20.0"), check.version_key("1.9.99"))
        self.assertGreater(check.version_key("1.20.0"), check.version_key("1.20.0-rc.2"))
        for latest in ("notice 1.19.5", "1.19.5\n", "1.19.6-rc.1", ["1.19.5"]):
            with self.subTest(latest=latest):
                self.latest = latest
                with self.assertRaises(check.PreflightError):
                    self.ensure()
                self.assertFalse((self.state / "daily.json").exists())

    def test_attached_ai_repairs_then_real_recheck_succeeds(self):
        broken = True
        tasks = []
        def command(args, **kwargs):
            if args[1] == "view" and broken:
                return subprocess.CompletedProcess(args, 1, "", "registry needs repair")
            return self.runner(args, **kwargs)
        def ai_repair(task):
            nonlocal broken
            tasks.append(task)
            self.assertIn("registry", (self.state / "checks.jsonl").read_text(encoding="utf-8"))
            self.assertIn("exempt", task["bootstrap"])
            broken = False
        result = check.ensure_current(self.config, state_dir=self.state, runner=command,
                                      clock=lambda: self.day, repair=ai_repair)
        self.assertTrue(result["updated"])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(result["installed_version"], "1.19.5")

    def test_claimed_ai_success_still_requires_actual_version_recovery(self):
        tasks = []
        def broken(args, **kwargs):
            return subprocess.CompletedProcess(args, 1, "", "still broken")
        with self.assertRaises(check.AIRepairRequired) as caught:
            check.ensure_current(self.config, state_dir=self.state, runner=broken,
                                 clock=lambda: self.day, repair=lambda task: tasks.append(task))
        self.assertEqual(len(tasks), 3)
        self.assertEqual(caught.exception.repair_request["event"], "AI_REPAIR_REQUIRED")
        self.assertFalse((self.state / "daily.json").exists())


if __name__ == "__main__":
    unittest.main()
