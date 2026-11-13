# Archive/replay hotpath: unsupported handoff rejection and equality shortcut

Twenty complete current production sources, separately labelled existingHELD65 candidate/unrun Test, one existing R75thread and C77 inclusive-wall summary were supplied. Already-present token/full caches, retained parsedCommit, strict decoder/history/row reuse and parser/encoding optimizations were explicit. No new platform or guard removal was requested.

POST05:23:31.886355Z to END05:24:01.685800Z completed200/stop/DONE/validJSON:153623input/1456output, contentTTFT19.7804823s and HTTP29.799411s. Compact725298B/ddc55ad4 prePOST/actual bytes match; one attempt, no retry/length, peak1/current0. BEGIN/END and original response path were reported before review.

The HELD65 rejection is unsupported: actual second checkedManifest retains bytes/size/SHA before taking a pure parsed Obj; same-call object identity is independent of how Archive originally supplied RawJson. Token caching is not Reader AST caching. Finally restoration and safe miss fallback are present; no concrete failing path was given. Unmeasured CPU gain does not establish source unsafety.

The other proposal retains freshread but removes cache-hit contentEquals based on ExactRef/SHA. That does not prove the original byte-equality guard equivalent and is rejected; its private-cache mock/count suggestion is not an old/new regression oracle. No finding, code or test change is adopted, no software/Runtime/ROI or technicalNO is granted, and no second request is planned. [Complete source pins, exact rejection and cost](2026-11-13-ck3-archive-replay-hotpath-review.json).
