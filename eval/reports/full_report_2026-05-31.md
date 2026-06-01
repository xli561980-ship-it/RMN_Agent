# RMN Agent Full Evaluation Report - 2026-05-31

## Artifacts

- Golden run: `eval/runs/2026-05-31_215552_baseline.jsonl`
- Run comparison: `eval/reports/baseline_2026-05-31.md`
- Corpus audit: `eval/reports/corpus_audit_2026-05-31.json`
- Parser audit sample without LlamaParse key: `eval/runs/parse_audit_2026-05-31_sample.jsonl`
- Parser audit sample after configuring `LLAMA_CLOUD_API_KEY`: `eval/runs/parse_audit_2026-05-31_llamaparse_sample.jsonl`

## Golden Experiment Summary

Configuration: `eval/configs/baseline.json`

Generation was enabled, so the run includes retrieval, answer generation, and citation validation.

| Metric | Result |
| --- | ---: |
| Cases | 5 |
| Passed route/source checks | 5 |
| Errors | 0 |
| Route accuracy | 100.0% |
| Required source hit | 100.0% |
| Citation validation OK | 20.0% |
| Average latency | 17.135 s |
| Average paper docs | 6.8 |
| Average SOP docs | 2.0 |
| Automatic score | 0.7143 |

Case-level results:

| Case | Route | Paper docs | SOP docs | Latency | Citation OK |
| --- | --- | ---: | ---: | ---: | --- |
| `sop_litesizer_basic` | `SOP_ONLY` | 0 | 5 | 11.862 s | false |
| `paper_protocol_microgel` | `PAPER_ONLY` | 13 | 0 | 26.761 s | false |
| `hybrid_replicate_safety` | `HYBRID` | 5 | 5 | 16.331 s | true |
| `paper_compare` | `PAPER_ONLY` | 8 | 0 | 17.000 s | false |
| `missing_evidence` | `PAPER_ONLY` | 8 | 0 | 13.719 s | false |

## Interpretation

The retrieval/routing layer is currently healthy on the small golden set: every expected route and required source check passed.

The generation/citation layer is not yet healthy enough for production claims. Four of five generated answers failed the lightweight citation validator:

- `sop_litesizer_basic`: 2 numeric claim lines were not cited on the same line.
- `paper_protocol_microgel`: generated a combined page citation not present in the allowed hint set.
- `paper_compare`: generated combined page citations not present in the allowed hint set.
- `missing_evidence`: generated a multi-source combined citation not present in the allowed hint set.

This does not necessarily mean the facts are wrong. It means the answer formatting and citation validator contract are misaligned: the model is merging citations such as `p.5, p.13` or multiple sources into one bracket, while the validator expects exact per-chunk citation hints from the retrieval bundle.

## Corpus Coverage Audit

Corpus audit counts:

| Item | Count |
| --- | ---: |
| First-level supported disk documents | 363 |
| Recursive supported disk documents | 572 |
| Current ingest supported documents | 572 |
| Recursive disk documents not seen by current ingest | 0 |
| Nested supported documents | 209 |
| Processed sources | 362 |
| Chroma sources | 275 |
| Chroma chunks | 7891 |

Important gaps:

- Recursive scanning is now implemented; the `209` nested supported documents are visible to ingest.
- `210` disk documents are not yet in `processed_files.json`: the 209 nested documents plus `manuals/Sylgard 184 eng.PDF`.
- `87` processed sources have no Chroma chunks. These are likely zero-text parse results, previous partial ingest records, or parse failures that still got recorded.
- Chroma has no source that is missing from `processed_files.json`.

Implementation decision after this report:

- `iter_ingest_jobs()` now recursively scans `data/papers/` and `data/manuals/`.
- Streamlit's sidebar corpus list also shows nested files.
- Future ingest runs remove processed records that have no corresponding Chroma source, so the 87 zero-chunk suspects are retried instead of being treated as successful.
- Files that parse to zero chunks are no longer written to `processed_files.json` or `corpus_manifest.json`.

## Parser Audit / Local Parser Route

First parser audit sample: 5 files.

Result: all 5 preferred `fallback`, but this was because LlamaParse did not actually run.

Observed LlamaParse error for every sample in the first run:

```text
未设置 LLAMA_CLOUD_API_KEY，无法调用 LlamaParse。
```

After configuring `LLAMA_CLOUD_API_KEY`, the sample was rerun. LlamaParse still did not produce readable segments for these files. The tool output reported the LlamaParse plan quota problem:

```text
You've exceeded the maximum number of credits for your plan.
```

The saved JSONL records this as `parser returned no readable segments` for the LlamaParse branch. Sample outcome:

| Source | Preferred | Fallback OK | LlamaParse OK | Fallback chars | LlamaParse chars |
| --- | --- | --- | --- | ---: | ---: |
| `manuals/(+-)-norepinephrine (+)-bitartrate salt.pdf` | `both_failed` | false | false | 0 | 0 |
| `manuals/-Pico-BreakTM eng.pdf` | `fallback` | true | false | 13496 | 0 |
| `manuals/-usermanual-en-Manual-arium-pro-SLG6101-e.pdf` | `fallback` | true | false | 63606 | 0 |
| `manuals/1-(4-Chlor­o­ben­zoyl­)-5-meth­oxy-2-methyl­in­dol-3-yl­acetic acid.pdf` | `both_failed` | false | false | 0 | 0 |
| `manuals/1-Hydroxybenzotriazole hydrate 123333-53-9 ENG.pdf` | `fallback` | true | false | 17058 | 0 |

Conclusion: LlamaParse is not a viable default for this project under the current pricing/credit constraint. The project should use local parsing by default and keep LlamaParse only as an explicit optional experiment.

Implementation decision after this report:

- Local `.env` disables `LLAMA_CLOUD_API_KEY` and enables `INGEST_PDFPLUMBER_FALLBACK=true`.
- Ingest now calls LlamaParse only when `INGEST_USE_LLAMAPARSE=true` and `LLAMA_CLOUD_API_KEY` are both set.
- `llama-parse` is no longer a default dependency; it is optional.

## Recommended Next Fixes

1. Fix citation formatting first.
   The model should cite exact allowed hints, one hint at a time, instead of merged citations like `p.5, p.13` or multi-source brackets. This should raise citation validation sharply without changing retrieval.

2. Add a validator tolerance or postprocessor only after prompt tightening.
   It may be reasonable to normalize combined page hints, but first enforce stricter generation rules so the answer remains traceable.

3. Fix ingest coverage.
   Run a controlled incremental ingest to backfill the 210 not-yet-processed disk documents and retry the 87 zero-chunk suspects. Watch the ingest log for files that still produce zero chunks.

4. Improve local parsing instead of paying for LlamaParse.
   Focus on local parser quality audits, recursive ingest coverage, and targeted handling for PDFs that currently produce zero chunks. Reconsider LlamaParse only if a future free/cheap quota is available and parse audit shows clear quality gains.
