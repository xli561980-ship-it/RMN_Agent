# Chunking Benchmark

## Preflight Warnings

- 未发现真实 paper/SOP 文件：data/papers 与 data/manuals 目前没有 PDF/DOCX。
- 未发现 corpus_manifest.json；看起来还没有完成可复现入库。
- 未发现默认 chroma_db；benchmark 指标可能只是空库/未入库状态。

| strategy | total_chunks | avg_chunk_chars | paper_chunks | sop_chunks | recall@5 | mrr | doc_type_accuracy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。 |
| header_aware | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。 |
| parent_child | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。 |
