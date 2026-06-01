# RMN Agent Run Comparison

## Summary

| Run | Cases | OK | Errors | Route | Required source | Citation | Avg latency | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2026-06-01_after_recursive_ingest` | 5 | 5 | 0 | 100.0% | 100.0% | 60.0% | 17.518 | 0.8124 |
| `2026-06-01_temp0_citation_prompt` | 5 | 5 | 0 | 100.0% | 100.0% | 100.0% | 18.318 | 0.9084 |

## Recommendation

- Best candidate by automatic score: `2026-06-01_temp0_citation_prompt`.
- Treat this as a regression screen, not a full answer-quality judgment.

## `2026-06-01_temp0_citation_prompt` vs `2026-06-01_after_recursive_ingest`

### Regressions
- None detected by automatic checks.

### Improvements
- `paper_compare`: citation False -> True
- `paper_protocol_microgel`: paper docs 15 -> 13; citation False -> True

### Other Changes
- None.
