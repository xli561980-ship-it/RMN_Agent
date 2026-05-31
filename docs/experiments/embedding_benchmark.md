# Embedding Model Benchmark

## 为什么做

RMN Agent 常见问题是中文提问检索英文论文，或 SOP 手册术语与用户自然语言不完全一致。embedding provider 会直接影响跨语言召回、参数类问题的 MRR 和 SOP 边界。

## 如何运行

默认不会重建向量库：

```bash
make bench-embedding
```

如需逐个 provider 重建：

```bash
python eval/run_embedding_benchmark.py --providers google,bge_m3,e5 --k 5 --rebuild
```

## 输出文件

结果写入 `eval/reports/embedding_benchmark_<timestamp>.json/.md`。

## 支持的 provider / 模型

- `google` / `gemini`：使用 `GOOGLE_EMBEDDING_MODEL`。
- `openai`：使用 `OPENAI_EMBEDDING_MODEL`。
- `zhipu`：通过 OpenAI-compatible client。
- `huggingface`：使用 `HF_EMBEDDING_MODEL`。
- `bge_m3`：HuggingFace alias，默认 `BAAI/bge-m3`。
- `e5`：HuggingFace alias，默认 `intfloat/multilingual-e5-base`。

缺少 API Key 或依赖时，benchmark 会跳过对应 provider 并在报告里记录原因。

## 指标解释

重点比较 `recall@5`、`precision@5`、`mrr`、`ndcg@5`、`doc_type_accuracy`、`avg_retrieval_latency_ms` 和 `index_build_time_sec`。

## 当前限制

本地 HuggingFace 模型首次下载较慢，脚本不会默认下载大型模型，除非用户选择对应 provider 并允许重建。

## 如何改进系统

如果 Google 表现稳定但成本敏感，可比较 `bge_m3` 与 `e5`；如果跨语言 MRR 偏低，应增加中英双语 query rewrite 或领域词表前缀。
