#!/usr/bin/env python3
"""Portable extraction of the existing task-local urllib/SSE caller (stdlib only).

Makes one task-local HTTP request, with configured transport retries. It does not
edit source, run candidates, schedule work, or perform downstream business actions.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse
import datetime
import getpass
import http.client
import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.request


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "executor.json"
SPEC_KEYS = ("model", "temperature", "chat_template_kwargs", "response_format",
             "max_tokens", "stream", "stream_options")


JSON_SYNTAX_MAX_BYTES = 1048576


class NonJsonCandidateConstant(ValueError):
    pass


def _reject_candidate_constant(_value):
    raise NonJsonCandidateConstant


def candidate_json_syntax(text, *, complete_stream, finish):
    """Bounded syntax metadata only; never changes dispatch or adoption decisions."""
    result = {"status": "UNKNOWN", "top_level_type": "UNKNOWN",
              "reason": "INCOMPLETE_STREAM", "error": None,
              "offset_units": "Unicode code points",
              "max_utf8_bytes": JSON_SYNTAX_MAX_BYTES,
              "semantic_review": "OWNER_REVIEW_REQUIRED"}
    if not complete_stream:
        return result
    if finish != "stop":
        result["reason"] = "NON_STOP_FINISH"
        return result
    # Check characters first, bounding the temporary UTF8 allocation to 4*cap.
    if len(text) > JSON_SYNTAX_MAX_BYTES:
        result["reason"] = "BYTE_LIMIT"
        return result
    try:
        raw = text.encode("utf-8")
    except UnicodeError:
        result["reason"] = "UTF8_UNENCODABLE"
        return result
    if len(raw) > JSON_SYNTAX_MAX_BYTES:
        result["reason"] = "BYTE_LIMIT"
        return result
    try:
        value = json.loads(text, parse_constant=_reject_candidate_constant)
        result.update(status="VALID", reason="COMPLETE_STOP_JSON",
                      top_level_type={dict: "object", list: "array", str: "string",
                                      int: "number", float: "number", bool: "boolean",
                                      type(None): "null"}[type(value)])
    except json.JSONDecodeError as exc:
        result.update(status="INVALID", reason="JSON_SYNTAX",
                      error={"class": "JSONDecodeError", "line": exc.lineno,
                             "column": exc.colno, "offset": exc.pos})
    except NonJsonCandidateConstant:
        result.update(status="INVALID", reason="NON_JSON_CONSTANT",
                      error={"class": "NonJsonConstant"})
    except (ValueError, RecursionError, MemoryError):
        result["reason"] = "PARSER_LIMIT"
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2),
                          encoding="utf-8", newline="\n")


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class LocalEvidenceIOError(OSError):
    """A local evidence operation failed; it is never a network retry reason."""


def spec_path(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def prepare_request(path, config):
    """Resolve all spec material against the spec's directory, never the cwd."""
    path = Path(path).resolve()
    request = read_json(path)
    if "body" in request:
        request = request["body"]
    elif "request" in request:
        request = request["request"]
    if "messages" not in request:
        spec = request
        stable_path = spec.get("stable_source_path") or spec.get("source_path")
        if stable_path:
            stable = spec_path(path.parent, stable_path).read_text(encoding="utf-8-sig")
        else:
            stable = "\n\n".join(
                "FILE " + str(name) + "\n" +
                spec_path(path.parent, name).read_text(encoding="utf-8-sig") +
                "\nEND FILE " + str(name) for name in spec["source_files"])
        task_path = spec.get("task_path") or spec.get("final_task_path")
        final = spec_path(path.parent, task_path).read_text(encoding="utf-8-sig")
        request = {key: spec[key] for key in SPEC_KEYS if key in spec}
        request["messages"] = [
            {"role": "system", "content": config["prompting"]["system_template"]},
            {"role": "user", "content": stable},
            {"role": "user", "content": final}]
    original_system = request["messages"][0] if request.get("messages") else None
    request.setdefault("model", config["model"])
    for key, value in config["defaults"].items():
        request.setdefault(key, value)
    messages = request["messages"]
    if len(messages) != 3 or [m.get("role") for m in messages] != ["system", "user", "user"]:
        raise ValueError("Exactly system, user source, user task messages are required")
    messages[0] = {"role": "system", "content": config["prompting"]["system_template"]}
    if not all(isinstance(m.get("content"), str) for m in messages):
        raise ValueError("Each message content must be a string")
    if request["model"] != config["model"]:
        raise ValueError("Request model must match the selected configuration")
    budget = request.get("max_tokens")
    if type(budget) is not int or not 1 <= budget <= 16000:
        raise ValueError("max_tokens must be an integer in 1..16000")
    request.update(stream=True, stream_options={"include_usage": True})
    return request, original_system


