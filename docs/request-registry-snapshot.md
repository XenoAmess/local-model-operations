# Report a frozen request registry

Use [snapshot_request_registry.py](../scripts/snapshot_request_registry.py) to report recorded BEGIN/END boundaries from an owner-provided frozen copy of a dedicated version-1 request registry. It reads the copy and emits one JSON line. It does not query live sockets, call a model or change the caller/dispatcher.

The input must already be closed, consolidated and immutable. The tool does not create a consistent backup. It rejects a missing file, UNC input and visible WAL/SHM/journal companions; absence of companions does not establish that a database is inactive. Path checks are not a filesystem sandbox.

Replace the placeholder below with the absolute local filename of that trusted copy. Use the execution machine's configured Python executable as the first command token.

```text
python -B scripts/snapshot_request_registry.py ABSOLUTE_LOCAL_DATABASE --limit 128
```

The default limit is 128; an explicit limit must be canonical decimal 1–10000. Input and normalized paths have a 4096-byte UTF-8 bound. The report is limited to 65536 UTF-8 bytes. An invalid input or oversized report produces one compact JSON error on stderr and exit 2, with no partial success line.

The report includes total begun, paired ended, unpaired, ended-invoked and ended-not-invoked counts, a bounded oldest-first record list, returned/truncated values and the recorded capacity. BEGIN tokens are omitted. An unpaired record has state OPEN_UNKNOWN; the output explicitly retains global_coverage and live_http as UNKNOWN. It does not infer a running request, globally empty service or backend capacity from registry rows.

The original implementation came from one genuine OpenCode assistant/tool task: eleven model requests, ten tool-call finishes and one stop. The owner corrected UTF-8 path bounds, oversized limit parsing and full meta-table validation. A separate ordinary HTTP counter supplied no accepted concrete finding. [The source-round record](evidence/2026-11-04-opencode-frozen-registry-cli-source-round.json) preserves the original pending-software cutoff.

The [later software record](evidence/2026-11-04-opencode-frozen-registry-cli-software-later.json) retains the first four-method run with two cleanup errors. The owner-created fixture used a transaction context without closing its SQLite connection. A Test-only revision added explicit closing around that transaction; all four test bodies and assertions stayed unchanged and the CLI bytes did not change. Three affected methods then passed without connection warnings. Final qualification combines those three with the original unaffected pure-path method, rather than reporting a new complete four-method run.

The published CLI and [manual witness](../tests/fixtures/registry_snapshot_cli_witness.py) preserve those qualified source bytes. Destination copies were not rerun for publication. The witness is kept outside normal test discovery because it requires explicit owned fixture configuration. To run it for a new necessary verification, set REGISTRY_SNAPSHOT_CLI to the absolute script filename and REGISTRY_SNAPSHOT_TEST_ROOT to an existing empty owned scratch directory, then invoke the configured Python executable with -B and the witness path. It creates synthetic registry fixtures and invokes the CLI; it does not open an active registry.

Verification covers finite Windows cases: counts and truncation, a filename containing space/hash/percent, unchanged DB bytes and directory contents, invalid limit forms, missing inputs, each companion type, UTF-8/surrogate rejection, extra meta rows and oversized output without partial stdout. This does not establish all SQLite corruption, filesystem race or platform behavior. No active operator use, Runtime integration, performance improvement or net owner-time saving was measured.
