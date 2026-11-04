# Explicit trusted-registrar intake and rejection observations

`scripts/source_intake.py` is an optional loop and observability component. It loads a registrar chosen by the operator and may invoke that registrar in a subprocess to prepare and register tasks. The component does not bundle a publisher or registrar, and is not a self-contained queue service. The current qualified publisher/registrar remains an external dependency supplied by the execution machine's operator.

The registrar path is an executable trusted Python module. Its top-level code runs during import. Review and qualify the entire module and its dependencies before selecting it; this interface is not a sandbox or permission check. Never obtain this path from a transfer ticket. A ticket's transfer boolean records an owner's assertion and does not mint authority.

## Explicit paths and sole writer

The CLI requires `--root`, `--registrar` and `--repo`; all three values must be existing absolute operator-controlled paths. `--once` selects one bounded pass; otherwise the loop polls until its stop control exists. There are no machine-root, repository, registrar or operator-identity defaults. The Python APIs are `process_once(*, root, registrar_path, repo, max_pending=256)` and `run(*, root, registrar_path, repo, poll_seconds=0.5)`. Each returns the original list of result dictionaries or runs the loop, respectively.

The operator must establish the existing stopped-writer handoff before replacing an intake. Preserve legacy claims, old receipts, normalized metadata, prepared inputs, outputs and both dispatcher/lease histories. `INTAKE-LOOP*.claim*` refuses startup. `INTAKE-LOOP.lock` is an OS-owned sidecar, held before any pass; it is never deleted or stolen using a PID or age. The registrar must cooperate on the same `READY.registration.lock`. These locks do not establish global process absence or protect against an uncooperative writer.

`INTAKE-STOP.json` prevents further intake work. The registrar owns any separate stop control for registration. The `INTAKE-LOOP.STATE.json` file records a start timestamp and `LOCK_HELD_NOT_POST_CREDIT`; a stale file is not evidence that an operator, process or model request is still running. No hard-coded operator identity is emitted.

## External registrar contract

The supplied module must expose the following reviewed API:

| Name | Required meaning |
| --- | --- |
| `MAX_METADATA`, `MAX_SPEC` | Positive finite byte bounds; metadata operations here require the existing 65536-byte contract. |
| `RegistrationError` | A `ValueError` subclass. Stable uppercase metadata reason codes may be retained in rejection observations. |
| `_metadata(raw)` | Validate the complete transfer schema before registration; return normalized metadata, including safe `id` and `task_id`, trusted path fields and explicit transfer evidence. |
| `bounded_read(path, limit)` | Return complete bytes or fail on the finite byte bound. |
| `strict_json(raw, bom=False)` | Strict bounded-input JSON decoding, including duplicate/non-JSON constant rejection. |
| `sha(raw)`, `js(value)` | SHA-256 hex and deterministic finite JSON bytes. |
| `atomic_file(path, raw, create_only=False)` | Whole-file publication; create-only never overwrites an old destination. |
| `immutable_file(path, raw)` | Accept identical existing bytes; reject a differing immutable destination. |
| `exclusive_file_lock(path, timeout)` | Context manager implementing the existing cooperating sole-writer OS lock. |

The registrar's executable CLI is invoked through the running Python interpreter with `-B -X utf8`, its own reviewed `__file__`, the new immutable normalized metadata path, `--root` and `--repo`. It must accept exactly that contract. Exit 0 must return one bounded strict JSON result whose stage is `READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT` or `ALREADY_REGISTERED_NOT_REPLAYED`.

Exit 3 is reserved for the exact object with keys `stage`, `this_attempt_appended_READY`, `reason`; the values must be `QUEUE_CAPACITY_DEFERRED_BEFORE_READY_APPEND`, false, and either `QUEUE_BYTE_LIMIT` or `QUEUE_RECORD_LIMIT`. This structured result creates no final receipt and keeps the same pending normalized transfer. The loop backs off without changing its identity. Other failures retain uncertain reconciliation metadata and do not prove zero registration or zero POST. Neither the intake nor this API document authorizes automatic replay of unknown work.

