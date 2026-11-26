#!/usr/bin/env python3
"""Keep local video accounting tracked until the shared queue reports a terminal state."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
MODELS = ("fasth3-omni-bf16", "open-h3-2k")
ACTIVE = {"queued", "in_progress"}
FINAL = {"completed": "completed", "failed": "failed", "cancelled": "failed"}
VIDEO_ID = re.compile(r"video_gen_[a-f0-9]{32}:openai")
CLAIM_TTL = timedelta(minutes=5)


def plan(row, now):
    status = row["accounting_status"]
    provider_status = row["provider_status"]
    state = row["queue_status"]
    due = row["next_check_at"]
    attempts = row["poll_attempts"]
    if row["queue_model"] is None:
        return "missing_queue_job", None
    if row["queue_model"] != row["model"] or state not in ACTIVE | FINAL.keys():
        return "queue_job_mismatch", None
    exhausted_while_active = (
        status == "unpriceable" and provider_status in ACTIVE
        and row["unpriceable_reason"] == "max_poll_attempts"
        and row["aggregate_log_written_at"] is None and row["governance_reported_at"] is None
    )
    if status == "unpriceable" and not exhausted_while_active:
        return "needs_accounting_review", None

    if state in ACTIVE:
        if status not in {"pending", "unpriceable"} or provider_status in FINAL:
            return "state_conflict", None
        if status == "pending" and state == provider_status and due is None and attempts == 0:
            return "waiting", None
        return "deferred", ("pending", state, None, 0)

    state = FINAL[state]
    if status == "processing":
        if due is not None:
            return "settling", None
        claim = row["claimed_at"]
        retry = max(now, datetime.fromisoformat(claim) + CLAIM_TTL) if claim else now
        return "retry_scheduled", (status, state, retry, attempts)

    if provider_status in ACTIVE or exhausted_while_active:
        return "handed_off", ("pending", state, now, 0)
    if due is not None:
        return "settling", None
    if status == "error" or attempts > 0:
        # A failed terminal status can clear the native deadline. Re-create it
        # without resetting the native retry budget or its settlement markers.
        retry = now + timedelta(minutes=5 if attempts >= 40 else 2)
        return "retry_scheduled", (status, state, retry, attempts)
    return "handed_off", (status, state, now, attempts)


def reconcile(queue_db, bifrost_db, *, apply=False, now=None):
    now = now or datetime.now(timezone.utc)
    counts = Counter()
    handed_off = []
    mode = "rw" if apply else "ro"
    with closing(sqlite3.connect(f"{bifrost_db.resolve().as_uri()}?mode={mode}", uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        db.execute("ATTACH DATABASE ? AS queue", (f"{queue_db.resolve().as_uri()}?mode=ro",))
        jobs = db.execute(
            "SELECT b.id, b.batch_id, b.model, b.accounting_status, b.provider_status, b.next_check_at, "
            "b.poll_attempts, b.unpriceable_reason, b.aggregate_log_written_at, b.governance_reported_at, "
            "b.runner_id, b.claimed_at, b.updated_at, q.model AS queue_model, q.status AS queue_status "
            "FROM batch_jobs AS b "
            "LEFT JOIN queue.jobs AS q ON q.id = substr(b.batch_id, 1, length(b.batch_id) - 7) "
            "WHERE b.kind = 'video' AND b.provider = 'openai' AND b.model IN (?, ?) "
            "AND b.batch_id GLOB 'video_gen_*:openai' AND length(b.batch_id) = 49 "
            "AND b.accounting_status IN ('pending', 'unpriceable', 'processing', 'error')",
            MODELS,
        ).fetchall()
        with db:
            for row in jobs:
                if not VIDEO_ID.fullmatch(row["batch_id"]):
                    continue
                action, update = plan(row, now)
                if update and apply:
                    status, provider_status, due, attempts = update
                    # A native sweep or client retrieve may have changed this row
                    # since the snapshot. Any such race can wait for the next tick.
                    changed = db.execute(
                        "UPDATE batch_jobs SET accounting_status = ?, provider_status = ?, next_check_at = ?, "
                        "poll_attempts = ?, updated_at = ?, unpriceable_reason = NULL "
                        "WHERE id = ? AND accounting_status = ? AND updated_at IS ? AND next_check_at IS ? "
                        "AND provider_status = ? AND runner_id IS ? AND claimed_at IS ?",
                        (status, provider_status, due.isoformat(sep=" ") if due else None, attempts,
                         now.isoformat(sep=" "), row["id"], row["accounting_status"], row["updated_at"],
                         row["next_check_at"], row["provider_status"], row["runner_id"], row["claimed_at"]),
                    ).rowcount
                    if not changed:
                        counts["concurrent_change"] += 1
                        continue
                counts[action] += 1
                if action == "handed_off":
                    handed_off.append(row["batch_id"])
    return {"counts": dict(counts), "handed_off": handed_off}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-db", type=Path, default=ROOT / "outputs/video-queue/queue.sqlite3")
    parser.add_argument("--bifrost-db", type=Path, default=ROOT / "llm-lab/deployment/bifrost-lan/data/config.db")
    parser.add_argument("--apply", action="store_true", help="Apply the planned schedule changes")
    args = parser.parse_args()
    result = reconcile(args.queue_db, args.bifrost_db, apply=args.apply)
    if not args.apply or any(count for action, count in result["counts"].items() if action not in {"waiting", "settling"}):
        print(json.dumps(result))


if __name__ == "__main__":
    main()
