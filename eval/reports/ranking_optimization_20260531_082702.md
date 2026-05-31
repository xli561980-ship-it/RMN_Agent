# Ranking Optimization Report

## Changes applied

- Dual-path rule reranker with RRF + rule_score fusion
- HYBRID minimum paper/SOP chunk reservation (`HYBRID_MIN_PAPER_CHUNKS`, `HYBRID_MIN_SOP_CHUNKS`)
- Safety/SOP/manual/protocol boosts and generic microgel demotion
- Introduction/discussion/limitations boost for generalization questions
- Retrieval eval now reports recall@5/10/20 and per-evidence `gold_hit_rank`

## Metric comparison

| metric | before_rule_rerank | after_rule_rerank | delta |
| --- | --- | --- | --- |
| recall@5 | 0.6 | 0.6 | +0.0000 |
| recall@10 | 0.6 | 0.8 | +0.2000 |
| recall@20 | 0.8 | 0.8 | +0.0000 |
| mrr | 0.5133 | 0.4867 | -0.0267 |
| ndcg@5 | 1.0 | 1.0 | +0.0000 |
| doc_type_accuracy | 1.0 | 1.0 | +0.0000 |
| paper_to_sop_confusion_rate | 0.0 | 0.0 | +0.0000 |

## Focus failure questions: gold_hit_rank

### `hybrid_replicate_safety`
| section | before_rule_rerank rank | after_rule_rerank rank | delta |
| --- | --- | --- | --- |
| Microfluidic fabrication | None | None | n/a |
| Safety Instructions | None | None | n/a |

### `missing_evidence`
| section | before_rule_rerank rank | after_rule_rerank rank | delta |
| --- | --- | --- | --- |
| Introduction | 15 | 10 | ↑5 |

## Manual review: `missing_evidence`

- Failure analysis flagged possible **`gold_label_mismatch`** for this question.
- The current gold evidence points to Wang 2025 Introduction scope (MSCs only), while retrieval often ranks other microgel/stem-cell papers higher.
- **Do not auto-edit gold labels.** Consider whether eval should:
  1. Add gold evidence rows for İyisan / Özkale papers when the question refers to “这些文献”, or
  2. Rewrite the question to explicitly anchor Wang 2025 / a single paper scope.

## Artifacts

- Before eval: `/Users/xds_mac/Library/CloudStorage/OneDrive-TUM/cursorgitrmn/RMN_Agent/eval/reports/retrieval_eval_20260531_082529.json`
- After eval: `/Users/xds_mac/Library/CloudStorage/OneDrive-TUM/cursorgitrmn/RMN_Agent/eval/reports/retrieval_eval_20260531_082609.json`
- Updated failure analysis: `/Users/xds_mac/Library/CloudStorage/OneDrive-TUM/cursorgitrmn/RMN_Agent/eval/reports/google_embedding_failure_analysis.md`
