"""Read existing OpenCode recordings; emit a sanitized diagnostic, never actions.

Only fixed JSON/JSONL artifacts and immediate http-* directories are read.
Tool argument paths, raw SSE, source snapshots and recorded Python are ignored.
This is a trace-format adapter, not an OS sandbox or proof of task correctness.
"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re


SCHEMA = "local-model-operations.opencode-trace-audit/v1"
TOOLS = {"read", "grep", "glob", "invalid", "write", "edit", "bash",
         "task", "webfetch", "websearch", "todowrite", "todoread", "question"}
ROLES = {"system", "developer", "user", "assistant", "tool", "function"}
STATUSES = {"completed", "error", "running", "pending"}
FINISHES = {"stop", "tool_calls", "length", "content_filter", "function_call"}


def _sha256_json(obj):
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def _sha256_str(s):
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def _integer(value, minimum=0):
    return value if type(value) is int and value >= minimum else None


def _number(value):
    if type(value) in (int, float):
        try:
            if math.isfinite(value):
                return value
        except OverflowError:
            pass
    return None


def _boolean(value):
    return value if type(value) is bool else None


def _enum(value, choices):
    return value if isinstance(value, str) and value in choices else "unknown"


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _parse_grep_output(output):
    """Keep file/line/content associations and multiplicity; reject partial forms."""
    lines = output.splitlines()
    if not lines:
        return None
    match = re.fullmatch(r"Found (\d+) matches?", lines[0])
    if not match:
        return None
    current_file = None
    file_matches = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        if line.endswith(":") and (line.startswith("/") or
                                     re.match(r"^[A-Za-z]:[/\\]", line)):
            current_file = line[:-1]
            file_matches.setdefault(current_file, [])
            continue
        item = re.fullmatch(r"\s*Line (\d+): (.*)", line)
        if item is None or current_file is None:
            return None
        file_matches[current_file].append((int(item[1]), item[2]))
    if sum(map(len, file_matches.values())) != int(match[1]):
        return None
    return {"file_matches": file_matches}


def _normalize_grep_multiset(parsed):
    # Model-proposed file-associated multiset retained; every output is parsed.
    fm = parsed["file_matches"]
    items = []
    for fname in sorted(fm.keys()):
        for ln, content in sorted(fm[fname], key=lambda x: (x[0], x[1])):
            items.append((fname, ln, content))
    return _sha256_json(items)


def _reject_constant(_value):
    raise ValueError


def _load_json(path, errors, record, optional=False):
    if path.is_symlink():
        errors.append({"record": record, "error": "symlink_ignored"})
        return None
    try:
        with path.open(encoding="utf-8-sig") as stream:
            value = json.load(stream, parse_constant=_reject_constant)
        if not isinstance(value, dict):
            errors.append({"record": record, "error": "expected_object"})
            return None
        return value
    except FileNotFoundError:
        if not optional:
            errors.append({"record": record, "error": "missing"})
    except (OSError, UnicodeError, ValueError, RecursionError):
        errors.append({"record": record, "error": "unreadable_or_invalid_json"})
    return None


def _request_metadata(request, ordinal, baseline):
    out = {"ordinal": ordinal}
    # An arbitrary model string can itself be a private path: show known aliases
    # and hash other names, rather than pass untrusted parameter text through.
    model = request.get("model")
    out["model"] = model if model == "qwen38-coder" else None
    out["model_sha256"] = _sha256_str(model) if isinstance(model, str) else None
    out["temperature"] = _number(request.get("temperature"))
    for key in ("max_tokens", "max_completion_tokens"):
        out[key] = _integer(request.get(key), 1)
    choice = request.get("tool_choice")
    if isinstance(choice, dict):
        out["tool_choice"] = "named_function" if choice.get("type") == "function" else "unknown"
    else:
        out["tool_choice"] = _enum(choice, {"auto", "none", "required"}) if choice is not None else None
    out["stream"] = _boolean(request.get("stream"))
    for obj_key, field, dest in (("stream_options", "include_usage", "include_usage"),
                                 ("chat_template_kwargs", "enable_thinking", "thinking")):
        obj = request.get(obj_key)
        out[dest] = _boolean(obj.get(field)) if isinstance(obj, dict) else None
    fmt = request.get("response_format")
    out["json_mode"] = (fmt.get("type") in ("json_object", "json_schema")
                        if isinstance(fmt, dict) else False if fmt is None else None)
    messages = request.get("messages")
    if not isinstance(messages, list):
        messages = []
    roles, calls, results = Counter(), [], []
    systems, user, user_present = [], None, False
    malformed = 0
    for message in messages:
        if not isinstance(message, dict):
            malformed += 1
            continue
        role = _enum(message.get("role"), ROLES)
        roles[role] += 1
        if role == "system":
            systems.append(message.get("content"))
        if role == "user" and not user_present:
            user, user_present = message.get("content"), True
        if role == "assistant":
            entries = message.get("tool_calls", [])
            if not isinstance(entries, list):
                malformed += 1
                continue
            for call in entries:
                if isinstance(call, dict) and isinstance(call.get("id"), str):
                    calls.append(call["id"])
                else:
                    malformed += 1
        if role == "tool":
            if isinstance(message.get("tool_call_id"), str):
                results.append(message["tool_call_id"])
            else:
                malformed += 1
    call_set, result_set = set(calls), set(results)
    out["role_counts"] = dict(roles)
    out["malformed_message_records"] = malformed
    out["linkage"] = {
        "unknown_result": sum(item not in call_set for item in results),
        "duplicate_result": len(results) - len(result_set),
        "duplicate_assistant_call_ids": len(calls) - len(call_set),
        "pending_calls": len(call_set - result_set),
    }
    out["system_present"], out["initial_user_present"] = bool(systems), user_present
    hashes = (_sha256_json(systems) if systems else None,
              _sha256_json(user) if user_present else None)
    for key, current, original in zip(("system_unchanged", "initial_user_unchanged"), hashes, baseline):
        out[key] = current == original if current is not None and original is not None else None
    return out, hashes


def _summary_metadata(summary):
    result = {}
    for field in ("http_status",):
        result[field] = _integer(summary.get(field))
    for field in ("content_ttft_ms", "first_tool_delta_ms"):
        value = _number(summary.get(field))
        result[field] = value if value is not None and value >= 0 else None
    for field in ("sse_done", "candidate_complete"):
        result[field] = _boolean(summary.get(field))
    result["finish_reason"] = (_enum(summary.get("finish_reason"), FINISHES)
                               if summary.get("finish_reason") is not None else None)
    result["error"] = summary.get("error") is not None
    for field in ("POST_BEGIN_utc", "ATTEMPT_END_utc"):
        result[field] = _utc(summary.get(field))
    return result


def _read_metadata(state, ordinal):
    inp = state.get("input")
    inp = inp if isinstance(inp, dict) else {}
    metadata = state.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    display = metadata.get("display")
    display = display if isinstance(display, dict) else {}
    output = state.get("output")
    output = output if isinstance(output, str) else ""
    cap = re.search(r"Output capped at\s+(\d+)\s*KB", output)
    continuation = re.search(r"Use offset=(\d+) to continue", output)
    out = {"event_ordinal": ordinal,
           "offset": _integer(inp.get("offset", 1), 1),
           "limit": _integer(inp.get("limit", 2000), 1),
           "truncated": _boolean(metadata.get("truncated")),
           "byte_cap": cap is not None,
           "cap_kb": int(cap[1]) if cap else None,
           "continuation_offset": int(continuation[1]) if continuation else None,
           "source_parity": "UNKNOWN"}
    for field in ("lineStart", "lineEnd", "totalLines"):
        out[field] = _integer(display.get(field))
    out["range_continuation"] = (out["truncated"] is True and not out["byte_cap"] and
                                  out["lineEnd"] is not None and out["totalLines"] is not None and
                                  out["lineEnd"] < out["totalLines"])
    return out


def audit_trace(root: Path) -> dict:
    """Analyze existing trace records without opening any recorded tool path."""
    root = Path(root)
    report = {"schema": SCHEMA, "requests": [], "tools": {
        "counts_by_name_status": {}, "repetition_groups": [], "reads": []},
        "termination": {}, "errors": []}
    errors = report["errors"]
    if not root.is_dir():
        errors.append({"record": "trace_root", "error": "not_a_directory"})
        return report
    actual = _load_json(root / "CLI-ACTUAL.json", errors, "cli_actual", optional=True)
    stop_records = [_load_json(root / name, errors, "owner_stop", optional=True)
                    for name in ("OWNER-STOP.json", "STOP-REQUEST.json")]
    owner_stop = any(item is not None for item in stop_records)
    try:
        dirs = [p for p in root.iterdir() if p.name.startswith("http-") and p.is_dir()]
    except OSError:
        errors.append({"record": "trace_root", "error": "unreadable"})
        dirs = []
    # Numeric ordinals first, then lexical suffixes. Never expose directory names.
    dirs.sort(key=lambda p: (0, int(p.name[5:])) if p.name[5:].isdigit() else (1, p.name))
    baseline = (None, None)
    finishes, interrupted, unknown = Counter(), 0, 0
    for ordinal, directory in enumerate(dirs, 1):
        if directory.is_symlink():
            errors.append({"record": ordinal, "error": "symlink_directory_ignored"})
            continue
        request = _load_json(directory / "REQUEST.json", errors, ordinal)
        summary = _load_json(directory / "SUMMARY.json", errors, ordinal)
        entry, hashes = _request_metadata(request or {}, ordinal, baseline)
        if ordinal == 1:
            baseline = hashes
            entry, _ = _request_metadata(request or {}, ordinal, baseline)
        entry.update(_summary_metadata(summary or {}))
        incomplete_error = (entry["error"] and entry["finish_reason"] is None and
                            entry["sse_done"] is not True)
        if summary is None or entry["ATTEMPT_END_utc"] is None:
            classification = "UNKNOWN"
            unknown += 1
        elif owner_stop and incomplete_error:
            classification = "owner_interrupted"
            interrupted += 1
        elif incomplete_error:
            classification = "transport_incomplete"
        elif entry["sse_done"] is not True:
            classification = "UNKNOWN"
            unknown += 1
        else:
            classification = entry["finish_reason"] or "UNKNOWN"
            unknown += classification == "UNKNOWN"
        entry["termination"] = classification
        if entry["finish_reason"] is not None:
            finishes[entry["finish_reason"]] += 1
        report["requests"].append(entry)
    groups, counts = {}, {}
    final_text = False
    events_complete = True
    event_path = root / "CLI-EVENTS.jsonl"
    try:
        if event_path.is_symlink():
            raise OSError
        with event_path.open(encoding="utf-8-sig") as stream:
            for ordinal, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line, parse_constant=_reject_constant)
                    if not isinstance(event, dict):
                        raise ValueError
                except (ValueError, RecursionError):
                    events_complete = False
                    errors.append({"record": "cli_event", "ordinal": ordinal, "error": "invalid_json_object"})
                    continue
                part = event.get("part")
                if not isinstance(part, dict):
                    if event.get("type") == "text":
                        events_complete = False
                        errors.append({"record": "cli_event", "ordinal": ordinal, "error": "invalid_text_part"})
                    continue
                if event.get("type") == "text":
                    text = part.get("text")
                    if not isinstance(text, str):
                        events_complete = False
                        errors.append({"record": "cli_event", "ordinal": ordinal, "error": "invalid_text_value"})
                    final_text |= isinstance(text, str) and bool(text.strip())
                if event.get("type") != "tool_use":
                    continue
                state = part.get("state")
                if not isinstance(state, dict):
                    errors.append({"record": "cli_event", "ordinal": ordinal, "error": "invalid_tool_state"})
                    continue
                tool, status = _enum(part.get("tool"), TOOLS), _enum(state.get("status"), STATUSES)
                counts.setdefault(tool, Counter())[status] += 1
                if tool == "read":
                    report["tools"]["reads"].append(_read_metadata(state, ordinal))
                output, inp = state.get("output"), state.get("input")
                if status != "completed" or not isinstance(output, str) or not isinstance(inp, dict):
                    continue
                args_sha = _sha256_json(inp)
                name_sha = (_sha256_json(part.get("tool")) if tool == "unknown" else "")
                group = groups.setdefault((tool, name_sha, args_sha), {"raw": Counter(), "grep": Counter(), "grep_unknown": 0})
                group["raw"][_sha256_str(output)] += 1
                if tool == "grep":
                    metadata = state.get("metadata")
                    truncated = isinstance(metadata, dict) and metadata.get("truncated") is True
                    parsed = None if truncated else _parse_grep_output(output)
                    if parsed is None:
                        group["grep_unknown"] += 1
                    else:
                        group["grep"][_normalize_grep_multiset(parsed)] += 1
    except (OSError, UnicodeError):
        events_complete = False
        errors.append({"record": "cli_events", "error": "missing_or_unreadable"})
    repetitions = report["tools"]["repetition_groups"]
    for (tool, name_sha, args_sha), group in sorted(groups.items()):
        count = sum(group["raw"].values())
        if count < 2:
            continue
        item = {"tool": tool, "args_sha": args_sha, "count": count,
                "raw_output_sha_variants": len(group["raw"]),
                "raw_output_sha_counts": dict(group["raw"]),
                "exact_same_result_subgroups": sum(n >= 2 for n in group["raw"].values())}
        if name_sha:
            item["tool_name_sha256"] = name_sha
        if tool == "grep":
            item["grep_normalized_sha_variants"] = len(group["grep"]) if not group["grep_unknown"] else None
            item["grep_normalized_sha_counts"] = dict(group["grep"])
            item["grep_normalization_unknown_results"] = group["grep_unknown"]
            item["ordering_only_variation"] = (not group["grep_unknown"] and
                                               len(group["grep"]) == 1 and len(group["raw"]) > 1)
        repetitions.append(item)
    report["tools"]["counts_by_name_status"] = {key: dict(value) for key, value in counts.items()}
    report["termination"] = {
        "total_requests": len(report["requests"]),
        "total_tool_invocations": sum(sum(value.values()) for value in counts.values()),
        "finish_counts": dict(finishes), "owner_stop_evidence": owner_stop,
        "owner_interrupted_attempts": interrupted, "unknown_attempts": unknown,
        "assistant_text_event_present": final_text,
        "event_stream_complete": events_complete,
        # This trace format has no response-ID link from CLI text to SUMMARY.
        # Intermediate assistant text cannot establish a final-answer event.
        "final_text_present": None if final_text or not events_complete else False,
        "final_text_association": ("UNKNOWN_INCOMPLETE_EVENTS" if not events_complete else
                                   "UNKNOWN_NO_RESPONSE_LINK" if final_text else "NO_TEXT_EVENTS"),
        "exit_code": (actual.get("exit_code") if actual and type(actual.get("exit_code")) is int else None),
    }
    if actual:
        for field in ("BEGIN_UTC", "END_UTC"):
            report["termination"][field] = _utc(actual.get(field))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_trace(args.trace_dir)
    except (OSError, ValueError, TypeError, RecursionError):
        report = {"schema": SCHEMA, "requests": [], "tools": {}, "termination": {},
                  "errors": [{"record": "audit", "error": "invalid_trace_structure"}]}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
