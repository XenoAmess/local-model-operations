"""Bounded DATA normalization of collaboration roster views. No I/O beyond CLI, no authority/liveness verification."""
import hashlib
import json
import sys

from dispatch_validation import (MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, PlanError, agent_id, decode, d_path, fail, identifier, text, utc)


def _validate_tool(tool_obj):
    exact_keys = {"agents"}
    if set(tool_obj) != exact_keys:
        fail("INVALID_FIELDS")
    agents = tool_obj["agents"]
    if type(agents) is not list or not 1 <= len(agents) <= 65:
        fail("INVALID_COLLECTION")
    return agents


def _validate_capture(capture_obj):
    required = {"schema", "snapshot_id", "observed_at_utc", "returned_view_complete", "path_prefix", "capture_kind", "evidence", "error_classifications"}
    if set(capture_obj) != required:
        fail("INVALID_FIELDS")
    if capture_obj["schema"] != "xar.collaboration-roster-capture/v1":
        fail("INVALID_SCHEMA")
    identifier(capture_obj["snapshot_id"])
    utc(capture_obj["observed_at_utc"])
    if capture_obj["returned_view_complete"] is not True:
        fail("INCOMPLETE_VIEW")
    prefix = capture_obj["path_prefix"]
    if prefix is not None:
        agent_id(prefix)
    if capture_obj["capture_kind"] != "STRUCTURED_VALUE_SERIALIZATION":
        fail("INVALID_CAPTURE_KIND")
    text(capture_obj["evidence"], 2048)
    classifications = capture_obj["error_classifications"]
    if type(classifications) is not list or len(classifications) > 65:
        fail("INVALID_COLLECTION")
    return classifications


def _normalize_status(agent_status):
    if type(agent_status) is str:
        if agent_status == "running":
            return "RUNNING", None, None
        fail("UNKNOWN_TOOL_STATUS")
    if type(agent_status) is dict:
        keys = set(agent_status)
        if keys == {"completed"}:
            val = agent_status["completed"]
            if type(val) is not str:
                fail("UNKNOWN_TOOL_STATUS")
            return "COMPLETED", None, None
        if keys == {"errored"}:
            val = agent_status["errored"]
            if type(val) is not str or not val.strip() or len(val.encode("utf-8")) > 8192:
                fail("UNKNOWN_TOOL_STATUS")
            return "ERROR", val, None
        fail("UNKNOWN_TOOL_STATUS")
    fail("UNKNOWN_TOOL_STATUS")


