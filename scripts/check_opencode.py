#!/usr/bin/env python3
"""Check OpenCode once per local calendar day; update only opencode-ai via pnpm."""
from contextlib import contextmanager
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "executor.json"
STATE_SCHEMA = "local-model-operations.opencode-daily/v1"
VERSION = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                     r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?")


class PreflightError(ValueError):
    """A maintenance problem to diagnose before ordinary business dispatch."""


class AIRepairRequired(PreflightError):
    """Hand a structured recovery task to the hosting AI client."""
    def __init__(self, request_path, reason):
        super().__init__(reason)
        self.repair_request = {"event": "AI_REPAIR_REQUIRED", "request_path": str(request_path),
            "reason": reason,
            "instruction": "Use the hosting AI's tools to diagnose and repair this maintenance problem, rerun the check, then resume the pending task. This is a recovery handoff, not a request to stop or ask the user to do routine repair."}


def version_key(value):
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise PreflightError("Unrecognized OpenCode version: " + repr(value))
    major, minor, patch, prerelease, _ = match.groups()
    parts = []
    if prerelease:
        for part in prerelease.split("."):
            if not part or part.isdigit() and len(part) > 1 and part.startswith("0"):
                raise PreflightError("Invalid prerelease version: " + value)
            parts.append((0, int(part)) if part.isdigit() else (1, part))
    return int(major), int(minor), int(patch), prerelease is None, tuple(parts)


def installed_version(output):
    # Ignore notices, but never mistake a number inside an arbitrary warning for a version.
    lines = [line.strip() for line in output.splitlines() if VERSION.fullmatch(line.strip())]
    if len(lines) != 1:
        raise PreflightError("opencode --version did not report exactly one version")
    version_key(lines[0])
    return lines[0].removeprefix("v")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def maintenance_policy(config):
    settings = config.get("client_maintenance")
    if settings is None:
        settings = read_json(DEFAULT_CONFIG)["client_maintenance"]
    policy = settings["opencode"]
    if policy["package"] != "opencode-ai" or policy["channel"] != "latest":
        raise PreflightError("Daily maintenance requires opencode-ai@latest")
    version_key(policy["minimum_version"])
    for field in ("command_timeout_seconds", "update_timeout_seconds", "lock_timeout_seconds"):
        if type(policy[field]) not in (int, float) or policy[field] <= 0:
            raise PreflightError(field + " must be positive")
    return policy


