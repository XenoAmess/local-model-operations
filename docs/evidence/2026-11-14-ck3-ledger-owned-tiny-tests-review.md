# NEW-owned Ledger source review 2

Both findings were rejected: the NEW reference already preserves the expected reference object, and the optimized verify path does not call exact. The tiny regression tests target behavior and first-error ordering; they are not allocation-counter mirrors.

Both complete wires were frozen before concurrent first POSTs. Each had 86 complete Java files plus 2 source contracts. Stop/DONE/strictJSON, 652668 input/251 output tokens, TTFT 178.1751085s and total 180.0811056s,0retry. Actualpeak2, no new source/Test hunk.

No old selected739b source provenance, full software validation or Runtime/performance qualification was granted. [Exact source/cost/disposition](2026-11-14-ck3-ledger-owned-tiny-tests-review.json).
