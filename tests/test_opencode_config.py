"""Offline tests for the reusable OpenCode exact-permission config generator."""
import copy
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("opencode_config", os.path.join(ROOT, "scripts", "opencode_config.py"))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def executor(**overrides):
    """Fresh shared-executor-shaped mapping; the sole endpoint/model authority."""
    data = {
        "schema": "local-model-operations.executor/v1",
        "base_url": "http://192.168.1.11:8080/v1",
        "model": "qwen38-coder",
        "authentication": {"required": False, "api_key_env": "LOCAL_MODEL_API_KEY"},
        "automatic_fallback": False,
        "defaults": {"temperature": 0, "response_format": {"type": "json_object"}},
        "timeouts": {"read_seconds": 180, "total_seconds": 900},
        "transient_retries": {"maximum_attempts": 6},
    }
    data.update(overrides)
    return data


def build(**kwargs):
    kwargs.setdefault("executor", executor())
    kwargs.setdefault("workspace", "D:/a/task/workspace")
    kwargs.setdefault("worktree", "D:/")
    kwargs.setdefault("owned_files", ["scripts/x.py"])
    return config.build_config(**kwargs)


class PathCoordinateTests(unittest.TestCase):
    def test_windows_disk_root_worktree_grants_worktree_relative_pattern(self):
        cfg = build(worktree="D:/", workspace="D:/a/task/workspace",
                    owned_files=["scripts/x.py"])
        grants = cfg["permission"]["edit"]
        self.assertEqual(grants["a/task/workspace/scripts/x.py"], "allow")
        self.assertNotIn("scripts/x.py", grants)
        self.assertNotIn("./scripts/x.py", grants)
        for pattern in grants:
            self.assertFalse(pattern.startswith("D:"))
            self.assertNotIn("\\", pattern)
            self.assertNotIn("//", pattern)
            self.assertFalse(pattern.endswith("/"))

    def test_windows_nested_worktree_and_backslash_input(self):
        cfg = build(worktree="D:/proj", workspace="D:/proj\\nested\\workspace",
                    owned_files=["src\\main.java"])
        self.assertEqual(cfg["permission"]["edit"]["nested/workspace/src/main.java"], "allow")

    def test_windows_case_insensitive_containment_keeps_actual_casing(self):
        cfg = build(worktree="D:/Proj", workspace="D:/proj/workspace",
                    owned_files=["Scripts/X.PY"])
        grants = cfg["permission"]["edit"]
        self.assertEqual(grants["workspace/Scripts/X.PY"], "allow")
        self.assertNotIn("workspace/scripts/x.py", grants)
        with self.assertRaises(config.ConfigError):
            build(worktree="/Repo", workspace="/repo/task", owned_files=["x.py"])

    def test_posix_nested_and_root_equal_cases(self):
        cfg = build(worktree="/home/u/repo", workspace="/home/u/repo/sub/task",
                    owned_files=["pkg/mod.ts"])
        self.assertEqual(cfg["permission"]["edit"]["sub/task/pkg/mod.ts"], "allow")
        cfg = build(worktree="/home/u/repo", workspace="/home/u/repo",
                    owned_files=["pkg/mod.ts"])
        self.assertEqual(cfg["permission"]["edit"]["pkg/mod.ts"], "allow")

    def test_posix_root_worktree_anchor_is_valid(self):
        cfg = build(worktree="/", workspace="/a/task/workspace",
                    owned_files=["scripts/x.py"])
        self.assertEqual(cfg["permission"]["edit"]["a/task/workspace/scripts/x.py"], "allow")
        cfg = build(worktree="/", workspace="/", owned_files=["x.py"])
        self.assertEqual(cfg["permission"]["edit"]["x.py"], "allow")

    def test_windows_root_equal_worktree(self):
        cfg = build(worktree="D:/", workspace="D:/", owned_files=["x.py"])
        self.assertEqual(cfg["permission"]["edit"]["x.py"], "allow")

    def test_workspace_outside_worktree_rejected(self):
        with self.assertRaises(config.ConfigError):
            build(worktree="D:/a/b", workspace="D:/a/c")
        with self.assertRaises(config.ConfigError):
            build(worktree="/a/b", workspace="/a")
        with self.assertRaises(config.ConfigError):
            build(worktree="D:/a/b", workspace="D:/a")

    def test_traversal_rejected(self):
        for owned in ["../outside.py", "scripts/../../x.py", "a/../b/x.py"]:
            with self.subTest(owned=owned):
                with self.assertRaises(config.ConfigError):
                    build(owned_files=[owned])
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a/task/../workspace", worktree="D:/")

    def test_cross_drive_and_flavor_mismatch_rejected(self):
        with self.assertRaises(config.ConfigError):
            build(worktree="C:/repo", workspace="D:/repo/task")
        with self.assertRaises(config.ConfigError):
            build(worktree="D:/repo", workspace="/repo/task")

    def test_absolute_drive_relative_unc_and_device_owned_entries_rejected(self):
        for owned in ["D:/abs/x.py", "/abs/x.py", "D:", "D:/", "//server/share/x.py",
                      "\\\\server\\share\\x.py", "/dev/null", "NUL", "a/COM1.txt",
                      "D:x.py", "C:/x.py", "/x.py", "file.txt:stream", "file.txt:"]:
            with self.subTest(owned=owned):
                with self.assertRaises(config.ConfigError):
                    build(owned_files=[owned])

    def test_device_like_regular_directories_are_not_rejected(self):
        cfg = build(owned_files=["device/x.py", "devices/x.py", "dev/x.py",
                                 "src/dev/null/x.py"])
        grants = cfg["permission"]["edit"]
        self.assertEqual(grants["a/task/workspace/dev/x.py"], "allow")
        self.assertEqual(grants["a/task/workspace/src/dev/null/x.py"], "allow")

    def test_wildcard_git_and_ads_prefixes_rejected(self):
        for workspace in ["D:/a/task/worxks*", "D:/a/task/w?ks", "D:/repo/task*",
                          "D:/repo/.git", "D:/repo/[x]task"]:
            with self.subTest(workspace=workspace):
                with self.assertRaises(config.ConfigError):
                    build(workspace=workspace, worktree="D:/", owned_files=["x.py"])
        for worktree in ["D:/re*po", "D:/.git", "/re?po"]:
            with self.subTest(worktree=worktree):
                with self.assertRaises(config.ConfigError):
                    build(workspace="D:/a" if worktree.startswith("D") else "/a",
                          worktree=worktree, owned_files=["x.py"])
        with self.assertRaises(config.ConfigError):
            build(worktree="D:/", workspace="D:/a/file.txt:stream", owned_files=["x.py"])

    def test_wildcard_and_metacharacter_entries_rejected(self):
        for owned in ["scripts/*.py", "scripts/?.py", "scripts/[ab].py",
                      "scripts/{a,b}.py", "scripts/<x>.py", "scripts/**"]:
            with self.subTest(owned=owned):
                with self.assertRaises(config.ConfigError):
                    build(owned_files=[owned])

    def test_git_components_rejected(self):
        for owned in [".git/config", "a/.git/b", "src/.GIT/hooks/x"]:
            with self.subTest(owned=owned):
                with self.assertRaises(config.ConfigError):
                    build(owned_files=[owned])

    def test_empty_owned_list_and_string_rejected(self):
        with self.assertRaises(config.ConfigError):
            build(owned_files=[])
        with self.assertRaises(config.ConfigError):
            build(owned_files="scripts/x.py")
        with self.assertRaises(config.ConfigError):
            build(owned_files=None)
        with self.assertRaises(config.ConfigError):
            build(owned_files={"scripts/x.py": "allow"})
        with self.assertRaises(config.ConfigError):
            build(owned_files=5)
        with self.assertRaises(config.ConfigError):
            build(owned_files=())
        with self.assertRaises(config.ConfigError):
            build(owned_files=["scripts/x.py", ""])
        with self.assertRaises(config.ConfigError):
            build(owned_files=["scripts/x.py", None])

    def test_invalid_numeric_output_limits_rejected(self):
        for bad in [True, False, 0, -1, 16001, 16000.0, "16000", None]:
            with self.subTest(bad=bad):
                with self.assertRaises(config.ConfigError):
                    build(max_output_tokens=bad)
        self.assertEqual(build(max_output_tokens=1)["provider"]["pilot"]["models"]
                         ["qwen38-coder"]["limit"]["output"], 1)
        self.assertEqual(build(max_output_tokens=16000)["provider"]["pilot"]["models"]
                         ["qwen38-coder"]["limit"]["output"], 16000)


    def test_owner_boundary_drive_relative_and_ambiguous_windows_paths(self):
        for bad in ["D:", "D:x.py", "D:/repo/task*", "D:/repo/.git", "D:/repo/CON"]:
            with self.subTest(coordinate=bad):
                with self.assertRaises(config.ConfigError):
                    build(worktree="D:/", workspace=bad)
        for bad in ["file.txt:", "a/NUL", "a/COM1.py", "a/.git.", "a/name.", "a/name ", "a/line\nname.py"]:
            with self.subTest(owned=bad):
                with self.assertRaises(config.ConfigError):
                    build(owned_files=[bad])
        with self.assertRaises(config.ConfigError):
            build(workspace="/repo", worktree="/repo", owned_files=["a\\b.py"])


