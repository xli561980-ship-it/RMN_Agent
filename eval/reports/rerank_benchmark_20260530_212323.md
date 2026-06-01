# Reranker Benchmark

## Preflight Warnings

- 未发现真实 paper/SOP 文件：data/papers 与 data/manuals 目前没有 PDF/DOCX。
- 未发现 corpus_manifest.json；看起来还没有完成可复现入库。
- 未发现默认 chroma_db；benchmark 指标可能只是空库/未入库状态。

| reranker | recall@5 | precision@5 | mrr | ndcg@5 | sop_boundary | confusion | failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | sop_litesizer_basic, paper_protocol_microgel, hybrid_replicate_safety, paper_compare, missing_evidence |
| rule | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | sop_litesizer_basic, paper_protocol_microgel, hybrid_replicate_safety, paper_compare, missing_evidence |
| bge | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | sop_litesizer_basic, paper_protocol_microgel, hybrid_replicate_safety, paper_compare, missing_evidence |

## 观察重点
- `rule` 是否降低 paper/SOP 混淆。
- `bge` 或 cross-encoder 是否提升 MRR。
- rerank 后是否牺牲 hybrid doc_type 平衡。
