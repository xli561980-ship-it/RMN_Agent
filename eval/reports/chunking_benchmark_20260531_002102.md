# Chunking Benchmark

| strategy | total_chunks | avg_chunk_chars | paper_chunks | sop_chunks | recall@5 | mrr | doc_type_accuracy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | 13505 | 563.8 | 2272 | 11233 | 0.44 | 0.5 | 0.92 | rebuild ok |
| header_aware | 13507 | 563.8 | 2274 | 11233 | 0.4 | 0.5 | 0.92 | rebuild ok |
| parent_child | 17253 | 510.5 | 4796 | 12457 | 0.44 | 0.6 | 0.92 | rebuild ok |
