"""Compile explicit curation to bounded pending DATA; never dispatch a plan."""
import argparse
import hashlib
import json
import sys

from authorized_dispatch_plan import PlanError, plan_dispatch
from dispatch_validation import (MAX_INPUT_BYTES, d_path, decode, exact_keys,
                                 fail, sequence, text)

ENTRY_KEYS = ("grant_id", "task_id", "owner", "body", "scope", "write_roots", "state",
              "evidence", "not_before_utc", "expires_at_utc", "allowed_actions")


def build_pending(snapshot_bytes, curation_bytes, *, now_utc, max_age_seconds, max_plan_items):
    curation = decode(curation_bytes)
    exact_keys(curation, ("schema", "bundle_id", "prepared_at_utc", "entries"))
    if curation["schema"] != "xar.authorized-dispatch-curation/v1":
        fail("INVALID_CURATION_SCHEMA")
    entries = sequence(curation["entries"], 65)
    grants, tasks = [], []
    for entry in entries:
        exact_keys(entry, ENTRY_KEYS)
        body = text(entry["body"], 16384)
        roots = sequence(entry["write_roots"], 8, 1)
        actions = sequence(entry["allowed_actions"], 3, 1)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        identity = {"task_id": entry["task_id"], "owner": entry["owner"],
                    "body_sha256": digest, "scope": entry["scope"]}
        grants.append(dict(identity, write_roots=list(roots), grant_id=entry["grant_id"],
                           state=entry["state"], evidence=entry["evidence"],
                           not_before_utc=entry["not_before_utc"],
                           expires_at_utc=entry["expires_at_utc"], allowed_actions=list(actions)))
        tasks.append(dict(identity, write_roots=list(roots),
                          grant_id=entry["grant_id"], body=body))
    pending = {"schema": "xar.authorized-dispatch-pending/v1", "bundle_id": curation["bundle_id"],
               "prepared_at_utc": curation["prepared_at_utc"], "grants": grants, "tasks": tasks}
    # Qualification only. Valid negative decisions remain DATA and are never dispatched.
    plan_dispatch(snapshot_bytes, _encoded(pending), now_utc=now_utc,
                  max_age_seconds=max_age_seconds, max_plan_items=max_plan_items)
    return pending


def _encoded(pending):
    raw = json.dumps(pending, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_INPUT_BYTES:
        fail("PENDING_DATA_TOO_LARGE")
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
    parser = _Parser(description="Create pending DATA only; no plan execution.")
    for option in ("snapshot", "curation", "now", "max-age-seconds", "max-plans", "output"):
        parser.add_argument("--" + option, required=True)
    try:
        args = parser.parse_args(argv)
        for path in (args.snapshot, args.curation, args.output):
            d_path(path)
        if (not args.max_age_seconds.isascii() or not args.max_age_seconds.isdecimal()
                or len(args.max_age_seconds) > 4 or not args.max_plans.isascii()
                or not args.max_plans.isdecimal() or len(args.max_plans) > 2):
            fail("INVALID_ARGUMENTS")
        pending = build_pending(_read(args.snapshot), _read(args.curation), now_utc=args.now,
                                max_age_seconds=int(args.max_age_seconds),
                                max_plan_items=int(args.max_plans))
        raw = _encoded(pending)
        with open(args.output, "xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("incomplete output")
        print(json.dumps({"code": "PENDING_DATA_CREATED", "actual_start": False,
                          "entry_count": len(pending["tasks"])}))
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
