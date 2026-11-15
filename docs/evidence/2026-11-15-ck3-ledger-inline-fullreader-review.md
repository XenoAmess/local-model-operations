# Ledger exact-lease inline reader review

Two independent source reviews used complete old/new components, the real lease provider and the existing 276/312 identity tests. The inline candidate was proposed by the owner; the model authored no implementation.

Both streams ended with `stop`, DONE and valid JSON, with no retry. Peak HTTP concurrency was 2 for 20.45117 seconds; 112,752 input and 1,780 output tokens were reported. Both frozen requests exactly match actual REQUEST files and full SSE content.

The semantic answer incorrectly claims that acquisition outside a `try` enters its catch with a null lease. The old Path overload has the same placement and the provider closes partial handles itself. Its second finding retreats to a maintenance concern without a reachable omitted check.

The cost answer counts uncalled getters and repeats the intermediate Document. Successful exact acquisition has three payload clones before and two after: one constructor clone is removed. Both routes still perform the same fresh read/hash/identity work and preserve expected-reference and Document identity. Later getter copies remain separate. This static allocation difference establishes no elapsed-time or peak-memory improvement.

Zero new reachable findings and zero source/Test hunks were adopted. The old rejected value-equals fast return remains rejected. Owner compilation, tests, publication and Runtime adoption are independent evidence levels.

The original 1536 MiB budget denial is preserved. Root raised only the prospective engineering material cap to 1538 MiB; Native funded the exact 1,410,048 B scope once. No prior closed pool was reused.

[Detailed source, HTTP and review record](2026-11-15-ck3-ledger-inline-fullreader-review.json).