def normalize_roster(tool_bytes, capture_bytes):
    if type(tool_bytes) is not bytes or len(tool_bytes) > MAX_INPUT_BYTES:
        fail("INVALID_INPUT_BYTES")
    if type(capture_bytes) is not bytes or len(capture_bytes) > MAX_INPUT_BYTES:
        fail("INVALID_INPUT_BYTES")

    tool_obj = decode(tool_bytes)
    capture_obj = decode(capture_bytes)

    tool_agents = _validate_tool(tool_obj)
    classifications = _validate_capture(capture_obj)

    # Validate classifications structure
    class_map = {}
    for row in classifications:
        if type(row) is not dict or set(row) != {"agent_id", "confirmed_kinds", "evidence"}:
            fail("INVALID_CLASSIFICATION")
        aid = row["agent_id"]
        agent_id(aid)
        kinds = row["confirmed_kinds"]
        if type(kinds) is not list or not 1 <= len(kinds) <= 3:
            fail("INVALID_CLASSIFICATION")
        for k in kinds:
            if k not in ("GUARD", "CAPACITY", "UNKNOWN"):
                fail("INVALID_CLASSIFICATION")
        if len(set(kinds)) != len(kinds):
            fail("INVALID_CLASSIFICATION")
        ev = row["evidence"]
        if type(ev) is not str or not ev.strip() or len(ev.encode("utf-8")) > 2048:
            fail("INVALID_CLASSIFICATION")
        if aid in class_map:
            fail("INVALID_CLASSIFICATION")
        class_map[aid] = {"confirmed_kinds": kinds, "evidence": ev}

    # Process agents
    normalized_agents = []
    seen_names = set()
    errored_agent_ids = set()
    root_running = 0
    root_status = None

    for agent in tool_agents:
        if type(agent) is not dict or set(agent) != {"agent_name", "agent_status"}:
            fail("INVALID_FIELDS")
        name = agent["agent_name"]
        agent_id(name)
        if name in seen_names:
            fail("DUPLICATE_AGENT")
        seen_names.add(name)

        status, raw_error, _ = _normalize_status(agent["agent_status"])
        if name == "/root":
            root_status = status
            root_running = 1 if status == "RUNNING" else 0

        if status == "ERROR":
            if name not in class_map:
                fail("UNCLASSIFIED_ERROR")
            errored_agent_ids.add(name)
            cls = class_map[name]
            error_obj = {
                "confirmed_kinds": cls["confirmed_kinds"],
                "raw": raw_error,
                "evidence": cls["evidence"]
            }
            normalized_agents.append({
                "agent_id": name,
                "status": "ERROR",
                "error": error_obj,
                "same_task": None
            })
        else:
            if name in class_map:
                fail("INVALID_CLASSIFICATION")
            normalized_agents.append({
                "agent_id": name,
                "status": status,
                "error": None,
                "same_task": None
            })

    # Check for unused classifications
    for aid in class_map:
        if aid not in errored_agent_ids:
            fail("INVALID_CLASSIFICATION")

    # Prefix check
    prefix = capture_obj["path_prefix"]
    if prefix is not None:
        for agent in normalized_agents:
            aid = agent["agent_id"]
            if aid == prefix or aid.startswith(prefix + "/"):
                continue
            fail("PREFIX_MISMATCH")

    # Build snapshot
    snapshot = {
        "schema": "xar.authorized-dispatch-snapshot/v1",
        "snapshot_id": capture_obj["snapshot_id"],
        "observed_at_utc": capture_obj["observed_at_utc"],
        "complete": True,
        "agent_count": len(normalized_agents),
        "agents": normalized_agents
    }

    # Counts
    counts = {
        "agents": len(normalized_agents),
        "running": 0,
        "completed": 0,
        "error": 0,
        "guard_error": 0,
        "capacity_error": 0,
        "unknown_error": 0,
        "root_running": root_running
    }
    for agent in normalized_agents:
        s = agent["status"]
        if s == "RUNNING":
            counts["running"] += 1
        elif s == "COMPLETED":
            counts["completed"] += 1
        elif s == "ERROR":
            counts["error"] += 1
            kinds = agent["error"]["confirmed_kinds"]
            if "GUARD" in kinds:
                counts["guard_error"] += 1
            if "CAPACITY" in kinds:
                counts["capacity_error"] += 1
            if "UNKNOWN" in kinds:
                counts["unknown_error"] += 1

    view = {
        "path_prefix": prefix,
        "returned_view_complete": True,
        "global_status": "UNKNOWN",
        "root_returned": "/root" in seen_names,
        "root_status": root_status
    }

    evidence = {
        "capture_kind": capture_obj["capture_kind"],
        "capture_evidence": capture_obj["evidence"],
        "tool_input": {
            "bytes": len(tool_bytes),
            "sha256": hashlib.sha256(tool_bytes).hexdigest()
        },
        "capture_input": {
            "bytes": len(capture_bytes),
            "sha256": hashlib.sha256(capture_bytes).hexdigest()
        }
    }

    result = {
        "schema": "xar.collaboration-roster-normalized/v1",
        "snapshot": snapshot,
        "counts": counts,
        "view": view,
        "evidence": evidence,
        "mode": "DATA_ONLY_REVIEW_REQUIRED",
        "actual_start": False
    }

    # Serialize check
    raw = (json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        fail("PLAN_TOO_LARGE")

    return result


class _Parser:
    def parse_args(self, argv):
        if type(argv) not in (list, tuple) or len(argv) != 6:
            fail("INVALID_ARGUMENTS")
        if any(type(item) is not str for item in argv):
            fail("INVALID_ARGUMENTS")
        result = {}
        for index in range(0, len(argv), 2):
            option, value = argv[index:index + 2]
            if option not in ("--tool", "--capture", "--output") or option in result:
                fail("INVALID_ARGUMENTS")
            result[option] = value
        if set(result) != {"--tool", "--capture", "--output"}:
            fail("INVALID_ARGUMENTS")
        return {key[2:]: value for key, value in result.items()}


def _read(path):
    d_path(path)
    with open(path, "rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        fail("INPUT_TOO_LARGE")
    return raw


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = _Parser()
    try:
        args = parser.parse_args(argv)
        tool_path = args["tool"]
        capture_path = args["capture"]
        output_path = args["output"]
        d_path(tool_path)
        d_path(capture_path)
        d_path(output_path)
        tool_bytes = _read(tool_path)
        capture_bytes = _read(capture_path)
        result = normalize_roster(tool_bytes, capture_bytes)
        raw = (json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
        with open(output_path, "xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("incomplete output")
        print(json.dumps({"code": "ROSTER_DATA_CREATED", "actual_start": False, "agents": result["counts"]["agents"]}))
        return 0
    except PlanError as error:
        print(json.dumps({"code": error.code, "actual_start": False}), file=sys.stderr)
        return 2
    except FileExistsError:
        print(json.dumps({"code": "OUTPUT_EXISTS", "actual_start": False}), file=sys.stderr)
        return 3
    except OSError:
        print(json.dumps({"code": "DATA_IO_FAILED", "actual_start": False}), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
