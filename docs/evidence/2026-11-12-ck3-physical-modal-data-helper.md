# Physical modal availability: bounded DATA helper

The source owner delegated a small new pure DATA helper, while independently implementing Clock, original-proof and archive integration. Three existing frozen packets distinguish an exact owner-unavailable object from a missing hint; explicit null remains separate. No field is filled, normalized or copied from older observations, and the helper issues no permission.

| Output obligation | Finish | Content TTFT | Total | Input / output |
| --- | --- | ---: | ---: | ---: |
| Helper plus complete packet regressions | length, whole unused | 3.7935s | 41.6016s | 27652 / 6500 |
| New helper-only obligation | stop/DONE/valid JSON | 3.6812s | 7.7441s | 26794 / 686 |

The first response was never read, parsed or extracted. Its cost and raw evidence remain retained; combining helper and packet-heavy full tests was an operator scope/budget error, not a demonstrated semantic failure. The explicitly authorized second task changed output scope to one small class, retained complete input evidence and used none of the truncated response. It was not stream continuation. Total input 54446/output 7186, summed HTTP duration 49.3457s, actual peak 1/current 0, no transport retry. Cached tokens and financial cost were unreported.

The complete 57-line helper matches the four states, exact five-key unknown profile, two cross-availability directions and three unchanged boundary comparisons. Three owner corrections are required: use standard constant BigInteger equality rather than invoking an input subclass, and constant String equality for the two text fields so public Text(null) values remain OTHER_PRESENT instead of throwing. Strictly parsed real packets do not contain those artificial malformed values; the public DATA contract still requires them to be handled. This is a useful partial source core, not an originally flawless implementation or an adopted source at this review cut.

A separate test owner already holds active ownership of the exact three-packet regressions and malformed/known/null/other-boundary cases, so no duplicate Test request was dispatched. No Java/tests, production source writes, live query, action or sampling occurred. Final callers must independently bind actual PhysicalAfterAck frames, Status chronology and archived proof; DATA compatibility alone grants none of those. No Runtime or speed benefit is inferred.

[Actual request parameters, costs and source grade](2026-11-12-ck3-physical-modal-data-helper.json).
