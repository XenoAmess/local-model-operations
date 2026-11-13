# C81 StageB crash and terminal replay review

No new actionable finding, code or test hunk was adopted. Agreement that the backend gate is false was supplied before POST. The returned crash matrix and read roles need substantive source corrections.

The authorization read is ARMED. The two later independent IDLE reads are the actual CANCEL ControlApplied read and a separate terminal Status read; they are compared with each other, while preserving ticks/date from ARMED. The answer instead conflated ARMED with the first IDLE. Its quoted continuation size branch is absent from that class, and Pending/exception behavior belongs to distinct live-observe and continuation callers. A held planning-scope lookup is not a persistent global cursor reader after a crash.

All 65 relevant Java files and frozen small originals were supplied. The byte-exact call used 383031 input/1089 output tokens, TTFT 99.6971439s and total 110.1418586s, stop/DONE/valid JSON, no retry. Pair overlap was 109.220511s at peak 2. Complete streams are retained; these semantic errors are not truncation or an actual compiler failure.

No controls, positive backend qualification, software/Runtime completion, credit or ROI is granted. [Exact evidence](2026-11-13-ck3-c81-stageb-crash-terminal-replay-review.json).
