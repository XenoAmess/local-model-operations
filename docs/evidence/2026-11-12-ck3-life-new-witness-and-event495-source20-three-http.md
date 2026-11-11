# Two new Life designs and the actual Event495 Source20 review

Three distinct requests ran together after the earlier [Life source-limit review](2026-11-12-ck3-future-life-afterack-source-no.md): a new typed witness/codec/validator design, actual Factory producer wiring, and review of the owner's completed Event495 Source20 candidate. Peak **3** lasted **96.564502 s**. All returned HTTP200 / stop / DONE / valid JSON, with no retry or truncation: **623354 input / 6452 output tokens**.

| Obligation | Content TTFT | Total | Input/output | Owner disposition |
|---|---:|---:|---:|---|
| New Life witness design | 80.1683 s | 102.2243 s | 230227 / 2562 | Rejected |
| New Life Factory wiring | 69.4206 s | 96.5647 s | 230271 / 1702 | Rejected |
| Actual Event495 Source20 | 48.0944 s | 100.6553 s | 162856 / 2188 | No actionable finding |

The first Life design reconstructs an `ObservedFrame` and then asks a privately issued token to accept it as the identical original occurrence. The supplied token rejects reconstructed objects. It also manufactures an ACK with custody but no outbound original, contrary to the supplied ACK constructor, and never establishes the required receive order after the setter ACK. Referenced auxiliary codec declarations were incomplete in the input; guesses about those helpers are kept separate from the errors demonstrated by supplied declarations.

The Factory candidate calls absent `ActionCommand.ack()` and packet-identity `requestId()`, treats `currentSnapshot` identity as after-ACK freshness, and fabricates identity components with zeros. It does not wire both actual warm call sites or implement the required real Driver producer. The owner checked that `context.transport()` and `originalRequestChronology(String)` do exist; those were not falsely counted as invented APIs. **Neither candidate was compiled or adopted.**

Source20 was already an owner-written candidate before POST. Its review confuses a callback being installed with a private scope being active: empty explicitly permits ordinary fallback, while an active private failure throws. The remaining alleged findings withdraw themselves or propose no change. The cached-family reconciliation route bypasses the new ordinary loop, so the old exception and guard cannot be dismissed as redundant. Suggested stale-to-later tests were already in owner preparation and earn no new testing credit.

All three results are retained unchanged. No model code, fix, compile, Runtime admission or saved-day credit follows. The separate DTO Source21 repair and live recovery were owner work. Event495's original after frame/time was not exposed, so a source-reachable stale path is not claimed as its uniquely proven runtime cause.

These prompts differ from ordinary business requests. Cached tokens are unreported; the evidence cannot attribute these TTFT values to cache, service queueing or a specific contention cause. All requests ended before grading; the operator did not leave artificial inflight slots. Further work waits for an actual new method contract, not another same-prefix validator run.

[Structured audit and complete rejection reasons](2026-11-12-ck3-life-new-witness-and-event495-source20-three-http.json).
