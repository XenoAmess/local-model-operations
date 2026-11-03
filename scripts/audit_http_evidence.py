"""Audit existing call.py evidence offline; stdout contains metadata, never bodies.

Only immediate fixed artifact names are opened. This is an evidence-format reader,
not a model caller, a semantic judge, or an operating-system security boundary.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

SCHEMA = "ordinary-http-evidence-audit/v1"
UNKNOWN = "UNKNOWN"
REVIEW = "OWNER_REVIEW_REQUIRED"
FINISHES = {"stop", "length", "tool_calls", "function_call", "content_filter"}
ROLES = {"system", "user", "assistant", "tool", "developer", "function"}
EVENTS = {"POST_BEGIN", "HEADERS", "FIRST_CONTENT", "ATTEMPT_END"}
METRICS = ("http_status", "http_headers_ms", "first_nonempty_content_delta_ms", "total_ms")
DEFAULTS = dict(max_artifact_bytes=8388608, max_total_bytes=67108864,
                max_events=10000, max_attempts=64, max_directory_entries=512)
ATTEMPT_FILE = re.compile(r"ATTEMPT([1-9][0-9]{0,8})-(RESPONSE\.sse|CONTENT\.txt|RESULT\.json)\Z")


class NonJsonConstant(ValueError):
    pass


def _reject_constant(_value):
    raise NonJsonConstant


def _loads(text):
    return json.loads(text, parse_constant=_reject_constant)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text_pin(value):
    if not isinstance(value, str):
        return {"utf8_bytes": UNKNOWN, "sha256": UNKNOWN}
    try:
        raw = value.encode("utf-8")
        return {"utf8_bytes": len(raw), "sha256": _sha(raw)}
    except UnicodeError:
        return {"utf8_bytes": UNKNOWN, "sha256": UNKNOWN}


def _number(value):
    if type(value) in (int, float):
        try:
            if value >= 0 and math.isfinite(value):
                return value
        except OverflowError:
            pass
    return UNKNOWN


def _integer(value):
    return value if type(value) is int and value >= 0 else UNKNOWN


def _bool(value):
    return value if type(value) is bool else UNKNOWN


def _enum(value, choices):
    return value if isinstance(value, str) and value in choices else UNKNOWN


def _linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


class _Reader:
    def __init__(self, root, limits, errors):
        self.root, self.limits, self.errors = root, limits, errors
        self.remaining = limits["max_total_bytes"]

    def read(self, name, label, attempt=None):
        meta = {"status": UNKNOWN, "bytes": UNKNOWN, "sha256": UNKNOWN}
        def fail(code):
            meta["status"] = code
            error = {"artifact": label, "code": code}
            if attempt is not None:
                error["attempt"] = attempt
            self.errors.append(error)
            return None, meta
        path = self.root / name
        try:
            info = path.lstat()
            if _linked(path):
                return fail("symlink_or_reparse_ignored")
            if not stat.S_ISREG(info.st_mode):
                return fail("not_regular_file")
            meta["bytes"] = info.st_size
            cap = min(self.limits["max_artifact_bytes"], self.remaining)
            if info.st_size > cap:
                return fail("artifact_limit" if info.st_size > self.limits["max_artifact_bytes"] else "total_byte_limit")
            # Bound the actual read too, including a file that grows after stat.
            with path.open("rb") as stream:
                raw = stream.read(cap + 1)
            self.remaining -= len(raw)
            if len(raw) > cap:
                return fail("read_limit")
            if len(raw) != info.st_size:
                return fail("size_changed_during_read")
            meta.update(status="present", bytes=len(raw), sha256=_sha(raw))
            return raw, meta
        except FileNotFoundError:
            return fail("missing")
        except OSError:
            return fail("unreadable")


def _object(raw, errors, label, attempt=None):
    if raw is None:
        return None
    code = None
    try:
        value = _loads(raw.decode("utf-8"))
        if isinstance(value, dict):
            return value
        code = "expected_object"
    except (UnicodeError, json.JSONDecodeError, NonJsonConstant):
        code = "invalid_json_or_utf8"
    except (ValueError, RecursionError):
        code = "parser_limit"
    error = {"artifact": label, "code": code}
    if attempt is not None:
        error["attempt"] = attempt
    errors.append(error)
    return None


def _request(raw, meta, errors):
    out = {"artifact": meta, "fixed_three_messages": UNKNOWN, "parameters": {},
           "messages": [], "source_message_sha256": UNKNOWN}
    request = _object(raw, errors, "request")
    if request is None:
        return out
    model = request.get("model")
    out["parameters"] = {
        "model": model if model == "qwen38-coder" else UNKNOWN,
        "model_sha256": _text_pin(model)["sha256"],
        "temperature": _number(request.get("temperature")),
        "max_tokens": _integer(request.get("max_tokens")),
        "stream": _bool(request.get("stream")),
    }
    for container, key, dest in (("stream_options", "include_usage", "include_usage"),
                                  ("chat_template_kwargs", "enable_thinking", "thinking")):
        obj = request.get(container)
        out["parameters"][dest] = _bool(obj.get(key)) if isinstance(obj, dict) else UNKNOWN
    fmt = request.get("response_format")
    out["parameters"]["response_format_type"] = _enum(fmt.get("type"), {"json_object", "json_schema", "text"}) if isinstance(fmt, dict) else UNKNOWN
    messages = request.get("messages")
    if isinstance(messages, list):
        exact = (len(messages) == 3 and all(isinstance(m, dict) for m in messages)
                 and [m.get("role") for m in messages] == ["system", "user", "user"]
                 and all(isinstance(m.get("content"), str) for m in messages))
        out["fixed_three_messages"] = exact
        for ordinal, message in enumerate(messages, 1):
            msg = message if isinstance(message, dict) else {}
            out["messages"].append(dict(ordinal=ordinal, role=_enum(msg.get("role"), ROLES),
                                        **_text_pin(msg.get("content"))))
        if exact:
            out["source_message_sha256"] = _text_pin(messages[1]["content"])["sha256"]
    return out


def _sse(raw):
    out = {"finish_reason": UNKNOWN, "done": UNKNOWN, "complete": UNKNOWN, "anomalies": [],
           "usage": _record(None)["usage"]}
    if raw is None:
        return out, None
    done, finishes, parts, indices, anomalies = False, [], [], set(), set()
    for line in raw.splitlines(keepends=True):
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if done:
            anomalies.add("data_after_done")
        if payload == b"[DONE]":
            done = True
            continue
        try:
            chunk = _loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            anomalies.add("malformed_data_chunk")
            continue
        if not isinstance(chunk, dict) or not isinstance(chunk.get("choices"), list):
            anomalies.add("unsupported_chunk_shape")
            continue
        if chunk.get("usage") is not None:
            if not isinstance(chunk["usage"], dict):
                anomalies.add("unsupported_usage_shape")
            else:
                out["usage"] = _record(chunk)["usage"]
        choices = chunk["choices"]
        if len(choices) > 1:
            anomalies.add("multiple_choices")
        for choice in choices:
            if not isinstance(choice, dict):
                anomalies.add("unsupported_choice_shape")
                continue
            if "index" in choice:
                index = choice["index"]
                if type(index) is not int or index != 0:
                    anomalies.add("unsupported_choice_index")
                else:
                    indices.add(index)
            finish = choice.get("finish_reason")
            if finish is not None:
                if _enum(finish, FINISHES) == UNKNOWN:
                    anomalies.add("unsupported_finish_reason")
                else:
                    finishes.append(finish)
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                anomalies.add("unsupported_delta_shape")
                continue
            text = delta.get("content")
            if text is not None:
                if not isinstance(text, str) or _text_pin(text)["sha256"] == UNKNOWN:
                    anomalies.add("invalid_content_string")
                else:
                    parts.append(text)
    if len(finishes) > 1:
        anomalies.add("multiple_finish_records")
    finish = finishes[0] if len(finishes) == 1 else UNKNOWN
    out.update(finish_reason=finish, done=done,
               complete=done and len(finishes) == 1 and not anomalies,
               anomalies=sorted(anomalies))
    # A malformed stream is not a source of a salvaged complete candidate.
    # Saved CONTENT, if present, can still be syntax-checked independently.
    return out, None if anomalies else "".join(parts)


def _syntax(text):
    out = {"syntax": UNKNOWN, "type": UNKNOWN, "utf8_bytes": UNKNOWN, "sha256": UNKNOWN,
           "semantic_review": REVIEW}
    if text is None:
        return out
    out.update(_text_pin(text))
    try:
        value = _loads(text)
        out.update(syntax="VALID", type={dict: "object", list: "array", str: "string",
                                        int: "number", float: "number", bool: "boolean", type(None): "null"}[type(value)])
    except json.JSONDecodeError as exc:
        out.update(syntax="INVALID", syntax_error={"class": "JSONDecodeError", "line": exc.lineno,
                                                  "column": exc.colno, "position": exc.pos})
    except NonJsonConstant:
        out.update(syntax="INVALID", syntax_error={"class": "NonJsonConstant"})
    except (ValueError, RecursionError):
        out["syntax_error"] = {"class": "ParserLimit"}
    return out


def _record(obj):
    obj = obj or {}
    usage = obj.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    return {**{key: _number(obj.get(key)) for key in METRICS},
            "finish_reason": _enum(obj.get("finish_reason"), FINISHES),
            "sse_done": _bool(obj.get("sse_done")),
            "failure_present": obj.get("failure") is not None if "failure" in obj else UNKNOWN,
            "usage": {"prompt_tokens": _integer(usage.get("prompt_tokens")),
                      "completion_tokens": _integer(usage.get("completion_tokens")),
                      "cached_tokens": None if cached is None else _integer(cached)}}


def _events(raw, meta, limit, errors):
    by_attempt, complete = {}, raw is not None
    count = 0
    if raw is not None:
        for line in raw.splitlines():
            if not line.strip():
                continue
            count += 1
            if count > limit:
                errors.append({"artifact": "events", "code": "event_limit"})
                complete = False
                break
            row = _object(line, errors, "events")
            if row is None:
                complete = False
                continue
            attempt = row.get("attempt")
            if type(attempt) is not int or not 1 <= attempt <= 999999999:
                errors.append({"artifact": "events", "code": "invalid_attempt"})
                complete = False
                continue
            event = _enum(row.get("event"), EVENTS)
            if event != UNKNOWN:
                by_attempt.setdefault(attempt, {}).setdefault(event, []).append(row)
    return {"artifact": meta, "rows_examined": min(count, limit),
            "parse_complete": complete if raw is not None else UNKNOWN}, by_attempt


def _event_record(rows, parse_complete):
    counts = {key: len(rows.get(key, [])) for key in EVENTS}
    unique = lambda key: rows[key][0] if counts[key] == 1 else {}
    record = _record(unique("ATTEMPT_END"))
    record["first_content_event_ms"] = _number(unique("FIRST_CONTENT").get("first_nonempty_content_delta_ms"))
    record["headers_event_ms"] = _number(unique("HEADERS").get("http_headers_ms"))
    record["event_counts"] = counts
    record["lifecycle_complete"] = (True if parse_complete is True and counts["POST_BEGIN"] == counts["ATTEMPT_END"] == 1 else UNKNOWN)
    return record


def _attempt(reader, number, rows, events_complete):
    artifacts, data = {}, {}
    for key, suffix in (("sse", "RESPONSE.sse"), ("content", "CONTENT.txt"), ("result", "RESULT.json")):
        data[key], artifacts[key] = reader.read(f"ATTEMPT{number}-{suffix}", key, number)
    result = _object(data["result"], reader.errors, "result", number)
    recorded = _record(result)
    event_record = _event_record(rows, events_complete)
    stream, reconstructed = _sse(data["sse"])
    saved, discrepancies = None, []
    if data["content"] is not None:
        try:
            saved = data["content"].decode("utf-8")
        except UnicodeError:
            discrepancies.append("content_invalid_utf8")
    match = reconstructed == saved if reconstructed is not None and saved is not None else UNKNOWN
    if match is False:
        discrepancies.append("content_stream_mismatch")
    for stream_key, result_key in (("finish_reason", "finish_reason"), ("done", "sse_done")):
        if stream[stream_key] != UNKNOWN and recorded[result_key] != UNKNOWN and stream[stream_key] != recorded[result_key]:
            discrepancies.append("stream_result_" + result_key + "_conflict")
    for key in METRICS + ("finish_reason", "sse_done"):
        if recorded[key] != UNKNOWN and event_record[key] != UNKNOWN and recorded[key] != event_record[key]:
            discrepancies.append("result_end_" + key + "_conflict")
    for key, alias in (("first_nonempty_content_delta_ms", "first_content_event_ms"), ("http_headers_ms", "headers_event_ms")):
        if event_record[key] != UNKNOWN and event_record[alias] != UNKNOWN and event_record[key] != event_record[alias]:
            discrepancies.append("end_event_" + key + "_conflict")
    candidate = _syntax(reconstructed if reconstructed is not None else saved)
    candidate["source"] = "sse" if reconstructed is not None else "content" if saved is not None else UNKNOWN
    candidate["saved_content_matches_stream"] = match
    candidate["saved_content_lf_normalized_matches_stream"] = (
        saved.replace("\r\n", "\n").replace("\r", "\n") == reconstructed.replace("\r\n", "\n").replace("\r", "\n")
        if reconstructed is not None and saved is not None else UNKNOWN)
    candidate["eligibility"] = UNKNOWN
    if stream["finish_reason"] == "length" or recorded["finish_reason"] == "length":
        candidate["eligibility"] = "DISCARD_LENGTH"
    elif data["sse"] is not None:
        candidate["eligibility"] = ("REVIEW_ELIGIBLE" if stream["complete"] is True and stream["finish_reason"] == "stop"
                                    and candidate["syntax"] == "VALID" and not discrepancies else "NOT_REVIEW_ELIGIBLE")
    return {"attempt": number, "artifacts": artifacts, "stream": stream, "candidate": candidate,
            "recorded_metrics": {"result": recorded, "events": event_record}, "discrepancies": discrepancies}


def audit_http(root: Path, **overrides) -> dict:
    limits = {**DEFAULTS, **overrides}
    report = {"schema": SCHEMA, "mode_id": "ordinary_http_fixed3_candidate", "semantic_review": REVIEW,
              "limits": limits, "request": {}, "events": {}, "attempts": [], "errors": []}
    if set(limits) != set(DEFAULTS) or any(type(v) is not int or v < 1 for v in limits.values()):
        report["limits"] = {key: UNKNOWN for key in DEFAULTS}
        report["errors"].append({"artifact": "limits", "code": "invalid_limit"})
        return report
    root = Path(root)
    errors = report["errors"]
    try:
        if _linked(root) or not root.is_dir():
            raise ValueError
        attempts = set()
        with os.scandir(root) as entries:
            for count, entry in enumerate(entries, 1):
                if count > limits["max_directory_entries"]:
                    errors.append({"artifact": "directory", "code": "directory_entry_limit"})
                    return report
                match = ATTEMPT_FILE.fullmatch(entry.name)
                if match:
                    attempts.add(int(match[1]))
    except (OSError, ValueError):
        errors.append({"artifact": "directory", "code": "unreadable_or_linked_directory"})
        return report
    reader = _Reader(root, limits, errors)
    raw, meta = reader.read("REQUEST.json", "request")
    report["request"] = _request(raw, meta, errors)
    raw, meta = reader.read("EVENTS.jsonl", "events")
    report["events"], event_rows = _events(raw, meta, limits["max_events"], errors)
    attempts.update(event_rows)
    if len(attempts) > limits["max_attempts"]:
        errors.append({"artifact": "attempts", "code": "attempt_limit"})
        return report
    for number in sorted(attempts):
        report["attempts"].append(_attempt(reader, number, event_rows.get(number, {}), report["events"]["parse_complete"]))
    report["bytes_read"] = limits["max_total_bytes"] - reader.remaining
    return report


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise ValueError


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("directory", type=Path)
    for key, default in DEFAULTS.items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=default)
    try:
        args = vars(parser.parse_args(argv))
        report = audit_http(args.pop("directory"), **args)
    except (ValueError, OSError):
        report = {"schema": SCHEMA, "errors": [{"artifact": "cli", "code": "invalid_arguments"}]}
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
