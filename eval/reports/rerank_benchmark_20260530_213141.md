# Reranker Benchmark

## Preflight Warnings

- 未发现 corpus_manifest.json；看起来还没有完成可复现入库。

| reranker | recall@5 | precision@5 | mrr | ndcg@5 | sop_boundary | confusion | failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | 0.88 | 0.88 | 1.0 | 1.0 | 1.0 | 0.0 |  |
| rule | 0.8 | 0.8 | 1.0 | 1.0 | 1.0 | 0.0 |  |
| bge | 0.88 | 0.88 | 1.0 | 1.0 | 0.8 | 0.0 |  |

## 观察重点
- `rule` 是否降低 paper/SOP 混淆。
- `bge` 或 cross-encoder 是否提升 MRR。
- rerank 后是否牺牲 hybrid doc_type 平衡。
