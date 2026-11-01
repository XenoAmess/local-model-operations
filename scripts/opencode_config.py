"""Reusable OpenCode exact-permission configuration generator.

``build_config(executor, *, workspace, worktree, owned_files, max_output_tokens=16000)``
is a pure, stdlib-only function: it performs no I/O, sends no HTTP or model requests,
never runs Git or subprocesses, and never installs, updates, writes, or debug-runs
OpenCode.  It returns a fresh configuration dict derived solely from the shared
executor mapping, which is the sole endpoint/model authority (no loopback proxy
address, no hard-coded model/IP, no silent fallback).

Permission enforcement assumption, stated explicitly: this module only produces a
configuration that a supported OpenCode version is expected to parse.  A successful
parse (or ``debug config`` exit 0) is NOT proof of live permission matching.  The
generated edit grants are worktree-relative, forward-slash patterns because, on the
actual non-Git Windows worktree (disk root), OpenCode 1.19.5 evaluates permission
patterns relative to its worktree root -- neither relative to the launch working
directory nor as absolute input paths.  Lexical path validation here does NOT prove
symlink safety; the caller must still supply the actual trusted workspace/worktree
discovered for its installed OpenCode version.

Actual 1.19.5 source semantics this shape relies on (v1.19.5 read/glob/grep/
external-directory/project instance-context references; not live-verified here):
- the read tool asks its permission with ``path.relative(worktree, filepath)``
  patterns, so worktree-relative edit/read patterns are the right coordinate;
- glob and grep ask with their QUERY pattern strings (glob pattern / regex), NOT
  directories, so the blanket ``glob``/``grep`` allows do not restrict or broaden
  searched directories; directory bounds there come from external_directory;
- external_directory fires only when ``containsPath`` fails, and non-Git projects
  set the raw instance worktree to ``"/"`` as a sentinel that SKIPS the worktree
  check; a raw ``D:/`` worktree is not that sentinel.  Therefore a default
  external_directory deny is NOT a general filesystem sandbox; it denies only
  prompts outside the actual instance directory/worktree context.

Corrections relative to the private pilot evidence (defects, not templates):
- edit allows are exactly the worktree-relative owned-file patterns (never
  workspace-relative-only, never absolute, never directory-wide, and external_directory
  stays denied rather than being loosened to fix a path error);
- the internal ``invalid`` tool is explicitly allowed as pure diagnosis so default
  deny does not mask truncated/invalid tool arguments;
- ``maxOutputTokens``/``maxRetries`` are never emitted as extra model API options;
  the finite per-response output budget uses the standard ``max_tokens`` option plus
  model ``limit.output`` metadata only;
- no steps/maxSteps, total request count, or whole-session wall cap is encoded.

The optional CLI adapter reads only ``--executor PATH``, accepts explicit
``--workspace``/``--worktree``/repeated ``--owned-file``/``--max-output-tokens``,
and prints the generated JSON to stdout.  Maintenance (daily version checks) belongs
to the actual model client entry, not this generator.  The separate ordinary three-message
caller is not modified by this module.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

CONFIG_SCHEMA = "https://opencode.ai/config.json"
PROVIDER_ID = "pilot"
AGENT_ID = "pilot"
# Client metadata inherited from the reference, not a measured backend capacity.
MODEL_LIMIT_CONTEXT = 1048576
MAX_OUTPUT_TOKENS_LIMIT = 16000

# Exact permission paths must not introduce matcher patterns or Win32 aliases.
_PATTERNS = re.compile(r"[*?\[\]{}<>]")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + str(n) for prefix in ("COM", "LPT") for n in range(1, 10)
}


class ConfigError(ValueError):
    """Raised for malformed authority inputs or rejected path/limit values."""


def _validate_prefix_parts(parts, label, *, windows=False):
    """Validate literal components before constructing exact permission keys."""
    for part in parts:
        if part in ("", ".", "..") or any(ord(c) < 32 or ord(c) == 127 for c in part):
            raise ConfigError(label + " has an invalid or traversal component")
        if _PATTERNS.search(part) or part.lower() == ".git":
            raise ConfigError(label + " has wildcard/metacharacters or a .git component")
        if windows and (":" in part or part.endswith((" ", "."))
                        or part.split(".", 1)[0].upper() in _WINDOWS_DEVICES):
            raise ConfigError(label + " has a Windows device, ADS or ambiguous component")


def _split_flavored(path):
    """Pure lexical paths: absolute D:/ and / are valid; D: and D:x are not."""
    if not isinstance(path, str) or not path:
        raise ConfigError("path must be a nonempty absolute string")
    windows = bool(_WINDOWS_DRIVE.match(path))
    if windows:
        parsed = PureWindowsPath(path)
        if not parsed.is_absolute() or len(parsed.drive) != 2:
            raise ConfigError("drive-relative or device coordinates are not accepted")
        flavor, anchor = "windows", parsed.drive.lower() + "/"
    else:
        if "\\" in path:
            raise ConfigError("mixed-flavor, UNC or device coordinates are not accepted")
        parsed = PurePosixPath(path)
        if not parsed.is_absolute() or parsed.anchor != "/":
            raise ConfigError("path must have an ordinary absolute root")
        flavor, anchor = "posix", "/"
    parts = list(parsed.parts[1:])
    _validate_prefix_parts(parts, "path", windows=windows)
    if not windows and parts and parts[0] == "dev":
        raise ConfigError("absolute POSIX device coordinates are not accepted")
    return flavor, anchor, parts


def _normalize_owned_entry(entry, *, windows):
    """Reject absolute/drive-relative paths and ambiguous exact-file grants."""
    if not isinstance(entry, str) or not entry:
        raise ConfigError("owned file must be a nonempty relative string")
    if _WINDOWS_DRIVE.match(entry) or entry.startswith(("/", "\\")):
        raise ConfigError("owned file must be workspace-relative")
    if not windows and "\\" in entry:
        raise ConfigError("POSIX owned file cannot use Windows separators")
    parts = entry.replace("\\", "/").split("/")
    _validate_prefix_parts(parts, "owned file", windows=windows)
    return parts


def _validate_executor(executor):
    """Validate the configured HTTP authority without IO, lookup or fallback."""
    if not isinstance(executor, dict):
        raise ConfigError("executor must be an already-decoded mapping")
    base_url, model = executor.get("base_url"), executor.get("model")
    if not isinstance(base_url, str) or not base_url or any(ord(c) <= 32 for c in base_url):
        raise ConfigError("executor base_url must be a nonempty URL without whitespace")
    try:
        split = urlsplit(base_url)
        port = split.port
    except ValueError as exc:
        raise ConfigError("executor base_url is malformed") from exc
    if (split.scheme not in ("http", "https") or not split.hostname
            or split.username is not None or split.password is not None
            or "?" in base_url or "#" in base_url or "\\" in base_url
            or split.netloc.endswith(":") or (port is not None and not 1 <= port <= 65535)
            or (split.path and not split.path.startswith("/")) or ".." in split.path.split("/")):
        raise ConfigError("executor base_url has an invalid authority, port or suffix")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ConfigError("executor model must be a simple alias")
    return base_url, model


def _validate_max_output_tokens(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("max_output_tokens must be an integer (bools rejected)")
    if not 1 <= value <= MAX_OUTPUT_TOKENS_LIMIT:
        raise ConfigError(
            "max_output_tokens must be within 1..%d: %r" % (MAX_OUTPUT_TOKENS_LIMIT, value)
        )
    return value


def _validate_paths(workspace, worktree):
    ws_flavor, ws_anchor, ws_parts = _split_flavored(workspace)
    wt_flavor, wt_anchor, wt_parts = _split_flavored(worktree)
    if ws_flavor != wt_flavor:
        raise ConfigError("workspace and worktree must use the same path flavor")
    if ws_anchor.lower() != wt_anchor.lower():
        raise ConfigError("workspace and worktree must share the same root/drive")
    # Windows path/drive components compare case-insensitively; POSIX stays
    # case-sensitive.  The emitted pattern keeps the actual workspace suffix
    # casing, never a lowercased user filename.
    if ws_flavor == "windows":
        lowered_ws = [part.lower() for part in ws_parts]
        lowered_wt = [part.lower() for part in wt_parts]
        contained = lowered_ws[: len(lowered_wt)] == lowered_wt
    else:
        contained = ws_parts[: len(wt_parts)] == wt_parts
    if not contained:
        raise ConfigError("workspace must be within the worktree")
    return ws_parts[len(wt_parts):]


def build_config(executor, *, workspace, worktree, owned_files, max_output_tokens=16000):
    """Return a fresh OpenCode configuration dict for the exact permission set.

    Parameters:
      executor: already-decoded mapping; sole endpoint/model authority.
      workspace/worktree: explicit absolute path strings of the same Windows
      (drive-anchored) or POSIX flavor; workspace must be within worktree.
      owned_files: nonempty sequence of exact file paths relative to workspace.
      max_output_tokens: finite per-response output budget, 1..16000 int.
    """
    base_url, model = _validate_executor(executor)
    max_output_tokens = _validate_max_output_tokens(max_output_tokens)
    workspace_tail = _validate_paths(workspace, worktree)
    if not isinstance(owned_files, (list, tuple)):
        raise ConfigError("owned_files must be a nonempty list or tuple of file paths")
    owned_parts = []
    for entry in owned_files:
        owned_parts.append(_normalize_owned_entry(entry, windows=bool(_WINDOWS_DRIVE.match(workspace))))
    if not owned_parts:
        raise ConfigError("owned_files must be nonempty")

    # Actual edit allow patterns: worktree-relative, forward slashes.
    edit_grants = {}
    for parts in owned_parts:
        pattern = "/".join([*workspace_tail, *parts])
        edit_grants[pattern] = "allow"

    permissions = {
        "*": "deny",
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "edit": {"*": "deny", **edit_grants},
        "external_directory": "deny",
        # Internal invalid tool: explicitly allowed as pure diagnosis so default
        # deny cannot mask truncated/invalid tool arguments (source-supported
        # 1.19.5 behavior; live matching still requires owner verification).
        "invalid": "allow",
        # No shell/Git/network/business/delegation permission.
        "bash": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "task": "deny",
    }

    model_options = {
        "baseURL": base_url,
        "apiKey": "local",
    }
    model_metadata = {
        "name": model,
        "tool_call": True,
        "temperature": True,
        "limit": {"context": MODEL_LIMIT_CONTEXT, "output": max_output_tokens},
        "options": {
            "max_tokens": max_output_tokens,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }
    agent = {
        "mode": "primary",
        "description": "Exact-permission OpenCode source task agent",
        "temperature": 0,
        "permission": {key: (dict(value) if isinstance(value, dict) else value)
                       for key, value in permissions.items()},
    }
    return {
        "$schema": CONFIG_SCHEMA,
        "model": PROVIDER_ID + "/" + model,
        "small_model": PROVIDER_ID + "/" + model,
        "default_agent": AGENT_ID,
        "enabled_providers": [PROVIDER_ID],
        "provider": {
            PROVIDER_ID: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Shared executor local model",
                "options": model_options,
                "models": {model: model_metadata},
            }
        },
        "agent": {AGENT_ID: agent},
        "permission": permissions,
        "share": "disabled",
        "snapshot": False,
        "autoupdate": False,
        "plugin": [],
        "mcp": {},
        "formatter": False,
        "lsp": False,
        "compaction": {"auto": False, "prune": False},
        "instructions": [],
    }


def _main(argv=None):
    """Optional adapter: read only --executor PATH, print generated JSON to stdout."""
    parser = argparse.ArgumentParser(
        description="Generate an OpenCode exact-permission config from the shared executor."
    )
    parser.add_argument("--executor", required=True, help="path to the executor JSON to read")
    parser.add_argument("--workspace", required=True, help="absolute workspace path")
    parser.add_argument("--worktree", required=True, help="absolute worktree path")
    parser.add_argument("--owned-file", action="append", required=True,
                        dest="owned_files", help="repeatable workspace-relative exact file path")
    parser.add_argument("--max-output-tokens", type=int, default=16000,
                        dest="max_output_tokens", help="finite per-response output budget (1..16000)")
    args = parser.parse_args(argv)
    try:
        with open(args.executor, "r", encoding="utf-8") as handle:
            executor = json.load(handle)
    except OSError as exc:
        parser.error("cannot read --executor: " + str(exc))
    except ValueError as exc:
        parser.error("--executor is not valid JSON: " + str(exc))
    try:
        config = build_config(
            executor,
            workspace=args.workspace,
            worktree=args.worktree,
            owned_files=args.owned_files,
            max_output_tokens=args.max_output_tokens,
        )
    except ConfigError as exc:
        parser.error(str(exc))
    json.dump(config, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
