# Selected source API layout clarification (after original native wire)
The frozen v1 PUBLIC-CONTRACT.md remains byte-exact and is not backfilled.
Native chose nested ready/http/intake sections. This is accepted as a previously unspecified output-layout detail; the independent six witness expected values are unchanged, while their field access paths now follow that accepted layout.
ready contains current_READY_records, registered_distinct_records, current_READY_bytes, maximum_READY_bytes=65536 and sources[{index,bytes,sha256,current}].
http is the unchanged observer report with observed_POSTs/observed_ENDs/actual_unpaired_POST_attempts/registered_no_observed_POST/current_generation_no_observed_POST added.
intake contains named receipt/linkage metrics. tickets contains per-explicit-ticket sanitized observation.
The seventh method is an owner source-review regression supplement, not an independent model oracle. It covers same-file duplicates, one-sided invalid ticket identity, conflicting unregistered identity, and repeated generations whose raw total exceeds256 but distinct count does not.
Source and all methods remain unexecuted here; Native owns only necessary fixture CLI first. No old SQLite CLI tests are repeated.

Selected input/report schemas are now v2. Manifest<=1MiB, distinct READY identities<=1024, tickets<=1024, READY files<=16/perfile64KiB, output<=2MiB; observer calls remain <=256. One additional owner-only pagination method tests257 distinct identities, cross-batch peak2 and one missing-stream UNKNOWN. This is a later genuine owner extension, not model repair or original model success.
