"""Pure client pending selection; never launches tasks or reserves server slots.

occupied_* are client reservations supplied by the integrating owner, not actual
HTTP event counts. This policy cannot preempt a POST, enforce service priority,
extend deadlines or authorize Runtime work. Integration needs a separate atomic
lease/claim before launch; this pure selection is not a cross-process lock.
"""
from collections import deque

FIELDS = frozenset({"id", "owner", "spec_path", "task_id", "output_path",
                    "config_path", "machine_id", "lane"})


def select_pending(pending, *, occupied_source, occupied_runtime, capacity=60,
                   reserve_runtime=1, last_owner=None):
    """Runtime first, then fair source owners; keep space for future Runtime.

    Source can occupy at most capacity-reserve_runtime even when no Runtime is
    pending. Existing Runtime reservations consume that reserved space. Inputs
    remain untouched; remaining preserves original order. Exact task records are
    returned to their owner only, never printed as a public summary.
    """
    for value in (occupied_source, occupied_runtime, capacity, reserve_runtime):
        if type(value) is not int or value < 0:
            raise ValueError("COUNTS_REQUIRE_NONNEGATIVE_INTEGERS")
    if reserve_runtime > capacity:
        raise ValueError("RESERVE_EXCEEDS_CAPACITY")
    if last_owner is not None and (not isinstance(last_owner, str) or not last_owner):
        raise ValueError("INVALID_LAST_OWNER")
    if not isinstance(pending, list) or len(pending) > 256:
        raise ValueError("INVALID_PENDING_SIZE")
    ids = set()
    owners, groups, runtime = [], {}, []
    for index, record in enumerate(pending):
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError("INVALID_PENDING_RECORD")
        if any(not isinstance(value, str) or not value.strip() or len(value) > 4096
               for value in record.values()):
            raise ValueError("INVALID_PENDING_FIELD")
        if record["lane"] not in ("source", "runtime"):
            raise ValueError("INVALID_PENDING_LANE")
        if record["id"] in ids:
            raise ValueError("DUPLICATE_PENDING_ID")
        ids.add(record["id"])
        if record["lane"] == "runtime":
            runtime.append(index)
        else:
            owner = record["owner"]
            if owner not in groups:
                groups[owner] = deque()
                owners.append(owner)
            groups[owner].append(index)
    free = max(0, capacity - occupied_source - occupied_runtime)
    selected_indexes = runtime[:free]
    runtime_selected = len(selected_indexes)
    source_limit = capacity - reserve_runtime
    source_budget = min(free - runtime_selected, max(0, source_limit - occupied_source))
    cursor = (owners.index(last_owner) + 1) % len(owners) if last_owner in groups else 0
    selected_owner = last_owner
    for _ in range(source_budget):
        for _ in range(len(owners)):
            owner = owners[cursor]
            cursor = (cursor + 1) % len(owners)
            if groups[owner]:
                selected_indexes.append(groups[owner].popleft())
                selected_owner = owner
                break
        else:
            break
    selected_set = set(selected_indexes)
    selected_source = len(selected_indexes) - runtime_selected
    return {
        "selected": [pending[index] for index in selected_indexes],
        "remaining": [record for index, record in enumerate(pending) if index not in selected_set],
        "limits": {
            "capacity": capacity, "reserve_runtime": reserve_runtime,
            "occupied_source": occupied_source, "occupied_runtime": occupied_runtime,
            "free_before_selection": free, "source_lane_limit": source_limit,
            "existing_total_overcapacity": max(0, occupied_source + occupied_runtime - capacity),
            "existing_source_reserved_limit_overage": max(0, occupied_source - source_limit),
            "selected_runtime": runtime_selected, "selected_source": selected_source,
            "free_after_selection": free - len(selected_indexes),
            "last_source_owner": selected_owner,
            "counts_are_client_admission_reservations": True,
            "actual_HTTP_or_server_slot_claim": False,
            "already_POSTed_jobs_modified": False
        }
    }
