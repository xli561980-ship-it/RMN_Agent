# Google Embedding Failure Analysis

- Source eval: `retrieval_eval_20260531_084151.json`
- Embedding provider: `google` / `gemini-embedding-001`
- Eval @k: `5`; deep dive @k: `20`
- Index note: `processed_files.json` has 362 files indexed (expect ~363 for full Google corpus).

## Summary

- Total questions: **5**
- Recall miss questions (@5, gold-evidence level): **0**

### Original eval snapshot (@k=5 from source JSON)

| id | recall@5 | gold_hit | missing_gold_sources |
| --- | --- | --- | --- |
| sop_litesizer_basic | 1.0 | True | 0 |
| paper_protocol_microgel | 1.0 | True | 0 |
| hybrid_replicate_safety | 1.0 | True | 1 |
| paper_compare | 1.0 | True | 1 |
| missing_evidence | 1.0 | True | 0 |

> Deep-dive re-runs use the restored Google index (362 files). Query routing may vary slightly between runs because `analyze_query` uses an LLM.

### Issue type (missed gold evidence items)

_No missed evidence items._

### Root-cause tags (missed gold evidence items; multi-label)

_No cause tags._

## Per-question Analysis

_No recall misses at eval k; all gold evidence found in top-5._

## Manual review: `missing_evidence`

- **Scheme A (applied):** corpus-level generalization question; gold evidence spans Wang 2025, İyisan 2024/2025, and Özkale 2024 microgel/stem-cell papers.
- Expected answer: evidence does **not** prove efficacy across **all** stem cell types; each paper covers specific cell types or conditions.
- Do **not** force `paper_scope_source` anchor in the default pipeline; `forced_gold_source_anchor` remains eval ablation only.
- Alternative **Scheme B:** rewrite to “Wang 2025 这篇论文是否证明…” if testing single-paper reasoning.

## Method

1. Reload questions from `eval/golden_questions.jsonl` and gold spans from `eval/gold_evidence.jsonl`.
2. Treat a question as recall miss when any gold evidence item is absent from top-5.
3. Re-run `fusion_prepare(..., k=20)` and inspect top-20 chunks.
4. If gold evidence appears in top-20 but not top-5 → **ranking_issue**; otherwise **recall_issue**.
5. Cause tags are heuristic and may co-occur on one missed evidence item.