def dispatch(request_path, task_id, out, config, machine_id, owner, stop_file):
    request, original_system = prepare_request(request_path, config)
    out = Path(out).resolve()
    if out in (REPO_ROOT.resolve(), Path(__file__).resolve().parent):
        raise ValueError("Use a unique per-task evidence directory, not the repo/script root")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "EVENTS.jsonl").exists():
        raise ValueError("Existing dispatch log: do not repeat this task directory")
    # Atomic and persistent: parallel callers cannot overwrite each other's REQUEST.
    try:
        with (out / "DISPATCH.claim").open("x", encoding="utf-8") as claim:
            claim.write(json.dumps({"task_id": task_id, "at_utc": utc()}))
    except FileExistsError as exc:
        raise ValueError("Evidence directory already claimed; choose a new directory") from exc
    body = json.dumps(request, ensure_ascii=False).encode("utf-8")
    (out / "REQUEST.json").write_bytes(body)
    save_json(out / "REQUEST-PREPARATION.json", {
        "input_path": str(Path(request_path).resolve()), "owner": owner,
        "machine_id": machine_id, "base_url": config["base_url"],
        "system_normalized_to_exact_config": original_system != request["messages"][0],
        "original_system": original_system, "source_and_final_task_unchanged": True})

    def local_io(operation, action):
        try:
            return action()
        except LocalEvidenceIOError:
            raise
        except OSError as exc:
            raise LocalEvidenceIOError(operation + ": " + repr(exc)) from exc

    def save(name, value):
        return local_io("writing " + name, lambda: save_json(out / name, value))

    @contextmanager
    def raw_evidence(path):
        raw = local_io("opening " + path.name, lambda: open(path, "wb"))
        try:
            yield raw
        finally:
            pending = sys.exc_info()[1]
            try:
                local_io("closing " + path.name, raw.close)
            except LocalEvidenceIOError as exc:
                if pending is not None:
                    raise LocalEvidenceIOError(str(exc) + "; after " + repr(pending)) from exc
                raise

    def emit(event, **data):
        row = {"event": event, "at_utc": utc(), "machine_id": machine_id,
               "executor": owner, "owner": owner, "task_id": task_id,
               "base_url": config["base_url"], **data}
        def append_row():
            with (out / "EVENTS.jsonl").open("a", encoding="utf-8", newline="\n") as log:
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            local_io("writing EVENTS.jsonl", append_row)
        except LocalEvidenceIOError as original:
            # Neither diagnostic sink may turn local I/O into transport retry.
            try:
                local_io("printing " + event, lambda: print(json.dumps(row, ensure_ascii=False), flush=True))
            except LocalEvidenceIOError as printing:
                raise LocalEvidenceIOError(str(original) + "; " + str(printing)) from printing
            raise
        local_io("printing " + event, lambda: print(json.dumps(row, ensure_ascii=False), flush=True))

    def finish_evidence(name, action):
        try:
            local_io("writing " + name, action)
            return True
        except LocalEvidenceIOError as exc:
            if not local_evidence_io:
                raise
            # Best effort only after an already classified failed attempt.
            print("call.py: local evidence I/O failure: " + str(exc), file=sys.stderr, flush=True)
            return False

    policy = config["transient_retries"]
    attempts = []
    success = False
    local_evidence_io = False
    headers = {"Content-Type": "application/json"}
    key_env = config.get("authentication", {}).get("api_key_env", "LOCAL_MODEL_API_KEY")
    key = os.environ.get(key_env) if key_env else None
    if key:
        headers["Authorization"] = "Bearer " + key
    elif config.get("authentication", {}).get("required", False):
        raise ValueError("Authentication required: set the configured api_key_env")
    timeouts = config.get("timeouts", {})
    for attempt in range(1, policy["maximum_attempts"] + 1):
        if stop_file is not None and Path(stop_file).exists():
            emit("CANCELLED_BEFORE_POST", attempt=attempt, reason="explicit_http_stop_file")
            break
        prefix = "ATTEMPT" + str(attempt)
        start, started = time.monotonic(), utc()
        status = headers_ms = ttft = reasoning_ttft = finish = usage = None
        done, content, failure, retry = False, [], None, False
        complete_stream = False
        local_evidence_io = False
        post_invoked = False
        reasoning = {"reasoning_content": [], "reasoning": []}
        try:
            req = urllib.request.Request(config["base_url"].rstrip("/") + "/chat/completions",
                                         data=body, headers=headers)
            with raw_evidence(out / (prefix + '-RESPONSE.sse')) as raw:
                emit("POST_BEGIN", attempt=attempt, request_path=str(out / "REQUEST.json"),
                     max_tokens=request["max_tokens"])
                post_invoked = True
                with urllib.request.urlopen(req, timeout=timeouts.get('read_seconds', 180)) as response:
                    headers_ms = (time.monotonic() - start) * 1000
                    status = response.status
                    save(prefix + "-HEADERS.json", {"http_status": status,
                         "http_headers_ms": headers_ms, "headers": dict(response.headers.items())})
                    emit("HEADERS", attempt=attempt, http_status=status, http_headers_ms=headers_ms)
                    for line in response:
                        local_io("writing " + prefix + "-RESPONSE.sse", lambda: raw.write(line))
                        local_io("flushing " + prefix + "-RESPONSE.sse", raw.flush)
                        if time.monotonic() - start > timeouts.get("total_seconds", 900):
                            raise TimeoutError("total model HTTP timeout")
                        if not line.startswith(b"data:"):
                            continue
                        data = line[5:].strip()
                        if data == b"[DONE]":
                            done = True
                            continue
                        try:
                            chunk = json.loads(data)
                        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                            # readline returns a non-LF tail only at EOF. Keep complete
                            # malformed events nonretryable; a truncated tail is a
                            # transport failure, not a candidate to splice or salvage.
                            if not line.endswith(b"\n"):
                                raise http.client.IncompleteRead(line) from exc
                            raise
                        if chunk.get("usage") is not None:
                            usage = chunk["usage"]
                        for choice in chunk.get("choices", []):
                            if choice.get("finish_reason") is not None:
                                finish = choice["finish_reason"]
                            delta = choice.get("delta", {})
                            for field in reasoning:
                                value = delta.get(field)
                                if isinstance(value, str) and value:
                                    if reasoning_ttft is None:
                                        reasoning_ttft = (time.monotonic() - start) * 1000
                                        save(prefix + "-FIRST-REASONING.json", {
                                            "first_nonempty_reasoning_delta_ms": reasoning_ttft,
                                            "delta_field": field, "observed_at_utc": utc()})
                                        emit("FIRST_REASONING", attempt=attempt,
                                             first_nonempty_reasoning_delta_ms=reasoning_ttft,
                                             delta_field=field)
                                    reasoning[field].append(value)
                            value = delta.get("content")
                            if isinstance(value, str) and value:
                                if ttft is None:
                                    ttft = (time.monotonic() - start) * 1000
                                    save(prefix + "-FIRST-CONTENT.json", {
                                        "first_nonempty_content_delta_ms": ttft,
                                        "observed_at_utc": utc()})
                                    emit("FIRST_CONTENT", attempt=attempt,
                                         first_nonempty_content_delta_ms=ttft)
                                content.append(value)
            if not done or finish is None:
                raise http.client.IncompleteRead(b"no complete SSE finish")
            complete_stream = True
            if finish != "stop":
                failure = "finish_reason_" + str(finish)
            else:
                try:
                    json.loads("".join(content))
                except (ValueError, TypeError) as exc:
                    failure = "invalid_candidate_json: " + str(exc)
        except LocalEvidenceIOError as exc:
            failure, retry, local_evidence_io = str(exc), False, True
            print("call.py: local evidence I/O failure: " + failure, file=sys.stderr, flush=True)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                ConnectionError, http.client.IncompleteRead, OSError) as exc:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else status
            failure = repr(exc)
            retry = (status in policy["retry_http_statuses"]
                     if isinstance(exc, urllib.error.HTTPError) else True)
            if isinstance(exc, urllib.error.HTTPError):
                error_body = exc.read()  # Network read, outside the local-write classifier.
                try:
                    local_io("writing " + prefix + "-HTTP-ERROR.txt",
                             lambda: (out / (prefix + "-HTTP-ERROR.txt")).write_bytes(error_body))
                except LocalEvidenceIOError as local_exc:
                    failure, retry, local_evidence_io = str(local_exc), False, True
                    print("call.py: local evidence I/O failure: " + failure, file=sys.stderr, flush=True)
        except Exception as exc:
            failure = repr(exc)
        content_saved = finish_evidence(prefix + "-CONTENT.txt", lambda:
            (out / (prefix + "-CONTENT.txt")).write_bytes("".join(content).encode("utf-8")))
        reasoning_text = {k: "".join(parts) for k, parts in reasoning.items() if parts}
        reasoning_path = None
        if reasoning_text:
            if finish_evidence(prefix + "-REASONING.json", lambda:
                    save(prefix + "-REASONING.json", reasoning_text)):
                reasoning_path = str(out / (prefix + "-REASONING.json"))
        result = {"started_at_utc": started, "attempt": attempt, "http_status": status,
                  "http_headers_ms": headers_ms, "first_nonempty_content_delta_ms": ttft,
                  "total_ms": (time.monotonic() - start) * 1000,
                  "finish_reason": finish, "sse_done": done, "usage": usage,
                  "cached_prompt_tokens_if_reported": ((usage or {}).get(
                      "prompt_tokens_details") or {}).get("cached_tokens"),
                  "failure": failure,
                  "content_path": str(out / (prefix + "-CONTENT.txt")) if content_saved else None,
                  "local_evidence_io_failure": local_evidence_io,
                  "post_invoked": post_invoked,
                  "json_syntax": candidate_json_syntax(
                      "".join(content), complete_stream=complete_stream, finish=finish),
                  "candidate_complete": failure is None,
                  "candidate_review": "NOT_YET_REVIEWED", "adopted": False,
                  "first_nonempty_reasoning_delta_ms": reasoning_ttft,
                  "reasoning_delta_fields_seen": list(reasoning_text),
                  "reasoning_path": reasoning_path}
        finish_evidence(prefix + "-RESULT.json", lambda: save(prefix + "-RESULT.json", result))
        attempts.append(result)
        finish_evidence("EVENTS.jsonl", lambda: emit("ATTEMPT_END", **result))
        if failure is None:
            success = True
            break
        if not retry or attempt == policy["maximum_attempts"]:
            break
        if stop_file is not None and Path(stop_file).exists():
            emit("RETRY_CANCELLED", attempt=attempt, reason="explicit_http_stop_file")
            break
        delay = policy["backoff_seconds"][attempt - 1] * random.uniform(
            1 - policy["jitter_ratio"], 1 + policy["jitter_ratio"])
        emit("RETRY_BACKOFF", attempt=attempt, delay_seconds=delay, scope="model_HTTP_only")
        time.sleep(delay)
    finish_evidence("SUMMARY.json", lambda: save("SUMMARY.json", {
        "task_id": task_id, "machine_id": machine_id, "owner": owner,
        "success": success, "attempts": attempts, "adopted": False}))
    return 0 if success else 1


