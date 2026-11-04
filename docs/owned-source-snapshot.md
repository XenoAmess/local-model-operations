# Bounded owned-source snapshot

[snapshot_owned_source.py](../scripts/snapshot_owned_source.py) reads explicit READY generations, named metadata/receipt pairs, and their existing EVENTS streams. It combines the existing [pool observer](../scripts/pool_observer.py) without opening candidate CONTENT, source specifications, a dispatch database, an operating process or a model connection. It performs no automatic capture, discovery or dispatch.

The trusted owner supplies one absolute local manifest path:

```sh
python -B -X utf8 scripts/snapshot_owned_source.py /owned/state/snapshot-input.json
```

The manifest uses `owned-source-snapshot-input/v2`, an ordered `ready_files` list, `current_ready` naming one listed generation, and explicit `tickets` containing `metadata_path`/`receipt_path`. No implicit machine root or directory scan is used. See the [complete v2 contract](contracts/owned-source-snapshot-v2.md) for exact keys, limits, identity rules and conservative error handling.

The report keeps READY membership, receipt stages and actual POST/END intervals separate. Missing or malformed streams retain UNKNOWN; metadata and receipts are not POST credit. At most 16 READY files, 1024 distinct identities and 1024 named tickets are accepted. Each READY remains bounded to 64 KiB, each observer call to 256 streams. Batches use one conservative common cutoff and combined intervals, rather than adding their independent peak counts. The result is bounded JSON and is explicitly non-atomic, scoped and unrelated to global service state or process liveness.

The [explicit manual witness](../tests/fixtures/snapshot_owned_source_witness.py) requires `OWNED_SOURCE_SNAPSHOT_CLI` and `OWNED_SOURCE_SNAPSHOT_TEST_ROOT`; the latter must be an existing owned D-drive directory on the qualified Windows host. It creates only synthetic fixtures there. Its six pre-frozen methods, one later source regression method and one owner pagination method passed the necessary [eight-method software first](evidence/2026-11-04-opencode-snapshot-software-first936.json) against the exact selected bytes. The unchanged observer dependency is SHA-256 `bec757c283b91960fee157c19e86a513639325f1a563f70635a7c6a27f111a9e`.

This publication preserves production and witness source bytes. The [layout clarification](evidence/owned-source-snapshot-api-layout-source-cut.md) retains its original unexecuted source cutoff; the later software receipt is separate. The shared destination binding has not received its own first, individual fixture CLI import origins were not independently captured, and the tool has not been adopted into a live operating entry. Do not infer process health, database state, task progress, service capacity or measured owner savings from this snapshot.