class AuthorityAndMetadataTests(unittest.TestCase):
    def setUp(self):
        self.cfg = build()

    def test_dynamic_endpoint_and_model_from_executor(self):
        cfg = build(executor=executor(base_url="http://10.0.0.5:7000/v1", model="other-model"))
        self.assertEqual(cfg["provider"]["pilot"]["options"]["baseURL"], "http://10.0.0.5:7000/v1")
        self.assertEqual(cfg["model"], "pilot/other-model")
        self.assertEqual(cfg["small_model"], "pilot/other-model")
        self.assertEqual(list(cfg["provider"]["pilot"]["models"]), ["other-model"])
        self.assertNotIn("192.168.1.11", json.dumps(cfg))
        self.assertNotIn("qwen38-coder", json.dumps(cfg))

    def test_no_loopback_proxy_address_or_hardcoded_authority(self):
        blob = json.dumps(self.cfg)
        self.assertNotIn("127.0.0.1", blob)
        self.assertNotIn("localhost", blob)
        self.assertIn("http://192.168.1.11:8080/v1", blob)
        self.assertEqual(self.cfg["provider"]["pilot"]["options"]["baseURL"],
                         "http://192.168.1.11:8080/v1")
        self.assertEqual(self.cfg["provider"]["pilot"]["options"]["apiKey"], "local")

    def test_malformed_or_missing_authority_rejected(self):
        for bad in [executor(model=""), {"base_url": "", "model": "m"},
                    {"base_url": "http://x/v1"}, {"model": "m"},
                    executor(base_url="not a url"), executor(base_url="http://a b/v1"),
                    executor(base_url="ftp://192.168.1.11:8080/v1"),
                    executor(base_url="http:///v1"), executor(base_url="http://"),
                    executor(base_url="http://:8080/v1"),
                    executor(base_url="http://host:port/v1"),
                    executor(base_url="http://host:99999999/v1"),
                    executor(base_url="http://host:8080x/v1"),
                    executor(base_url="http://host:8080/v1?q=1"),
                    executor(base_url="http://host:65536/v1"),
                    executor(base_url="http://host:0/v1"),
                    executor(base_url="http://user:secret@host/v1"),
                    executor(base_url="http://host/v1#fragment"),
                    executor(base_url="http://[bad/v1"),
                    executor(model="pilot/qwen38-coder"), "not-a-mapping", None]:
            with self.subTest(bad=bad):
                with self.assertRaises(config.ConfigError):
                    config.build_config(bad, workspace="/w", worktree="/w",
                                        owned_files=["x.py"])

    def test_valid_authority_shapes_accepted(self):
        for base_url in ["http://192.168.1.11:8080/v1", "https://host/v1",
                         "http://host:80", "http://sub.domain.example:1234/v1"]:
            with self.subTest(base_url=base_url):
                cfg = build(executor=executor(base_url=base_url))
                self.assertEqual(cfg["provider"]["pilot"]["options"]["baseURL"], base_url)

    def model_options(self):
        return self.cfg["provider"]["pilot"]["models"]["qwen38-coder"]

    def test_1_19_5_metadata_temperature_tools_thinking_usage(self):
        model = self.model_options()
        self.assertIs(model["temperature"], True)
        self.assertIs(model["tool_call"], True)
        self.assertEqual(self.cfg["agent"]["pilot"]["temperature"], 0)
        self.assertEqual(model["options"]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(model["options"]["stream_options"], {"include_usage": True})

    def test_output_budget_and_no_forbidden_sdk_controls(self):
        model = self.model_options()
        self.assertEqual(model["options"]["max_tokens"], 16000)
        self.assertEqual(model["limit"]["output"], 16000)
        blob = json.dumps(self.cfg)
        for forbidden in ("maxOutputTokens", "maxRetries", "max_steps", "steps",
                          "wall", "total_posts"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, blob)
        self.assertNotIn("response_format", blob)
        self.assertNotIn("transient_retries", blob)
        self.assertNotIn("timeouts", blob)
        self.assertNotIn("system_template", blob)

    def test_disabled_environment_and_no_ambient_discovery(self):
        self.assertEqual(self.cfg["share"], "disabled")
        self.assertIs(self.cfg["snapshot"], False)
        self.assertIs(self.cfg["autoupdate"], False)
        self.assertEqual(self.cfg["plugin"], [])
        self.assertEqual(self.cfg["mcp"], {})
        self.assertIs(self.cfg["formatter"], False)
        self.assertIs(self.cfg["lsp"], False)
        self.assertEqual(self.cfg["compaction"], {"auto": False, "prune": False})
        self.assertEqual(self.cfg["instructions"], [])


class PermissionShapeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = build(owned_files=["a/x.py", "b/y.py"])

    def test_default_deny_and_exact_edit_grants(self):
        permission = self.cfg["permission"]
        self.assertEqual(permission["*"], "deny")
        self.assertEqual(permission["edit"]["*"], "deny")
        # Default build coordinates: worktree "D:/", workspace "D:/a/task/workspace",
        # so the actual grants are the full worktree-relative patterns.
        self.assertEqual(permission["edit"]["a/task/workspace/a/x.py"], "allow")
        self.assertEqual(permission["edit"]["a/task/workspace/b/y.py"], "allow")
        self.assertNotIn("a/x.py", permission["edit"])
        self.assertNotIn("a", permission["edit"])
        self.assertNotIn("a/*", permission["edit"])
        self.assertNotIn("a/**", permission["edit"])

    def read_glob_grep_and_external_directory(self):
        return self.cfg["permission"]

    def test_read_glob_grep_allowed_external_directory_denied(self):
        permission = self.read_glob_grep_and_external_directory()
        self.assertEqual(permission["read"], "allow")
        self.assertEqual(permission["glob"], "allow")
        self.assertEqual(permission["grep"], "allow")
        self.assertEqual(permission["external_directory"], "deny")

    def test_internal_invalid_explicitly_allowed_for_diagnosis(self):
        self.assertEqual(self.cfg["permission"]["invalid"], "allow")
        self.assertEqual(self.cfg["agent"]["pilot"]["permission"]["invalid"], "allow")

    def test_no_shell_git_network_business_delegation_grants(self):
        permission = self.cfg["permission"]
        self.assertEqual(permission["bash"], "deny")
        self.assertEqual(permission["webfetch"], "deny")
        self.assertEqual(permission["websearch"], "deny")
        self.assertEqual(permission["task"], "deny")
        for forbidden in ("git", "command", "shell", "delegate", "http", "network",
                         "write", "apply_patch", "multiedit", "curl", "subprocess"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, permission)
        blob = json.dumps(permission)
        self.assertNotIn("curl", blob)
        self.assertNotIn("subprocess", blob)
        self.assertNotIn("apply_patch", blob)
        self.assertNotIn("multiedit", blob)

    def test_agent_permission_mirrors_top_level(self):
        self.assertEqual(self.cfg["agent"]["pilot"]["permission"], self.cfg["permission"])

    def test_agent_permission_is_independent_copy(self):
        agent_permission = self.cfg["agent"]["pilot"]["permission"]
        self.assertIsNot(agent_permission, self.cfg["permission"])
        self.assertIsNot(agent_permission["edit"], self.cfg["permission"]["edit"])
        agent_permission["edit"]["injected.py"] = "allow"
        self.assertNotIn("injected.py", self.cfg["permission"]["edit"])

    def test_glob_grep_allows_are_tool_level_not_path_shaped(self):
        # 1.19.5 glob/grep ask with their query pattern strings, not directories;
        # these blanket allows neither restrict nor broaden searched directories.
        permission = self.cfg["permission"]
        self.assertEqual(permission["glob"], "allow")
        self.assertEqual(permission["grep"], "allow")
        self.assertNotIsInstance(permission["glob"], dict)
        self.assertNotIsInstance(permission["grep"], dict)


class PurityAndOwnershipTests(unittest.TestCase):
    def test_build_config_performs_no_io_and_returns_fresh_dict(self):
        import builtins

        def guard(*args, **kwargs):
            raise AssertionError("build_config must not touch the filesystem")

        previous = builtins.open
        builtins.open = guard
        try:
            source = executor()
            owned = ["scripts/x.py"]
            first = config.build_config(source, workspace="D:/a/task/workspace",
                                        worktree="D:/", owned_files=owned)
            second = config.build_config(source, workspace="D:/a/task/workspace",
                                         worktree="D:/", owned_files=owned)
        finally:
            builtins.open = previous
        self.assertIsNot(first, second)
        self.assertIsNot(first["permission"], second["permission"])
        self.assertEqual(first, second)

    def test_caller_inputs_are_not_mutated(self):
        source = executor()
        snapshot = copy.deepcopy(source)
        owned = ["scripts/x.py"]
        owned_snapshot = list(owned)
        cfg = config.build_config(source, workspace="D:/a/task/workspace",
                                  worktree="D:/", owned_files=owned)
        self.assertEqual(source, snapshot)
        self.assertEqual(owned, owned_snapshot)
        cfg["permission"]["edit"]["injected.py"] = "allow"
        cfg["provider"]["pilot"]["options"]["baseURL"] = "http://evil/v1"
        fresh = config.build_config(source, workspace="D:/a/task/workspace",
                                    worktree="D:/", owned_files=owned)
        self.assertNotIn("injected.py", fresh["permission"]["edit"])
        self.assertEqual(fresh["provider"]["pilot"]["options"]["baseURL"],
                         "http://192.168.1.11:8080/v1")

    def test_generated_config_is_json_serializable(self):
        cfg = build()
        round_trip = json.loads(json.dumps(cfg))
        self.assertEqual(round_trip, cfg)

    def test_only_enabled_local_provider_and_single_model_present(self):
        cfg = build(executor=executor(base_url="http://10.0.0.5:7000/v1", model="other-model"))
        self.assertEqual(cfg["enabled_providers"], ["pilot"])
        self.assertEqual(cfg["default_agent"], "pilot")
        self.assertEqual(list(cfg["provider"]), ["pilot"])
        self.assertEqual(list(cfg["provider"]["pilot"]["models"]), ["other-model"])
        self.assertEqual(list(cfg["agent"]), ["pilot"])
        self.assertEqual(cfg["model"], "pilot/other-model")
        self.assertEqual(cfg["small_model"], "pilot/other-model")

    def test_invalid_path_and_authority_types_rejected(self):
        for bad in [None, 5, ["D:/w"], {"path": "D:/w"}, "", "relative/path"]:
            with self.subTest(bad=bad):
                with self.assertRaises(config.ConfigError):
                    build(workspace=bad)
                with self.assertRaises(config.ConfigError):
                    build(worktree=bad)
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="C:/a")
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="D:/a/../b")
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="//server/share")
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="/dev/null")
        # A separator makes D:/ an absolute root; bare D: remains drive-relative.
        for trailing in ["D:/a/", "D:/a\\"]:
            with self.subTest(trailing=trailing):
                cfg = build(workspace="D:/a", worktree=trailing, owned_files=["x.py"])
                self.assertEqual(cfg["permission"]["edit"]["x.py"], "allow")
        cfg = build(workspace="/a/b", worktree="/a/b/", owned_files=["x.py"])
        self.assertEqual(cfg["permission"]["edit"]["x.py"], "allow")
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="D:", owned_files=["x.py"])
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="D:x.py")
        with self.assertRaises(config.ConfigError):
            build(workspace="D:/a", worktree="/a")
        with self.assertRaises(config.ConfigError):
            build(workspace="/a", worktree="D:/a")