def client_preflight(config):
    if __package__:
        from .check_opencode import ensure_current
    else:
        from check_opencode import ensure_current
    result = ensure_current(config)
    if not result["cached"]:
        print(json.dumps({"event": "OPENCODE_DAILY_CHECK", "date": result["date"],
                          "installed_version": result["installed_version"],
                          "registry_latest": result["registry_latest"],
                          "updated": result["updated"]}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_path", help="spec or complete request JSON")
    parser.add_argument("task_id")
    parser.add_argument("output_dir", nargs="?", help="legacy positional evidence directory")
    parser.add_argument("executor", nargs="?", help="legacy positional owner")
    parser.add_argument("--config", default=os.environ.get("LOCAL_MODEL_CONFIG", str(DEFAULT_CONFIG)))
    parser.add_argument("--output", help="unique evidence directory")
    parser.add_argument("--output-root", default=os.environ.get("LOCAL_MODEL_OUTPUT_ROOT"))
    parser.add_argument("--machine-id", default=os.environ.get("LOCAL_MODEL_MACHINE_ID"))
    parser.add_argument("--owner", default=os.environ.get("LOCAL_MODEL_OWNER"))
    parser.add_argument("--stop-file", default=os.environ.get("LOCAL_MODEL_STOP_FILE"))
    args = parser.parse_args(argv)
    try:
        config = read_json(args.config)
        root = Path(args.output_root) if args.output_root else Path.cwd() / ".local-model-evidence"
        out = args.output or args.output_dir
        if out is None:
            if args.task_id in ("", ".", "..") or "/" in args.task_id or "\\" in args.task_id:
                raise ValueError("task_id must be a directory name when output is implicit")
            out = root / args.task_id
        machine_id = args.machine_id or socket.gethostname()
        owner = args.owner or args.executor or getpass.getuser()
        stop_file = Path(args.stop_file) if args.stop_file else root / "STOP-NEW-HTTP.json"
        client_preflight(config)
        return dispatch(args.request_path, args.task_id, out, config, machine_id, owner, stop_file)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        if hasattr(exc, "repair_request"):
            print(json.dumps(exc.repair_request, ensure_ascii=False), file=sys.stderr)
            return 75
        print("call.py: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
