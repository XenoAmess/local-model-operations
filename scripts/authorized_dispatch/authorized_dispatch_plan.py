"""DATA-only dispatch planning. The coordinator alone dispatches reviewed plans."""
import argparse
import json
import sys

from dispatch_validation import (MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, PlanError, d_path,
                                 decode, fail, integer, same_identity, utc, validate)


def _decide(agent, task, grant, now):
    # 1. Known agent INTERRUPTED -> NEVER
    if agent is not None and agent["status"] == "INTERRUPTED":
        return ("NEVER", "AGENT_INTERRUPTED", None)

    # 2. A referenced grant with mismatching Identity -> REJECT
    if grant is not None and not same_identity(grant, task):
        return ("REJECT", "GRANT_IDENTITY_MISMATCH", None)

    # 3. Matching explicit grant REVOKED -> NEVER
    if grant is not None and grant["state"] == "REVOKED":
        return ("NEVER", "GRANT_REVOKED", None)

    # 4. ERROR with confirmed GUARD anywhere -> NOT_RETRY
    if agent is not None and agent["status"] == "ERROR":
        error = agent["error"]
        if "GUARD" in error["confirmed_kinds"]:
            return ("NOT_RETRY", "GUARD_CONFIRMED", None)

    # 5. Missing grant -> REJECT; inactive-in-time grant -> HOLD
    if grant is None:
        return ("REJECT", "GRANT_MISSING", None)
    not_before = utc(grant["not_before_utc"])
    expires_at = utc(grant["expires_at_utc"])
    if not (not_before <= now < expires_at):
        return ("HOLD", "GRANT_INACTIVE", None)

    # 6. Missing agent -> HOLD. UNKNOWN -> HOLD.
    if agent is None:
        return ("HOLD", "AGENT_MISSING", None)
    if agent["status"] == "UNKNOWN":
        return ("HOLD", "AGENT_UNKNOWN", None)

    # 7. ERROR CAPACITY-only
    if agent["status"] == "ERROR":
        error = agent["error"]
        kinds = error["confirmed_kinds"]
        # CAPACITY+UNKNOWN and unconfirmed/UNKNOWN errors -> HOLD
        if "UNKNOWN" in kinds or "CAPACITY" not in kinds:
            return ("HOLD", "ERROR_NOT_CAPACITY_ONLY", None)
        same_task = agent["same_task"]
        if same_task is None:
            return ("HOLD", "SAME_TASK_MISSING", None)
        if not same_identity(same_task, task):
            return ("HOLD", "SAME_TASK_MISMATCH", None)
        operation = same_task["operation"]
        if operation not in ("SEND", "FOLLOWUP"):
            return ("HOLD", "INVALID_OPERATION", None)
        if "SAME_TASK_RETRY" not in grant["allowed_actions"]:
            return ("REJECT", "RETRY_NOT_ALLOWED", None)
        # Recovery must start an ERROR owner, including a failed original SEND.
        # Original operation remains snapshot evidence; identity/body never change.
        return ("SAME_TASK_RETRY", "CAPACITY_RETRY", "FOLLOWUP")

    # 8. RUNNING -> SEND; COMPLETED -> FOLLOWUP
    if agent["status"] == "RUNNING":
        if "SEND" in grant["allowed_actions"]:
            return ("SEND", "RUNNING_SEND", "SEND")
        return ("REJECT", "ACTION_NOT_ALLOWED", None)
    if agent["status"] == "COMPLETED":
        if "FOLLOWUP" in grant["allowed_actions"]:
            return ("FOLLOWUP", "COMPLETED_FOLLOWUP", "FOLLOWUP")
        return ("REJECT", "ACTION_NOT_ALLOWED", None)

    # Fallback (should not reach here if status is validated)
    return ("HOLD", "UNHANDLED_STATUS", None)


def plan_dispatch(snapshot_bytes, pending_bytes, *, now_utc, max_age_seconds, max_plan_items):
    integer(max_age_seconds, 1, 3600)
    integer(max_plan_items, 1, 65)
    now = utc(now_utc)
    snapshot, pending = decode(snapshot_bytes), decode(pending_bytes)
    validate(snapshot, pending, now, max_age_seconds, max_plan_items)
    agents = {row["agent_id"]: row for row in snapshot["agents"]}
    grants = {row["grant_id"]: row for row in pending["grants"]}
    items = []
    for task in pending["tasks"]:
        action, reason, operation = _decide(agents.get(task["owner"]), task,
                                             grants.get(task["grant_id"]), now)
        if (action in ("SEND", "FOLLOWUP", "SAME_TASK_RETRY")
                and operation == "FOLLOWUP" and task["owner"] == "/root"):
            action, reason, operation = "REJECT", "ROOT_FOLLOWUP_UNSUPPORTED", None
        dispatch = None
        if action in ("SEND", "FOLLOWUP", "SAME_TASK_RETRY"):
            if operation not in ("SEND", "FOLLOWUP"):
                fail("INVALID_DECISION_OPERATION")
            dispatch = {"method": "send_message" if operation == "SEND" else "followup_task",
                        "target": task["owner"], "task_id": task["task_id"],
                        "message": task["body"], "scope": task["scope"],
                        "write_roots": list(task["write_roots"])}
        items.append({"task_id": task["task_id"], "owner": task["owner"],
                      "grant_id": task["grant_id"], "action": action,
                      "reason": reason, "dispatch": dispatch})
    result = {"schema": "xar.authorized-dispatch-plan/v1", "snapshot_id": snapshot["snapshot_id"],
              "bundle_id": pending["bundle_id"], "observed_at_utc": snapshot["observed_at_utc"],
              "now_utc": now_utc, "max_age_seconds": max_age_seconds,
              "mode": "DATA_ONLY_REVIEW_REQUIRED", "actual_start": False, "items": items}
    _serialized(result)
    return result


def _serialized(plan):
    raw = (json.dumps(plan, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        fail("PLAN_TOO_LARGE")
    return raw


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        fail("INVALID_ARGUMENTS")


def _read(path):
    with open(d_path(path), "rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        fail("INPUT_TOO_LARGE")
    return raw


def main(argv=None):
    parser = _Parser(description="Create a DATA plan for separate coordinator review.")
    for option in ("snapshot", "pending", "now", "max-age-seconds", "max-plans", "output"):
        parser.add_argument("--" + option, required=True)
    try:
        args = parser.parse_args(argv)
        for path in (args.snapshot, args.pending, args.output):
            d_path(path)
        if not args.max_age_seconds.isascii() or not args.max_age_seconds.isdecimal():
            fail("INVALID_ARGUMENTS")
        if not args.max_plans.isascii() or not args.max_plans.isdecimal():
            fail("INVALID_ARGUMENTS")
        if len(args.max_age_seconds) > 4 or len(args.max_plans) > 2:
            fail("INVALID_ARGUMENTS")
        plan = plan_dispatch(_read(args.snapshot), _read(args.pending), now_utc=args.now,
                             max_age_seconds=int(args.max_age_seconds),
                             max_plan_items=int(args.max_plans))
        raw = _serialized(plan)
        with open(args.output, "xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("incomplete output")
        print(json.dumps({"code": "PLAN_DATA_CREATED", "actual_start": False,
                          "plan_items": len(plan["items"])}))
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