class CliAdapterTests(unittest.TestCase):
    def test_cli_reads_executor_and_prints_json_to_stdout(self):
        import contextlib
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "executor.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(executor(), handle)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = config._main([
                    "--executor", path,
                    "--workspace", "D:/a/task/workspace",
                    "--worktree", "D:/",
                    "--owned-file", "scripts/x.py",
                    "--owned-file", "scripts/y.py",
                    "--max-output-tokens", "8000",
                ])
            self.assertEqual(code, 0)
            emitted = json.loads(buffer.getvalue())
        expected = build(owned_files=["scripts/x.py", "scripts/y.py"], max_output_tokens=8000)
        self.assertEqual(emitted, expected)
        self.assertEqual(emitted["provider"]["pilot"]["models"]["qwen38-coder"]
                         ["options"]["max_tokens"], 8000)

    def test_cli_rejects_invalid_inputs_without_writing(self):
        import contextlib
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "executor.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(executor(), handle)
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as caught:
                with contextlib.redirect_stderr(stderr):
                    config._main([
                        "--executor", path,
                        "--workspace", "D:/a/task/workspace",
                        "--worktree", "D:/",
                        "--owned-file", "scripts/*.py",
                    ])
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("wildcard", stderr.getvalue())
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(stderr):
                    config._main([
                        "--executor", path,
                        "--workspace", "D:/a/task/workspace",
                        "--worktree", "D:/",
                        "--owned-file", "scripts/x.py",
                        "--max-output-tokens", "0",
                    ])


if __name__ == "__main__":
    unittest.main()
