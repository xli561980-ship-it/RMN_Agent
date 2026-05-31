# Embedding Model Benchmark

## 为什么做

RMN Agent 常见问题是中文提问检索英文论文，或 SOP 手册术语与用户自然语言不完全一致。embedding provider 会直接影响跨语言召回、参数类问题的 MRR 和 SOP 边界。

## 如何运行

默认（仅 Google API，不下载 HuggingFace 模型）：

```bash
make bench-embedding
```

离线 / 无 API 对照：

```bash
make bench-embedding-local    # local_hash，无需外部 API
```

HuggingFace 模型（需下载，可能较慢或受网络限制）：

```bash
make bench-embedding-hf       # bge_m3, e5
```

如需逐个 provider 重建索引：

```bash
python eval/run_embedding_benchmark.py --providers google --k 5 --rebuild
python eval/run_embedding_benchmark.py --providers bge_m3,e5 --k 5 --rebuild
```

## 输出文件

结果写入 `eval/reports/embedding_benchmark_<timestamp>.json/.md`。

## 支持的 provider / 模型

- `google` / `gemini`：使用 `GOOGLE_EMBEDDING_MODEL`（**默认 benchmark**）。
- `local_hash`：离线 hash embedding，用于无 API  smoke / 对照。
- `openai`：使用 `OPENAI_EMBEDDING_MODEL`。
- `zhipu`：通过 OpenAI-compatible client。
- `huggingface`：使用 `HF_EMBEDDING_MODEL`。
- `bge_m3`：HuggingFace alias，默认 `BAAI/bge-m3`（`make bench-embedding-hf`）。
- `e5`：HuggingFace alias，默认 `intfloat/multilingual-e5-base`（`make bench-embedding-hf`）。

缺少 API Key 或依赖时，benchmark 会跳过对应 provider 并在报告里记录原因。

## 与当前扩展 eval 的关系

当前生产路径与扩展 golden eval 使用 **Google `gemini-embedding-001`**。31 题扩展集 retrieval 结果（本地语料，**非生产性能**）：

| 指标 | 值 |
| --- | --- |
| recall@5 | 0.936 |
| recall@10 | 0.936 |
| recall@20 | 0.968 |
| MRR | 0.844 |

Failure analysis 表明：低 recall@5 往往来自 anchoring / ranking / gold label，而非 embedding 模型本身。最弱类型为 **paper-only hard negatives**。

## 指标解释

重点比较 `recall@5`、`precision@5`、`mrr`、`ndcg@5`、`doc_type_accuracy`、`avg_retrieval_latency_ms` 和 `index_build_time_sec`。

## 当前限制

本地 HuggingFace 模型首次下载较慢；**Makefile 默认不触发 HF 下载**。扩展 eval 指标仅反映当前本地 corpus 与 gold 标注，不代表线上性能。

## 如何改进系统

若 Google 表现稳定但成本敏感，可比较 `bge_m3` 与 `e5`（`make bench-embedding-hf`）；若 paper-only hard negatives 持续失败，优先 paper title/entity query expansion 与 section-aware retrieval，而非仅换 embedding。
