# Reranker Benchmark

| reranker | recall@5 | precision@5 | mrr | ndcg@5 | sop_boundary | confusion | failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | sop_litesizer_basic, paper_protocol_microgel, hybrid_replicate_safety, paper_compare, missing_evidence |
| rule | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | sop_litesizer_basic, paper_protocol_microgel, hybrid_replicate_safety, paper_compare, missing_evidence |
| bge | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | sop_litesizer_basic, paper_protocol_microgel, hybrid_replicate_safety, paper_compare, missing_evidence |

## 观察重点
- `rule` 是否降低 paper/SOP 混淆。
- `bge` 或 cross-encoder 是否提升 MRR。
- rerank 后是否牺牲 hybrid doc_type 平衡。
