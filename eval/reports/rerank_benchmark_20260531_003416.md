# Reranker Benchmark

| reranker | recall@5 | precision@5 | mrr | ndcg@5 | sop_boundary | confusion | failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | 0.44 | 0.44 | 0.6 | 0.977 | 0.8 | 0.08 | paper_protocol_microgel, hybrid_replicate_safety, missing_evidence |
| rule | 0.48 | 0.48 | 0.467 | 1.0 | 1.0 | 0.0 | paper_protocol_microgel, hybrid_replicate_safety, missing_evidence |
| bge | 0.48 | 0.48 | 0.6 | 1.0 | 1.0 | 0.0 | paper_protocol_microgel, hybrid_replicate_safety, missing_evidence |

## 观察重点
- `rule` 是否降低 paper/SOP 混淆。
- `bge` 或 cross-encoder 是否提升 MRR。
- rerank 后是否牺牲 hybrid doc_type 平衡。