def default_state_dir():
    override = os.environ.get("LOCAL_MODEL_CLIENT_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "local-model-operations" / "opencode"


def signature(policy):
    material = {"schema": STATE_SCHEMA, "policy": policy,
                "pnpm_path": shutil.which("pnpm"), "opencode_path": shutil.which("opencode")}
    raw = json.dumps(material, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cached_result(path, policy, clock):
    try:
        state = read_json(path)
        if (state["schema"] != STATE_SCHEMA or state["date"] != clock().date().isoformat()
                or state["signature"] != signature(policy)
                or version_key(state["installed_version"]) < version_key(state["target_version"])):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return {**state, "cached": True}


@contextmanager
def maintenance_lock(path, timeout):
    # Kernel-owned locks are released on process exit; never delete a live lock file.
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        start = time.monotonic()
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() - start >= timeout:
                    raise PreflightError("Timed out waiting for the OpenCode daily check") from exc
                time.sleep(0.1)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _check_once(config, *, state_dir=None, runner=None, clock=None):
    """One check/update cycle, outside model retries and business actions.

    ensure_current routes failures to the hosting AI. runner/clock injection is
    for offline tests, not a CLI bypass.
    """
    policy = maintenance_policy(config)
    directory = Path(state_dir) if state_dir is not None else default_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    clock = clock or (lambda: datetime.datetime.now().astimezone())
    runner = runner or subprocess.run
    state_path = directory / "daily.json"
    cached = cached_result(state_path, policy, clock)
    if cached is not None:
        return cached
    with maintenance_lock(directory / "maintenance.lock", policy["lock_timeout_seconds"]):
        cached = cached_result(state_path, policy, clock)
        if cached is not None:
            return cached

        def event(kind, **data):
            row = {"event": kind, "at_local": clock().isoformat(), **data}
            with (directory / "checks.jsonl").open("a", encoding="utf-8", newline="\n") as log:
                log.write(json.dumps(row, ensure_ascii=False) + "\n")

        def invoke(argv, timeout):
            event("COMMAND_BEGIN", argv=argv)
            try:
                result = runner(argv, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=timeout,
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            except (OSError, subprocess.TimeoutExpired) as exc:
                event("COMMAND_ERROR", error=repr(exc))
                raise PreflightError("OpenCode maintenance command failed; see " + str(directory / "checks.jsonl")) from exc
            event("COMMAND_END", returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            if result.returncode != 0:
                raise PreflightError("OpenCode maintenance command exited " + str(result.returncode)
                                     + "; see " + str(directory / "checks.jsonl"))
            return result.stdout

        event("CHECK_BEGIN")
        try:
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise PreflightError("pnpm is required on PATH for the daily OpenCode check")
            opencode = shutil.which("opencode")
            before = installed_version(invoke([opencode, "--version"], policy["command_timeout_seconds"])) if opencode else None
            latest = json.loads(invoke([pnpm, "view", "opencode-ai@latest", "version", "--json"],
                                       policy["command_timeout_seconds"]))
            latest_key = version_key(latest)
            if not latest_key[3]:
                raise PreflightError("opencode-ai@latest is a prerelease; no stable target was reported")
            target = max((latest, policy["minimum_version"]), key=version_key)
            updated = before is None or version_key(before) < version_key(target)
            after = before
            if updated:
                invoke([pnpm, "add", "--global", "opencode-ai@" + target], policy["update_timeout_seconds"])
                opencode = shutil.which("opencode")
                if opencode is None:
                    raise PreflightError("pnpm finished, but opencode is not on PATH")
                after = installed_version(invoke([opencode, "--version"], policy["command_timeout_seconds"]))
                if version_key(after) < version_key(target):
                    raise PreflightError("The opencode on PATH is still too old after pnpm update; check command shadowing")
            state = {"schema": STATE_SCHEMA, "date": clock().date().isoformat(),
                     "checked_at_local": clock().isoformat(), "signature": signature(policy),
                     "installed_before": before, "installed_version": after,
                     "registry_latest": latest, "target_version": target, "updated": updated,
                     "pnpm_path": pnpm, "opencode_path": opencode}
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8", newline="\n")
            temporary.replace(state_path)
            event("CHECK_SUCCESS", installed_version=after, target_version=target, updated=updated)
            return {**state, "cached": False}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            event("CHECK_FAILED", error=str(exc))
            if isinstance(exc, PreflightError):
                raise
            raise PreflightError("OpenCode daily check failed: " + str(exc)) from exc


def repair_task(directory, reason, round_number):
    task = {"schema": "local-model-operations.opencode-ai-repair/v1",
        "created_at_local": datetime.datetime.now().astimezone().isoformat(),
        "repair_round": round_number, "failure": str(reason),
        "diagnostic_log": str(directory / "checks.jsonl"),
        "commands_found": {name: shutil.which(name) for name in ("pnpm", "opencode")},
        "objective": "Autonomously restore pnpm/OpenCode maintenance, verify the daily check, and resume the pending local-model task.",
        "diagnosis": ["Check command resolution, PATH and pnpm global bin for shadowed or missing commands.",
                      "Use the command log to investigate registry/network/proxy, installation, package scripts, file locks, or version parsing as relevant.",
                      "Apply a specific repair based on the actual error, then rerun the daily check."],
        "bootstrap": "Use the hosting AI's available model and tools. Maintenance diagnosis is exempt from the OpenCode-version prerequisite; do not make the repair depend on the broken check passing first.",
        "scope": "Repair client dependencies/environment. Model HTTP retries and business/tool actions remain separate; do not replay business actions.",
        "completion": "Only an actual successful daily recheck marks recovery complete. If an external dependency is still unavailable after meaningful repair attempts, report the concrete blocker and diagnostics."}
    path = directory / "ai-repair-request.json"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with (directory / "repairs.jsonl").open("a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps(task, ensure_ascii=False) + "\n")
    except OSError as exc:
        # A broken state directory must still produce a task for the hosting AI.
        task["state_write_failure"] = str(exc)
        with tempfile.NamedTemporaryFile(mode="w", prefix="local-model-ai-repair-", suffix=".json",
                encoding="utf-8", newline="\n", delete=False) as handle:
            json.dump(task, handle, ensure_ascii=False, indent=2)
            path = Path(handle.name)
    return path, task


def ensure_current(config, *, state_dir=None, runner=None, clock=None, repair=None):
    """Check, ask an attached AI repair handler to fix failures, and recheck.

    AI clients can supply repair(task), which uses their existing AI/tools. CLI
    clients may attach LOCAL_MODEL_AI_REPAIR_COMMAND as a JSON argv array; the
    driver receives the recovery task as JSON on stdin. Without a handler, exit
    75 carries the recovery task to the hosting AI, which must continue repair.
    """
    directory = Path(state_dir) if state_dir is not None else default_state_dir()
    command_text = os.environ.get("LOCAL_MODEL_AI_REPAIR_COMMAND")
    for round_number in range(4):
        try:
            return _check_once(config, state_dir=directory, runner=runner, clock=clock)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            path, task = repair_task(directory, exc, round_number + 1)
            if round_number == 3 or repair is None and not command_text:
                raise AIRepairRequired(path, str(exc)) from exc
            # _check_once released its update lock before entering the AI handler.
            if repair is not None:
                try:
                    repair(task)
                except Exception as error:
                    path, _ = repair_task(directory, "Attached AI repair handler: " + str(error), round_number + 1)
                    raise AIRepairRequired(path, str(error)) from error
            else:
                try:
                    argv = json.loads(command_text)
                    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
                        raise ValueError("repair command must be a JSON argv array")
                    repair_env = dict(os.environ)
                    repair_env.pop("LOCAL_MODEL_AI_REPAIR_COMMAND", None)
                    result = subprocess.run(argv, input=json.dumps(task, ensure_ascii=False), capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=600, env=repair_env,
                        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
                    with (directory / "repair-driver.jsonl").open("a", encoding="utf-8", newline="\n") as log:
                        log.write(json.dumps({"round": round_number + 1, "argv": argv,
                            "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, ensure_ascii=False) + "\n")
                except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                    path, _ = repair_task(directory, "AI repair driver: " + str(error), round_number + 1)
                    raise AIRepairRequired(path, str(error)) from error
            # A handler's claim of success is not enough: always recheck real state.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("LOCAL_MODEL_CONFIG", str(DEFAULT_CONFIG)))
    parser.add_argument("--state-dir", default=os.environ.get("LOCAL_MODEL_CLIENT_STATE_DIR"))
    args = parser.parse_args(argv)
    try:
        result = ensure_current(read_json(args.config), state_dir=args.state_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except AIRepairRequired as exc:
        print(json.dumps(exc.repair_request, ensure_ascii=False), file=sys.stderr)
        return 75
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("check_opencode.py: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