The existing transfer contract has required `id`, `task_id`, `owner`, `spec_path`, `output_path`, `owner_zero_post_and_execute_transferred_to_models` and nonempty string `transfer_evidence`, with optional `spec_sha256`. Schema enforcement belongs to the reviewed registrar; this component does not add a second contradictory validator or relax its policy. A normal publisher should validate before atomic ticket publication. Directly writing a malformed ticket does not demonstrate a defect in that publisher.

## Rejection observations and scan counts

At most 4096 `*.ready.json` directory entries are enumerated per pass. Names that do not match the existing safe ticket-name rule and early bounded-read/schema failures produce an immutable observation in `INTAKE-REJECTIONS`. Output basenames are SHA-256 derived from a domain, original filename bytes and complete bounded content SHA or an explicit unavailable marker. Untrusted ticket IDs and paths never form rejection destinations; no raw metadata or exception text is saved in these observations. The observation directory is checked before writing and has its own finite entry bound.

`INTAKE_REJECTED_BEFORE_REGISTRATION_OBSERVATION` is not a final ticket failure receipt. It has `registration_attempted=false`, `final_receipt=false` and `POST_credit=false`. Partial metadata can later become complete and proceed while the original observation stays intact. Identical observations are idempotent and not emitted repeatedly as new events. Rejections do not consume the valid-ticket pass allowance. Observation or status persistence failures stop with reconciliation rather than silently pretending success.

`INTAKE-SCAN.STATE.json` contains `seen_ready_tickets`, `tickets_with_final_receipt`, `tickets_without_final_receipt`, `rejected_before_registration`, `valid_metadata_pending`, `registration_attempts`, `accepted_registration_results`, `reconciliation_results` and `capacity_deferred`. Receipt/pending counts are measured during enumeration; classification and registration counts describe this pass. Check `processing_complete` and `unclassified_pending` before interpreting an interrupted or bounded pass. These reads are not atomic across files. Existing receipt presence is not registration proof, so `actual_registered_tasks` and `HTTP_inflight` remain null and `global_state` remains `UNKNOWN`. Explicit READY and event evidence is still required for actual registration, POST and END counts.

## Opt-in witness and qualification

`tests/fixtures/source_intake_observability_witness.py` is an explicit manual witness outside default test discovery. It uses synthetic metadata with `SYNTHETIC_DATA_NOT_AUTHORIZATION`. Supply `INTAKE_OBSERVABILITY_SOURCE_DIR` pointing to the directory containing the selected `source_intake.py`, `INTAKE_OBSERVABILITY_REGISTRAR_PATH` pointing to the reviewed executable registrar, and `INTAKE_OBSERVABILITY_SCRATCH_DIR` pointing to a fresh existing owned D-directory. The D-only fixture condition from the original finite Windows qualification is retained; this is not an all-platform claim. The witness never invokes an unmocked registrar child. Missing inputs fail; they are not silently skipped.

Five original case methods retain their assertion bodies and cover early schema/filename rejection, immutable observation and later completion, pass allowance/STOP, capacity versus uncertain reconciliation, and empty/bounded/persistence-error paths. One new method covers the changed public CLI binding: missing any of its three required operator paths must reject before importing a dependency or entering the loop. These six public bindings require a future necessary destination first. The earlier private five-method result does not execute or qualify this source projection, its explicit external-registrar binding, public path or CLI entry. No old private green should be rerun to substitute for that destination evidence.

This is source-only public handoff. It does not deploy an intake, supply real authorization, reset a DB, change a caller/configuration or establish live registration, global capacity, automatic capture, performance improvement, malicious-filesystem-race safety or arbitrary power-loss durability. Source, finite software qualification, formal publication and live adoption remain separate.
