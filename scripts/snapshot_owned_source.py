"""Explicit owned-source snapshot CLI v2: named READY generations plus named INTAKE tickets/receipts.

Read-only metadata observation via the supplied unchanged pool_observer.observe_registry.
Not global source/Runtime/cloud/backend liveness, not adoption, not dispatch, not a rerun
of the old frozen SQLite request-registry CLI. No writes, retries, sleeps, subprocesses,
DB/network/CONTENT/source-body access, directory discovery, or execution of supplied paths.
"""

import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import pool_observer

INPUT_SCHEMA = "owned-source-snapshot-input/v2"
REPORT_SCHEMA = "owned-source-snapshot-report/v2"
SCOPE = "EXPLICIT_READY_AND_TICKETS_ONLY_NOT_GLOBAL"
UTC = dt.timezone.utc

MANIFEST_MAX_BYTES = 1048576
READY_MAX_BYTES = 65536
READY_MAX_ROWS = 256
MAX_READY_FILES = 16
MAX_REGISTERED_IDS = 1024
MAX_TICKETS = 1024
TICKET_MAX_BYTES = 65536
REPORT_MAX_BYTES = 2097152
MAX_PATH_CHARS = 4096
MAX_ID_BYTES = 512
MAX_FIELD_LEN = 4096
MAX_STAGE_LEN = 256

READY_KEYS = frozenset({"id", "owner", "spec_path", "task_id", "output_path",
                        "config_path", "machine_id", "lane"})
LANES = ("source", "runtime")
IDENTITY_KEYS = ("id", "owner", "task_id", "machine_id")
PATH_KEYS = ("spec_path", "config_path", "output_path")


class FatalError(Exception):
    """Fatal manifest/READY input, schema, bounds, or identity error."""


def _fatal(code):
    raise FatalError(code)


