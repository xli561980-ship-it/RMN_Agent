# Chunking Benchmark

## Preflight Warnings

- 未发现 corpus_manifest.json；看起来还没有完成可复现入库。

| strategy | total_chunks | avg_chunk_chars | paper_chunks | sop_chunks | recall@5 | mrr | doc_type_accuracy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | 530 | 605.7 | 228 | 302 | 0.88 | 1.0 | 1.0 | 未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。 |
| header_aware | 530 | 605.7 | 228 | 302 | 0.88 | 1.0 | 1.0 | 未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。 |
| parent_child | 530 | 605.7 | 228 | 302 | 0.88 | 1.0 | 1.0 | 未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。 |
