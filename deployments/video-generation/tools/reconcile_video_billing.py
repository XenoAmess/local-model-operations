#!/usr/bin/env python3
"""Re-arm Bifrost settlement for local videos that outlasted its poll budget."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
MODELS = ("fasth3-omni-bf16", "open-h3-2k")
TERMINAL = {"completed", "failed", "cancelled"}
VIDEO_ID = re.compile(r"(video_gen_[a-f0-9]{32}):openai")

# Only recover abandoned polling. A provider error, missing rate, active
# accounting claim or existing settlement needs its own handling.
EXPIRED = (
    "kind = 'video' AND provider = 'openai' AND model IN (?, ?) "
    "AND provider_status IN ('queued', 'in_progress') "
    "AND accounting_status = 'unpriceable' AND unpriceable_reason = 'max_poll_attempts' "
    "AND aggregate_log_written_at IS NULL AND governance_reported_at IS NULL "
    "AND runner_id IS NULL AND claimed_at IS NULL"
)


def connect(path, mode):
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode={mode}", uri=True, timeout=5)


def reconcile(queue_db, bifrost_db, *, apply=False):
    with closing(connect(queue_db, "ro")) as queue, closing(connect(bifrost_db, "rw" if apply else "ro")) as bifrost:
        candidates = bifrost.execute(
            f"SELECT id, batch_id, model FROM batch_jobs WHERE {EXPIRED} ORDER BY created_at",
            MODELS,
        ).fetchall()
        terminal = []
        for row_id, batch_id, model in candidates:
            match = VIDEO_ID.fullmatch(batch_id)
            if not match:
                continue
            job = queue.execute("SELECT model, status FROM jobs WHERE id = ?", (match[1],)).fetchone()
            if job and job[0] == model and job[1] in TERMINAL:
                terminal.append((row_id, batch_id, model))

        rearmed = []
        if apply and terminal:
            now = datetime.now(timezone.utc).isoformat(sep=" ")
            with bifrost:
                for row_id, batch_id, model in terminal:
                    update = bifrost.execute(
                        "UPDATE batch_jobs SET accounting_status = 'pending', poll_attempts = 0, "
                        "next_check_at = ?, updated_at = ?, unpriceable_reason = NULL, last_error = NULL "
                        f"WHERE id = ? AND batch_id = ? AND model = ? AND {EXPIRED}",
                        (now, now, row_id, batch_id, model, *MODELS),
                    )
                    if update.rowcount:
                        rearmed.append(batch_id)
    return {"expired": len(candidates), "terminal": [batch_id for _, batch_id, _ in terminal], "rearmed": rearmed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-db", type=Path, default=ROOT / "outputs/video-queue/queue.sqlite3")
    parser.add_argument("--bifrost-db", type=Path, default=ROOT / "llm-lab/deployment/bifrost-lan/data/config.db")
    parser.add_argument("--apply", action="store_true", help="Return eligible jobs to Bifrost's settlement queue")
    args = parser.parse_args()
    result = reconcile(args.queue_db, args.bifrost_db, apply=args.apply)
    if not args.apply or result["rearmed"]:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
