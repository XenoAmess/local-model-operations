# Collaboration roster DATA normalization

This optional module converts a supplied collaboration roster JSON value into the existing authorized-dispatch snapshot schema, counts, and input-byte evidence. It imports the existing dispatch_validation module in this directory; the two existing authorized-dispatch production modules remain unchanged.

The program has no collaboration tool, clock, network, subprocess or dispatch capability. The whole tool return still has to be saved manually by an operator, including every returned row and completed-message body. A cloud collaboration tool result cannot be automatically obtained as a functions V8 value by this helper. Its SHA is over the supplied serialization bytes, not raw tool transport bytes or an automatic sample. It only normalizes DATA after that capture. Any 30-60 second coordinator-cycle preparation savings remain unmeasured.

## API

normalize_roster(tool_bytes, capture_bytes) returns a new JSON-compatible envelope. Both arguments must be exact bytes, each at most1MiB; original dispatch_validation strict JSON bounds apply. PlanError is the existing safe validation exception. There is no implicit timestamp, capture ID, prefix, completeness marker or classification.

The tool value is exactly an agents array of rows containing agent_name and agent_status. Supported statuses are the held shapes "running", {"completed": primitive string}, and {"errored": nonempty primitive string}. Other or ambiguous shapes reject. Names are unique canonical agent IDs. A path_prefix admits only itself and boundary descendants.

The explicit capture object has these exact fields:

- schema: xar.collaboration-roster-capture/v1
- snapshot_id: caller-supplied identifier
- observed_at_utc: caller-supplied canonical UTC
- returned_view_complete: true for all entries of this returned view
- path_prefix: explicit null or canonical agent ID
- capture_kind: STRUCTURED_VALUE_SERIALIZATION
- evidence: explicit nonempty source description
- error_classifications: explicit array of objects with agent_id, confirmed_kinds and evidence

Each errored member needs one classification row, with a nonempty unique subset of GUARD, CAPACITY, UNKNOWN and explicit evidence. Missing, duplicate or unused classifications reject. No words in raw/completed text are used to infer a classification, authority, task identity or actualSTART. The program never creates same_task, pending work or grants.

The envelope contains snapshot, counts, view, evidence, mode=DATA_ONLY_REVIEW_REQUIRED and actual_start=false. Only snapshot is serialized for the unchanged plan_dispatch API; pending bytes, grants and explicit now remain separate caller inputs. Counts categories may overlap when operator-curated kinds overlap. Global status is always UNKNOWN, including a complete65-member returned view. Root contributes to root_running only if /root is returned with running status.

A minimal synthetic bytes-only call is:

```python
import json
from collaboration_roster_snapshot import normalize_roster

tool_bytes = json.dumps({"agents": [
    {"agent_name": "/root/example_branch", "agent_status": "running"}
]}).encode("utf-8")
capture_bytes = json.dumps({
    "schema": "xar.collaboration-roster-capture/v1",
    "snapshot_id": "synthetic-example",
    "observed_at_utc": "2026-01-02T03:04:05Z",
    "returned_view_complete": True,
    "path_prefix": "/root/example_branch",
    "capture_kind": "STRUCTURED_VALUE_SERIALIZATION",
    "evidence": "Synthetic documentation DATA; no actual tool capture",
    "error_classifications": []
}).encode("utf-8")
result = normalize_roster(tool_bytes, capture_bytes)
snapshot_bytes = json.dumps(result["snapshot"]).encode("utf-8")
```

## CLI and tests

main(argv=None) accepts exactly --tool, --capture and --output once each, in any order. CLI paths retain the existing canonical D:/ lexical rule; the bytes API is independent of file paths. It reads only the two explicit bounded inputs, validates and serializes fully, then opens the new output with xb. It never overwrites. Fixed JSON summaries report exits0 DATA-created,2 invalid DATA/arguments,3 existing output,4 IO/short-write. A failed partial new output is not atomic success and is not rewritten or retried.

test_collaboration_roster_snapshot.py uses only synthetic rows, synthetic operator evidence and in-memory D-path CLI streams. It contains no private roster/context/raw, machine-local fixture path or private oracle. These are new public Test bindings; earlier private five-method acceptance does not validate this projection. A future necessary first should select these five public methods with the two existing production dependencies, without repeating the old private tests or historical CLI.
