# Optional durable request boundaries

`scripts/call_with_registry.py` is an explicit opt-in sibling of the ordinary caller. Its registry module records committed `POST_BEGIN` and `ATTEMPT_END` boundaries in a dedicated local SQLite file. Existing `scripts/call.py`, running dispatchers and business clients keep their current entry points.

```text
python scripts/call_with_registry.py task.json unique-task-id --config config/source-high-concurrency-direct.json --output D:/review/unique-output --machine-id example-machine --owner example-owner --request-registry D:/review/request-boundaries.sqlite
```

Paths above are mapping examples. Choose an absolute local database path owned by this client. `LOCAL_MODEL_REQUEST_REGISTRY` supplies the same optional setting; omitting both leaves registry state disabled. Normal client maintenance, finite output, retries, raw evidence and stop-file rules still apply.

The hook appends the ordinary EVENTS row first, then records the same identity and timestamp. A committed BEGIN precedes transport. A registry write failure is a local evidence failure: it blocks transport when BEGIN fails and prevents another retry when END fails. Each attempt owns its token; normalized equivalent END timestamps are idempotent, while conflicting identities or instants are rejected. History has finite storage limits and is retained without automatic expiry or deletion.

`RequestRegistry.snapshot(limit=...)` returns bounded records and consistent aggregate counts from one read transaction. It covers only boundaries recorded in that database. An unpaired BEGIN is `OPEN_UNKNOWN`; it does not establish that a socket remains live. `global_coverage` and `live_http` remain `UNKNOWN`, including when all recorded BEGIN rows have an END. Filesystem locality is a trusted owner configuration premise, not a sandbox guarantee.

Nine distinct raw-source methods passed the first isolated no-network validation: three caller tests, one historical canonical compatibility test, four independent DATA tests and one terminal-history test. The public package contains the caller three and terminal one. The module and sibling caller preserve the qualified raw bytes; public test docstrings and default source/scratch bindings are portable projections. Those new default bindings have not been executed. Explicit source/scratch environment settings continue to take precedence.

One genuine source-review canary exercised the opt-in caller and exact registry/event pairing. Its first launch failed on owner stdout handling; an explicit launch repair completed. The model's completed counter was rejected for misreading the identity-check order. Neither HTTP completion nor the registry itself grants global coverage, software correctness or performance credit. [Pins, validation and cost boundaries](evidence/2026-11-04-opt-in-request-registry.json) retain these distinctions.
