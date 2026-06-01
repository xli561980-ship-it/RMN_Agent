# RMN Agent Full Evaluation Report - 2026-06-01

## Artifacts

- Post-ingest golden run: `eval/runs/2026-06-01_after_recursive_ingest.jsonl`
- Final golden run after citation prompt + temperature change: `eval/runs/2026-06-01_temp0_citation_prompt.jsonl`
- Previous baseline run: `eval/runs/2026-05-31_215552_baseline.jsonl`
- Run comparison: `eval/reports/compare_2026-05-31_vs_2026-06-01.md`
- Final comparison: `eval/reports/compare_2026-05-31_vs_2026-06-01_final.md`
- Corpus audit: `eval/reports/corpus_audit_2026-06-01.json`

Note: raw `eval/runs/*.jsonl` artifacts stay local and are intentionally excluded from GitHub because they can include retrieved corpus snippets and generated answer text.

## What Changed

The project now uses the local parser route by default and recursively scans `data/papers/` and `data/manuals/`.

Incremental ingest was run after the recursive scan change. It:

- Repaired `87` stale processed records that had no Chroma chunks.
- Retried those files without marking zero-chunk parses as successful.
- Added `3824` new Chroma chunks from newly visible nested SOP/SDS documents.
- Kept LlamaParse disabled; no LlamaParse credits were used.

Generation was also tightened after the ingest run:

- `fusion_prompts.py` now explicitly forbids merged citations, bare page citations, and multi-source citation brackets.
- `rag_core.py` now uses temperature `0.0` for fusion generation by default.

## Corpus State

| Item | Before | After |
| --- | ---: | ---: |
| Supported disk documents seen by ingest | 572 | 572 |
| Chroma sources | 275 | 483 |
| Chroma chunks | 7891 | 11715 |
| Processed sources | 362 | 483 |
| Processed without Chroma | 87 | 0 |
| Chroma without processed | 0 | 0 |
| Zero-chunk suspects in processed records | 87 | 0 |
| Disk documents not processed | 210 | 89 |

Remaining `89` unprocessed disk documents are not hidden from ingest anymore. They are files that the current local parser cannot turn into chunks, or malformed PDFs. Example observed failure:

```text
manuals/Safety Data Sheets/Sylgard 184 eng.PDF: No /Root object! - Is this really a PDF?
```

These remaining files need either OCR, PDF repair/re-export, or a different local parser strategy.

## Golden Experiment Summary

| Metric | 2026-05-31 baseline | After recursive ingest | Final temp0 + strict citation |
| --- | ---: | ---: | ---: |
| Cases | 5 | 5 | 5 |
| Passed route/source checks | 5 | 5 | 5 |
| Errors | 0 | 0 | 0 |
| Route accuracy | 100.0% | 100.0% | 100.0% |
| Required source hit | 100.0% | 100.0% | 100.0% |
| Citation validation OK | 20.0% | 60.0% | 100.0% |
| Average latency | 17.135 s | 17.518 s | 18.318 s |
| Average paper docs | 6.8 | 7.2 | 6.8 |
| Average SOP docs | 2.0 | 2.0 | 2.0 |
| Automatic score | 0.7143 | 0.8124 | 0.9084 |

Final automatic comparison result:

- Best candidate: `2026-06-01_temp0_citation_prompt`
- Regressions: none detected
- Improvements:
  - `sop_litesizer_basic`: citation validation changed from false to true
  - `missing_evidence`: citation validation changed from false to true
- `paper_protocol_microgel`: citation validation changed from false to true
- `paper_compare`: citation validation changed from false to true

No final golden case has unknown citation hints or numeric lines without citations.

## Interpretation

The recursive ingest work improved the knowledge base coverage substantially and did not regress the golden retrieval set. The citation prompt and temperature change then fixed the machine-checkable citation failures on the current golden set. The golden set is still small, but this was a clean improvement:

- More sources are available.
- No stale processed-without-Chroma records remain.
- Route/source checks stayed at 100%.
- Citation validation improved from 20% to 100%.

The next highest-leverage fix is broadening evaluation coverage. The current five-case golden set now passes, but it is not enough to prove robustness across SDS lookup, German SDS, malformed files, OCR-needed scans, and nested manual retrieval.

## Recommended Next Steps

1. Expand `eval/golden_questions.jsonl`.
   Add cases for SDS lookup, chemical safety, German SDS, malformed/missing evidence, and nested manual retrieval.

2. Add OCR/local repair path for the remaining 89 unprocessed files.
   Start with a small sample. Do not reintroduce LlamaParse as default.

3. Keep citation validator strict.
   The final golden run shows the model can comply when prompted and run at temperature 0. Avoid loosening the validator unless there is a concrete false positive.