def _strict_json(raw):
    def reject_constant(_value):
        _fatal("NONFINITE_JSON")
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            _fatal("NONFINITE_JSON")
        return result
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fatal("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw, parse_constant=reject_constant, parse_float=finite_float,
                          object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        _fatal("INVALID_JSON")


def _is_absolute_local_path(value):
    return (isinstance(value, str) and bool(value) and len(value) <= MAX_PATH_CHARS
            and "\0" not in value and not value.startswith(("\\\\", "//"))
            and os.path.isabs(value))


def _normalized_path(value):
    return os.path.normcase(os.path.realpath(value))


def _identity_string(value):
    if not isinstance(value, str) or not value.strip() or value.startswith("-") or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_ID_BYTES
    except UnicodeError:
        return False


def _ticket_identity_string(value):
    if not isinstance(value, str) or not value or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_ID_BYTES
    except UnicodeError:
        return False


def _bounded_string(value, maximum):
    if not isinstance(value, str) or not 0 < len(value) <= maximum or "\0" in value:
        return False
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _validate_manifest(manifest):
    if not isinstance(manifest, dict):
        _fatal("MANIFEST_REQUIRES_OBJECT")
    if set(manifest) != {"schema", "ready_files", "current_ready", "tickets"}:
        _fatal("MANIFEST_REQUIRES_EXACT_KEYS")
    if manifest["schema"] != INPUT_SCHEMA:
        _fatal("UNSUPPORTED_INPUT_SCHEMA")
    try:
        encoded = json.dumps(manifest, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fatal("INVALID_MANIFEST_JSON")
    if len(encoded) > MANIFEST_MAX_BYTES:
        _fatal("MANIFEST_BYTE_LIMIT")
    ready_files = manifest["ready_files"]
    if not isinstance(ready_files, list) or not 1 <= len(ready_files) <= MAX_READY_FILES:
        _fatal("INVALID_READY_FILE_LIST")
    normalized = []
    seen = set()
    for entry in ready_files:
        if not _is_absolute_local_path(entry):
            _fatal("INVALID_READY_PATH")
        key = _normalized_path(entry)
        if key in seen:
            _fatal("DUPLICATE_READY_PATH")
        seen.add(key)
        normalized.append(entry)
    current_ready = manifest["current_ready"]
    if not isinstance(current_ready, str) or current_ready not in normalized:
        _fatal("CURRENT_READY_NOT_IN_LIST")
    tickets = manifest["tickets"]
    if not isinstance(tickets, list) or len(tickets) > MAX_TICKETS:
        _fatal("INVALID_TICKET_LIST")
    validated_tickets = []
    metadata_seen = set()
    receipt_seen = set()
    for ticket in tickets:
        if not isinstance(ticket, dict) or set(ticket) != {"metadata_path", "receipt_path"}:
            _fatal("TICKET_REQUIRES_EXACT_KEYS")
        metadata_path = ticket["metadata_path"]
        receipt_path = ticket["receipt_path"]
        if not _is_absolute_local_path(metadata_path) or not _is_absolute_local_path(receipt_path):
            _fatal("INVALID_TICKET_PATH")
        metadata_key = _normalized_path(metadata_path)
        receipt_key = _normalized_path(receipt_path)
        if metadata_key in metadata_seen:
            _fatal("DUPLICATE_METADATA_PATH")
        if receipt_key in receipt_seen:
            _fatal("DUPLICATE_RECEIPT_PATH")
        metadata_seen.add(metadata_key)
        receipt_seen.add(receipt_key)
        validated_tickets.append((metadata_path, receipt_path))
    return normalized, current_ready, validated_tickets


def _load_ready_files(normalized, current_ready):
    """Bounded strict reads of explicitly named READY files; never open spec/config/output bodies."""
    per_file = {}
    for path in normalized:
        try:
            with Path(path).open("rb") as source:
                raw = source.read(READY_MAX_BYTES + 1)
        except OSError:
            _fatal("READY_UNREADABLE")
        if len(raw) > READY_MAX_BYTES:
            _fatal("READY_BYTE_LIMIT")
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            _fatal("READY_INVALID_UTF8")
        rows = _strict_json(text)
        if not isinstance(rows, list) or not 0 <= len(rows) <= READY_MAX_ROWS:
            _fatal("READY_INVALID_ROWS")
        per_file[path] = (raw, rows)
    return per_file


def _canonical_ready_row(row):
    if not isinstance(row, dict) or set(row) != READY_KEYS:
        _fatal("READY_RECORD_REQUIRES_EXACT_8_KEYS")
    clean = {}
    for key in READY_KEYS:
        value = row[key]
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_FIELD_LEN:
            _fatal("READY_INVALID_RECORD_FIELD")
        clean[key] = value
    if clean["lane"] not in LANES:
        _fatal("READY_INVALID_RECORD_LANE")
    for key in IDENTITY_KEYS:
        if not _identity_string(clean[key]):
            _fatal("READY_INVALID_RECORD_IDENTITY")
    for key in PATH_KEYS:
        if not _is_absolute_local_path(clean[key]):
            _fatal("READY_PATHS_REQUIRE_ABSOLUTE")
    return clean


def _deduplicate_ready(per_file, current_ready):
    unique, by_id = [], {}
    task_ids, outputs = set(), set()
    current_ids = {_canonical_ready_row(row)["id"] for row in per_file[current_ready][1]}
    for path in per_file:
        local_ids, local_tasks, local_outputs = set(), set(), set()
        for row in per_file[path][1]:
            clean = _canonical_ready_row(row)
            norm_output = _normalized_path(clean["output_path"])
            if (clean["id"] in local_ids or clean["task_id"] in local_tasks
                    or norm_output in local_outputs):
                _fatal("DUPLICATE_TASK_OR_OUTPUT_WITHIN_READY")
            local_ids.add(clean["id"])
            local_tasks.add(clean["task_id"])
            local_outputs.add(norm_output)
            prior = by_id.get(clean["id"])
            if prior is not None:
                if prior != clean:
                    _fatal("CROSS_GENERATION_IDENTITY_CONFLICT")
                continue
            if clean["task_id"] in task_ids or norm_output in outputs:
                _fatal("DUPLICATE_TASK_OR_OUTPUT_ACROSS_READY")
            by_id[clean["id"]] = clean
            task_ids.add(clean["task_id"])
            outputs.add(norm_output)
            unique.append((clean, clean["id"] in current_ids))
    if len(unique) > MAX_REGISTERED_IDS:
        _fatal("READY_REGISTERED_ID_LIMIT")
    return unique


def _observe_batched_registry(records):
    """Owner v2 extension. Keep the unchanged observer's 256-stream call bound."""
    batches = [pool_observer.observe_registry(records[offset:offset + 256], max_streams=256)
               for offset in range(0, len(records), 256)]
    streams = [stream for batch in batches for stream in batch["streams"]]
    known = all(batch["evidence_status"] == "KNOWN" for batch in batches)
    result = {
        "schema": pool_observer.SCHEMA, "registered_streams": len(streams), "streams": streams,
        "evidence_status": "KNOWN" if known else "UNKNOWN", "snapshot_atomic": False,
        "client_clock_synchronization": "NOT_VERIFIED", "unended_at_cutoff": None,
        "peak_registered_POST_intervals": None, "peak_seconds": None,
        "observed_union_seconds": None, "process_liveness": "UNKNOWN",
        "server_receipt": "UNKNOWN", "semantic_review": "OWNER_REVIEW_REQUIRED",
        "observer_batches": len(batches), "observer_batch_max_streams": 256,
        "maximum_registered_streams": MAX_REGISTERED_IDS,
        "whole_registry_cutoff_not_max_of_batch_peaks": True}
    if not known:
        return result
    def stamp(value):
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    # Same interval sweep as the supplied observer lines244-271, on ALL streams.
    # Earliest observation across all batches is one common half-open cutoff.
    cutoff = min(stamp(stream["observed_at_utc"]) for stream in streams)
    edges, current = {}, 0
    for stream in streams:
        for interval in stream["intervals"]:
            begin = stamp(interval["begin_utc"])
            end = stamp(interval["end_utc"]) if interval["end_utc"] else None
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
    result.update(cutoff_utc=_iso(cutoff), unended_at_cutoff=current,
                  peak_registered_POST_intervals=peak, peak_seconds=peak_seconds,
                  observed_union_seconds=union)
    return result


def _observe_http(unique):
    """Reuse the unchanged observer in finite batches; owner v2 merges all intervals."""
    if not unique:
        return {
            "schema": pool_observer.SCHEMA,
            "registered_streams": 0,
            "streams": [],
            "evidence_status": "KNOWN",
            "snapshot_atomic": False,
            "client_clock_synchronization": "NOT_VERIFIED",
            "observed_POSTs": 0,
            "observed_ENDs": 0,
            "actual_unpaired_POST_attempts": 0,
            "peak_registered_POST_intervals": 0,
            "peak_seconds": 0.0,
            "observed_union_seconds": 0.0,
            "unended_at_cutoff": 0,
            "no_streams": True,
            "observer_batches": 0,
            "observer_batch_max_streams": 256,
            "maximum_registered_streams": MAX_REGISTERED_IDS,
            "whole_registry_cutoff_not_max_of_batch_peaks": True,
            "registered_no_observed_POST": 0,
            "current_generation_no_observed_POST": 0,
            "registered_total": 0,
            "no_observed_POST_does_not_prove_no_actual_POST": True,
            "process_liveness": "UNKNOWN",
            "server_receipt": "UNKNOWN",
            "semantic_review": "OWNER_REVIEW_REQUIRED",
        }
    records = []
    for clean, _in_current in unique:
        events_path = os.path.join(clean["output_path"], "EVENTS.jsonl")
        records.append({"id": clean["id"], "events_path": events_path})
    observer = _observe_batched_registry(records)
    streams = observer["streams"]
    observed_posts = 0
    observed_ends = 0
    registered_no_observed_POST = 0
    current_no_observed_POST = 0
    for index, (clean, in_current) in enumerate(unique):
        stream = streams[index]
        posts = stream.get("observed_POSTs", 0)
        ends = stream.get("observed_ENDs", 0)
        observed_posts += posts
        observed_ends += ends
        if posts == 0:
            registered_no_observed_POST += 1
            if in_current:
                current_no_observed_POST += 1
    observer["observed_POSTs"] = observed_posts
    observer["observed_ENDs"] = observed_ends
    observer["actual_unpaired_POST_attempts"] = observer.get("unended_at_cutoff")
    observer["registered_no_observed_POST"] = registered_no_observed_POST
    observer["current_generation_no_observed_POST"] = current_no_observed_POST
    observer["registered_total"] = len(unique)
    observer["no_observed_POST_does_not_prove_no_actual_POST"] = True
    return observer


def _read_metadata(metadata_path):
    """Bounded strict read; only id/task_id inspected. Never aborts the READY snapshot."""
    entry = {"metadata_status": "VALID", "id": None, "task_id": None,
             "sha256": None, "bytes": None, "diagnostics": []}
    try:
        with Path(metadata_path).open("rb") as source:
            raw = source.read(TICKET_MAX_BYTES + 1)
    except OSError:
        entry["metadata_status"] = "UNREADABLE"
        entry["diagnostics"].append("METADATA_UNREADABLE")
        return entry
    if len(raw) > TICKET_MAX_BYTES:
        entry["metadata_status"] = "INVALID"
        entry["diagnostics"].append("METADATA_BYTE_LIMIT")
        return entry
    try:
        document = _strict_json(raw.decode("utf-8"))
    except FatalError as failure:
        entry["metadata_status"] = "INVALID"
        entry["diagnostics"].append("METADATA_" + str(failure))
        return entry
    except UnicodeError:
        entry["metadata_status"] = "INVALID"
        entry["diagnostics"].append("METADATA_INVALID_UTF8")
        return entry
    if not isinstance(document, dict):
        entry["metadata_status"] = "INVALID"
        entry["diagnostics"].append("METADATA_REQUIRES_OBJECT")
        return entry
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    entry["bytes"] = len(raw)
    raw_id = document.get("id")
    raw_task = document.get("task_id")
    id_ok = _ticket_identity_string(raw_id)
    task_ok = _ticket_identity_string(raw_task)
    if not id_ok or not task_ok:
        entry["metadata_status"] = "INVALID"
        entry["diagnostics"].append("TICKET_IDENTITY_INVALID")
        return entry
    entry["id"] = raw_id if id_ok else None
    entry["task_id"] = raw_task if task_ok else None
    return entry


def _read_receipt(receipt_path):
    """Independent bounded strict read of the explicitly supplied receipt."""
    receipt = {"receipt_status": "KNOWN", "stage": None, "sha256": None,
               "bytes": None, "diagnostics": []}
    try:
        with Path(receipt_path).open("rb") as source:
            raw = source.read(TICKET_MAX_BYTES + 1)
    except FileNotFoundError:
        receipt["receipt_status"] = "ABSENT"
        receipt["diagnostics"].append("RECEIPT_ABSENT")
        return receipt
    except OSError:
        receipt["receipt_status"] = "UNREADABLE"
        receipt["diagnostics"].append("RECEIPT_UNREADABLE")
        return receipt
    if len(raw) > TICKET_MAX_BYTES:
        receipt["receipt_status"] = "INVALID"
        receipt["diagnostics"].append("RECEIPT_BYTE_LIMIT")
        return receipt
    try:
        document = _strict_json(raw.decode("utf-8"))
    except FatalError as failure:
        receipt["receipt_status"] = "INVALID"
        receipt["diagnostics"].append("RECEIPT_" + str(failure))
        return receipt
    except UnicodeError:
        receipt["receipt_status"] = "INVALID"
        receipt["diagnostics"].append("RECEIPT_INVALID_UTF8")
        return receipt
    if not isinstance(document, dict):
        receipt["receipt_status"] = "INVALID"
        receipt["diagnostics"].append("RECEIPT_REQUIRES_OBJECT")
        return receipt
    stage = document.get("stage")
    if not _bounded_string(stage, MAX_STAGE_LEN):
        receipt["receipt_status"] = "INVALID"
        receipt["diagnostics"].append("RECEIPT_STAGE_INVALID")
        return receipt
    receipt["stage"] = stage
    receipt["sha256"] = hashlib.sha256(raw).hexdigest()
    receipt["bytes"] = len(raw)
    return receipt


def _link_tickets(validated_tickets, by_id):
    """Exact id AND task_id linkage against deduplicated READY; revisions share one logical identity."""
    entries = []
    groups = {}
    for index, (metadata_path, receipt_path) in enumerate(validated_tickets):
        metadata = _read_metadata(metadata_path)
        receipt = _read_receipt(receipt_path)
        valid = (metadata["metadata_status"] == "VALID"
                 and metadata["id"] is not None and metadata["task_id"] is not None)
        registered = False
        if valid:
            row = by_id.get(metadata["id"])
            if row is not None:
                if row["task_id"] == metadata["task_id"]:
                    registered = True
                else:
                    metadata["diagnostics"].append("IDENTITY_CONFLICT")
        group_key = (metadata["id"], metadata["task_id"]) if valid else None
        if group_key is not None:
            groups.setdefault(group_key, []).append(index)
        entries.append({"index": index, "metadata": metadata, "receipt": receipt,
                        "valid": valid, "registered": registered, "group": group_key})
    tasks_by_id = {}
    for group_key in groups:
        tasks_by_id.setdefault(group_key[0], set()).add(group_key[1])
    for entry in entries:
        if (entry["valid"] and len(tasks_by_id[entry["metadata"]["id"]]) > 1
                and "IDENTITY_CONFLICT" not in entry["metadata"]["diagnostics"]):
            entry["metadata"]["diagnostics"].append("IDENTITY_CONFLICT")
    logical_ids = set()
    unregistered_ids = set()
    unregistered_stage_counts = {}
    for group_key, indexes in groups.items():
        logical_ids.add(group_key)
        if not any(entries[index]["registered"] for index in indexes):
            unregistered_ids.add(group_key)
        for index in indexes:
            entry = entries[index]
            if not entry["registered"]:
                receipt = entry["receipt"]
                stage = (receipt["stage"] if receipt["receipt_status"] == "KNOWN"
                         else receipt["receipt_status"])
                unregistered_stage_counts[stage] = unregistered_stage_counts.get(stage, 0) + 1
    return entries, logical_ids, unregistered_ids, unregistered_stage_counts


def build_snapshot(manifest):
    """Return the complete finite report mapping for a strict manifest; fatal on manifest/READY errors."""
    read_started_at = dt.datetime.now(UTC)
    if not isinstance(manifest, dict):
        _fatal("MANIFEST_REQUIRES_OBJECT")
    if set(manifest) != {"schema", "ready_files", "current_ready", "tickets"}:
        _fatal("MANIFEST_REQUIRES_EXACT_KEYS")
    if manifest["schema"] != INPUT_SCHEMA:
        _fatal("UNSUPPORTED_INPUT_SCHEMA")
    normalized, current_ready, validated_tickets = _validate_manifest(manifest)
    per_file = _load_ready_files(normalized, current_ready)
    unique = _deduplicate_ready(per_file, current_ready)
    by_id = {clean["id"]: clean for clean, _in_current in unique}
    current_ready_records = len(per_file[current_ready][1])
    largest_observed_READY_bytes = max(len(raw) for raw, _rows in per_file.values())
    http = _observe_http(unique)
    entries, logical_ids, unregistered_ids, unregistered_stage_counts = _link_tickets(validated_tickets, by_id)
    tickets_with_known_receipt = 0
    tickets_awaiting_receipt = 0
    preparation_rejected_receipts = 0
    invalid_or_unreadable_metadata_tickets = 0
    invalid_or_unreadable_receipts = 0
    ticket_rows = []
    for entry in entries:
        metadata = entry["metadata"]
        receipt = entry["receipt"]
        if metadata["metadata_status"] != "VALID":
            invalid_or_unreadable_metadata_tickets += 1
        if receipt["receipt_status"] == "KNOWN":
            tickets_with_known_receipt += 1
            if receipt["stage"] == "PREPARATION_FAILED_NO_AUTO_RETRY":
                preparation_rejected_receipts += 1
        elif receipt["receipt_status"] == "ABSENT":
            tickets_awaiting_receipt += 1
        else:
            invalid_or_unreadable_receipts += 1
        ticket_rows.append({
            "index": entry["index"],
            "metadata_status": metadata["metadata_status"],
            "id": metadata["id"],
            "task_id": metadata["task_id"],
            "registered": entry["registered"],
            "receipt_status": receipt["receipt_status"],
            "receipt_stage": receipt["stage"],
            "metadata_sha256": metadata["sha256"],
            "metadata_bytes": metadata["bytes"],
            "receipt_sha256": receipt["sha256"],
            "receipt_bytes": receipt["bytes"],
            "diagnostics": list(metadata["diagnostics"]) + list(receipt["diagnostics"]),
        })
    registered_valid_logical_ids = len(logical_ids) - len(unregistered_ids)
    read_finished_at = dt.datetime.now(UTC)
    report = {
        "schema": REPORT_SCHEMA,
        "scope": SCOPE,
        "read_started_at_utc": _iso(read_started_at),
        "read_finished_at_utc": _iso(read_finished_at),
        "snapshot_atomic": False,
        "evidence_status": http["evidence_status"],
        "global_source_Runtime_cloud_backend": "UNKNOWN_OR_SEPARATE",
        "process_liveness": "UNKNOWN",
        "server_receipt": "UNKNOWN",
        "actual_socket_or_backend_queue": "UNKNOWN",
        "metadata_or_receipt_is_POST_credit": False,
        "candidate_CONTENT_or_DB_access": False,
        "ready": {
            "ready_files": len(normalized),
            "current_READY_records": current_ready_records,
            "registered_distinct_records": len(unique),
            "current_READY_bytes": len(per_file[current_ready][0]),
            "maximum_READY_bytes": READY_MAX_BYTES,
            "largest_observed_READY_bytes": largest_observed_READY_bytes,
            "sources": [{"index": index, "bytes": len(per_file[path][0]),
                         "sha256": hashlib.sha256(per_file[path][0]).hexdigest(),
                         "current": path == current_ready}
                        for index, path in enumerate(normalized)],
        },
        "http": http,
        "intake": {
            "seen_intake_tickets": len(entries),
            "distinct_valid_logical_ids": len(logical_ids),
            "tickets_with_known_receipt": tickets_with_known_receipt,
            "tickets_awaiting_receipt": tickets_awaiting_receipt,
            "preparation_rejected_receipts": preparation_rejected_receipts,
            "invalid_or_unreadable_metadata_tickets": invalid_or_unreadable_metadata_tickets,
            "invalid_or_unreadable_receipts": invalid_or_unreadable_receipts,
            "registered_valid_logical_ids": registered_valid_logical_ids,
            "unregistered_valid_logical_ids": len(unregistered_ids),
            "unregistered_stage_counts": unregistered_stage_counts,
        },
        "tickets": ticket_rows,
    }
    if len(json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")) > REPORT_MAX_BYTES:
        _fatal("REPORT_BYTE_LIMIT")
    return report


def _emit_fatal(code):
    sys.stderr.write(json.dumps({"schema": REPORT_SCHEMA, "error": code},
                                ensure_ascii=False, allow_nan=False) + "\n")
    return 2


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 1:
        return _emit_fatal("USAGE_REQUIRES_ONE_ABSOLUTE_MANIFEST_JSON")
    path = argv[0]
    if not isinstance(path, str) or not _is_absolute_local_path(path):
        return _emit_fatal("MANIFEST_PATH_REQUIRES_ABSOLUTE_LOCAL")
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MANIFEST_MAX_BYTES + 1)
    except OSError:
        return _emit_fatal("MANIFEST_UNREADABLE")
    if len(raw) > MANIFEST_MAX_BYTES:
        return _emit_fatal("MANIFEST_BYTE_LIMIT")
    try:
        manifest = _strict_json(raw.decode("utf-8"))
    except FatalError as failure:
        return _emit_fatal(str(failure) or "INVALID_JSON")
    except UnicodeError:
        return _emit_fatal("MANIFEST_INVALID_UTF8")
    try:
        report = build_snapshot(manifest)
    except FatalError as failure:
        return _emit_fatal(str(failure) or "FATAL_INPUT_ERROR")
    except (ValueError, OSError, TypeError, RecursionError, UnicodeError):
        return _emit_fatal("FATAL_INPUT_ERROR")
    line = (json.dumps(report, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(line) > REPORT_MAX_BYTES:
        return _emit_fatal("REPORT_BYTE_LIMIT")
    sys.stdout.buffer.write(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
