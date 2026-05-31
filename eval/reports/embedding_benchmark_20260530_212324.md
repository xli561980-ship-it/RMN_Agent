# Embedding Benchmark

## Preflight Warnings

- 未发现真实 paper/SOP 文件：data/papers 与 data/manuals 目前没有 PDF/DOCX。
- 未发现 corpus_manifest.json；看起来还没有完成可复现入库。
- 未发现默认 chroma_db；benchmark 指标可能只是空库/未入库状态。

| provider | model | recall@5 | precision@5 | mrr | ndcg@5 | doc_type_accuracy | latency_ms | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| google | gemini-embedding-001 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  | provider skipped: missing GOOGLE_API_KEY/GEMINI_API_KEY |
| bge_m3 | BAAI/bge-m3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 未传入 --rebuild，未重建索引；指标反映当前 Chroma。 |
| e5 | intfloat/multilingual-e5-base | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 未传入 --rebuild，未重建索引；指标反映当前 Chroma。 |

中文问题检索英文论文时，请重点观察 recall/MRR 与失败问题列表；本报告不会自动解释语义失败原因。
