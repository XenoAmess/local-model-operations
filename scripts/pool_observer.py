#!/usr/bin/env python3
"""Read only explicitly named caller event logs; no caller import or actions.

Unpaired POSTs are evidence gaps, not a claim that a process/server is alive.
All counts become UNKNOWN when a supplied stream has incomplete/invalid evidence.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA = "local-model-operations.pool-observer/v1"
EVENTS = frozenset({"POST_BEGIN", "HEADERS", "FIRST_CONTENT", "FIRST_REASONING",
                    "ATTEMPT_END", "RETRY_BACKOFF", "RETRY_CANCELLED", "CANCELLED_BEFORE_POST"})
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
UTC = dt.timezone.utc


def _reject_constant(_value):
    raise ValueError("NONFINITE_JSON")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object)


def _stamp(value):
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise ValueError("TIMESTAMP_REQUIRES_TIMEZONE")
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _limit(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError("INVALID_LIMIT")


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _unknown(code, **extra):
    return {"schema": SCHEMA, "evidence_status": "UNKNOWN", "issues": [code],
            "unended_attempts": None, "observed_POSTs": 0, "observed_ENDs": 0,
            "intervals": [], "process_liveness": "UNKNOWN", "server_receipt": "UNKNOWN", **extra}


def observe_stream(path, *, max_bytes=1048576, max_events=5000):
    """Bounded raw read of one EVENTS.jsonl; never read REQUEST/SSE/CONTENT.

    Returned intervals use caller-recorded UTC. Invalid/partial evidence retains
    observed fragments but cannot establish current/peak totals. No path, task
    identity, free-text error or content fields are copied into the report.
    """
    _limit(max_bytes, 8 * 1048576)
    _limit(max_events, 50000)
    try:
        with Path(path).open("rb") as source:
            raw = source.read(max_bytes + 1)
    except OSError:
        return _unknown("EVENTS_UNREADABLE")
    observed_at = dt.datetime.now(UTC)
    common = {"observed_at_utc": _iso(observed_at), "bytes_read": len(raw),
              "source_sha256": hashlib.sha256(raw).hexdigest() if len(raw) <= max_bytes else None}
    if len(raw) > max_bytes:
        return _unknown("BYTE_LIMIT_EXCEEDED", **common)
    lines = raw.splitlines(keepends=True)
    if len(lines) > max_events:
        return _unknown("EVENT_LIMIT_EXCEEDED", **common)
    issues, attempts, counts, rows = [], {}, {}, []
    identity, previous_time = None, None
    previous_attempt = 0
    for line_number, line in enumerate(lines, 1):
        def issue(code):
            issues.append({"line": line_number, "code": code})
        if not line.endswith(b"\n"):
            issue("PARTIAL_FINAL_LINE")
            continue
        try:
            row = _json(line)
        except (ValueError, UnicodeError, RecursionError):
            issue("INVALID_EVENT_JSON")
            continue
        if not isinstance(row, dict) or not isinstance(row.get("event"), str) or row["event"] not in EVENTS:
            issue("UNRECOGNIZED_EVENT_SCHEMA")
            continue
        event, attempt = row["event"], row.get("attempt")
        if type(attempt) is not int or not 1 <= attempt <= 1000:
            issue("INVALID_ATTEMPT")
            continue
        if not isinstance(row.get("task_id"), str) or not row["task_id"]:
            issue("TASK_ID_MISSING")
            continue
        current_identity = tuple(row.get(key) for key in ("task_id", "machine_id", "owner"))
        if any(value is not None and not isinstance(value, str) for value in current_identity):
            issue("INVALID_STREAM_IDENTITY")
            continue
        if identity is None:
            identity = current_identity
        elif identity != current_identity:
            issue("CONFLICTING_STREAM_IDENTITY")
        try:
            when = _stamp(row.get("at_utc"))
        except ValueError:
            issue("INVALID_EVENT_TIMESTAMP")
            continue
        if previous_time is not None and when < previous_time:
            issue("OUT_OF_ORDER_TIMESTAMP")
        if when > observed_at:
            issue("FUTURE_EVENT_TIMESTAMP")
        previous_time = when
        counts[event] = counts.get(event, 0) + 1
        rows.append((event, attempt, when))
        state = attempts.setdefault(attempt, {"begin": None, "end": None, "seen": set()})
        if event in state["seen"]:
            issue("DUPLICATE_EVENT")
            continue
        state["seen"].add(event)
        if event == "POST_BEGIN":
            if attempt != previous_attempt + 1:
                issue("NONSEQUENTIAL_POST_ATTEMPT")
            if any(item["begin"] is not None and item["end"] is None
                   for number, item in attempts.items() if number != attempt):
                issue("OVERLAPPING_STREAM_ATTEMPTS")
            previous_attempt = attempt
            state["begin"] = when
            state["route"] = (row.get("network_routing") or {}).get("proxy_mode", "UNKNOWN") if isinstance(row.get("network_routing"), dict) else "UNKNOWN"
            if state["route"] not in ("direct", "environment"):
                state["route"] = "UNKNOWN"
        elif event in {"HEADERS", "FIRST_CONTENT", "FIRST_REASONING", "ATTEMPT_END"}:
            before_post_failure = event == "ATTEMPT_END" and state["begin"] is None and row.get("post_invoked") is False
            if (state["begin"] is None and not before_post_failure) or state["end"] is not None:
                issue("EVENT_OUTSIDE_OPEN_POST")
            if event == "HEADERS":
                if type(row.get("http_status")) is not int or not _number(row.get("http_headers_ms")):
                    issue("INVALID_HEADERS_MEASUREMENT")
                else:
                    state["http_status"] = row["http_status"]
                    state["http_headers_ms"] = row["http_headers_ms"]
            elif event == "FIRST_CONTENT":
                if "HEADERS" not in state["seen"] or not _number(row.get("first_nonempty_content_delta_ms")):
                    issue("INVALID_FIRST_CONTENT_MEASUREMENT")
                else:
                    state["first_nonempty_content_delta_ms"] = row["first_nonempty_content_delta_ms"]
            elif event == "ATTEMPT_END":
                state["end"] = when
                if state["begin"] is not None and when < state["begin"]:
                    issue("END_PRECEDES_POST")
                if row.get("post_invoked") is False and state["begin"] is not None:
                    issue("END_REPORTS_NO_POST")
                state["finish_reason"] = row.get("finish_reason") if row.get("finish_reason") in ("stop", "length") else "OTHER_OR_UNKNOWN"
                state["sse_done"] = row.get("sse_done") if type(row.get("sse_done")) is bool else None
                state["reported_candidate_complete"] = row.get("candidate_complete") if type(row.get("candidate_complete")) is bool else None
                state["reported_total_ms"] = row.get("total_ms") if _number(row.get("total_ms")) else None
                syntax = row.get("json_syntax")
                state["json_syntax"] = syntax.get("status", "UNKNOWN") if isinstance(syntax, dict) else "UNKNOWN"
                if state["json_syntax"] not in ("VALID", "INVALID", "UNKNOWN"):
                    state["json_syntax"] = "UNKNOWN"
        elif event in {"RETRY_BACKOFF", "RETRY_CANCELLED"}:
            if state["end"] is None:
                issue("RETRY_EVENT_WITHOUT_END")
            if event == "RETRY_BACKOFF" and not _number(row.get("delay_seconds")):
                issue("INVALID_BACKOFF_DURATION")
        elif state["begin"] is not None:
            issue("CANCEL_BEFORE_POST_CONFLICT")
    intervals = []
    for number, state in sorted(attempts.items()):
        if state["begin"] is None:
            continue
        intervals.append({"attempt": number, "begin_utc": _iso(state["begin"]),
                          "end_utc": _iso(state["end"]) if state["end"] else None,
                          "headers_observed": "HEADERS" in state["seen"],
                          "valid_content_delta_observed": "FIRST_CONTENT" in state["seen"],
                          "network_proxy_mode": state.get("route", "UNKNOWN"),
                          **{key: state.get(key) for key in ("http_status", "http_headers_ms", "first_nonempty_content_delta_ms", "reported_total_ms", "finish_reason", "sse_done", "reported_candidate_complete", "json_syntax")}})
    if not lines:
        issues.append({"code": "NO_EVENTS"})
    last_event = rows[-1][0] if rows else None
    return {"schema": SCHEMA, "evidence_status": "KNOWN" if not issues else "UNKNOWN",
            **common, "issues": issues, "events_observed": len(rows), "event_counts": counts,
            "observed_POSTs": counts.get("POST_BEGIN", 0), "observed_ENDs": counts.get("ATTEMPT_END", 0),
            "observed_paired_POST_ENDs": sum(item["end_utc"] is not None for item in intervals),
            "unended_attempts": sum(item["end_utc"] is None for item in intervals) if not issues else None,
            "last_state": ("BACKOFF" if last_event == "RETRY_BACKOFF" else
                           "STOPPED_BEFORE_NEXT_POST" if last_event in {"RETRY_CANCELLED", "CANCELLED_BEFORE_POST"} else
                           "UNPAIRED_POST" if intervals and intervals[-1]["end_utc"] is None else
                           "PAIRED_END" if last_event == "ATTEMPT_END" else "UNKNOWN") if not issues else "UNKNOWN",
            "intervals": intervals, "process_liveness": "UNKNOWN", "server_receipt": "UNKNOWN",
            "semantic_review": "OWNER_REVIEW_REQUIRED"}


def observe_registry(records, *, max_streams=256):
    """Observe a bounded explicit list of {id, events_path}, no discovery.

    Global intervals end at the earliest read observation to avoid comparing
    different current cutoffs. Reads are not atomic and caller clocks are not
    independently synchronized. A missing/ambiguous stream makes totals UNKNOWN.
    """
    _limit(max_streams, 256)
    if not isinstance(records, list) or not 1 <= len(records) <= max_streams:
        raise ValueError("INVALID_REGISTRY_SIZE")
    ids, paths, reports = set(), set(), []
    for record in records:
        if not isinstance(record, dict) or set(record) != {"id", "events_path"}:
            raise ValueError("INVALID_REGISTRY_RECORD")
        if not isinstance(record["id"], str) or not record["id"] or len(record["id"]) > 256:
            raise ValueError("INVALID_REGISTRY_ID")
        if not isinstance(record["events_path"], str) or not record["events_path"]:
            raise ValueError("INVALID_REGISTRY_PATH")
        path = Path(record["events_path"]).resolve()
        if record["id"] in ids or path in paths:
            raise ValueError("DUPLICATE_REGISTERED_STREAM")
        ids.add(record["id"])
        paths.add(path)
        reports.append(observe_stream(path))
    known = all(report["evidence_status"] == "KNOWN" for report in reports)
    result = {"schema": SCHEMA, "registered_streams": len(reports), "streams": reports,
              "evidence_status": "KNOWN" if known else "UNKNOWN", "snapshot_atomic": False,
              "client_clock_synchronization": "NOT_VERIFIED", "unended_at_cutoff": None,
              "peak_registered_POST_intervals": None, "peak_seconds": None, "observed_union_seconds": None,
              "process_liveness": "UNKNOWN", "server_receipt": "UNKNOWN",
              "semantic_review": "OWNER_REVIEW_REQUIRED"}
    if not known:
        return result
    cutoff = min(_stamp(report["observed_at_utc"]) for report in reports)
    edges, current = {}, 0
    for report in reports:
        for interval in report["intervals"]:
            begin = _stamp(interval["begin_utc"])
            end = _stamp(interval["end_utc"]) if interval["end_utc"] else None
            if begin > cutoff:
                continue
            if end is None or end > cutoff:
                current += 1
            stop = min(end, cutoff) if end else cutoff
            if stop > begin:
                edges[begin] = edges.get(begin, 0) + 1
                edges[stop] = edges.get(stop, 0) - 1
    active, peak, peak_seconds, union = 0, 0, 0.0, 0.0
    ordered = sorted(edges)
    for index, when in enumerate(ordered[:-1]):
        active += edges[when]
        seconds = (ordered[index + 1] - when).total_seconds()
        if active > 0:
            union += seconds
        if active > peak:
            peak, peak_seconds = active, seconds
        elif active == peak and active > 0:
            peak_seconds += seconds
    result.update({"cutoff_utc": _iso(cutoff), "unended_at_cutoff": current,
                   "peak_registered_POST_intervals": peak, "peak_seconds": peak_seconds,
                   "observed_union_seconds": union})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", help="Explicit JSON list of id/events_path records; <=64 KiB")
    args = parser.parse_args(argv)
    with Path(args.registry).open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("REGISTRY_BYTE_LIMIT")
    report = observe_registry(_json(raw))
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report["evidence_status"] == "KNOWN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
