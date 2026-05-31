# Reranker Benchmark

## 为什么做

基础向量召回容易把论文方法和 SOP 操作片段混在一起。reranker 的目标是在不改变 query analyzer 的前提下，对候选 chunk 排序，让最终上下文更符合问题路线。

## 默认策略说明

**`rule` reranker 不是当前默认 pipeline。** 2026-05 的 ranking optimization 显示：

- `rule` 提升了 `recall@10`，但**没有提升 `recall@5`**
- **MRR 略降**
- `missing_evidence` 的 gold rank 仅从 15→10，仍未进 top-5
- `hybrid_replicate_safety` 在 top-20 仍未命中 gold → 主因是 **query anchoring / candidate pool recall**，不是 rerank 权重

因此默认配置为 `RERANKER_PROVIDER=none`。`RERANK_RULE_WEIGHT=0.35` 等参数保留，仅供实验对比。

当前优先改进：**query anchoring**（`paper_scope_*` + anchored retrieval）与 **HYBRID 候选池扩大**（paper/SOP topN ≥ 20）。

## 如何运行

```bash
make bench-rerank
```

或：

```bash
RERANKER_PROVIDER=rule python eval/run_rerank_benchmark.py --rerankers none,rule,bge --k 5
```

Query anchoring 对比：

```bash
python eval/run_query_anchor_ablation.py --heuristic-only
```

## 输出文件

- Rerank：`eval/reports/rerank_benchmark_<timestamp>.json/.md`
- Anchor ablation：`eval/reports/query_anchor_ablation_<timestamp>.md`

## 支持模式

- `none`：默认，不改变检索顺序。
- `rule`：本项目特定规则 rerank，不依赖外部 API（实验用）。
- `cross_encoder`：可选本地 cross-encoder，缺依赖或模型不可用时 fallback。
- `bge`：可选 BGE reranker，默认 `BAAI/bge-reranker-base`。
- `cohere_optional`：预留 Cohere API，缺 key 时跳过。
- `llm_optional`：预留 LLM rerank，默认关闭。

## 指标解释

重点看 `mrr` 是否提升、`paper_to_sop_confusion_rate` 是否下降、`sop_boundary_accuracy` 是否保持，以及 failure cases 是否新增。

同时查看 retrieval eval 中的：

- `candidate_pool_size`
- `anchored_source_detected` / `anchored_source_hit_count`
- `gold_hit_rank_before_rerank` / `gold_hit_rank_after_rerank`
- `whether_gold_was_in_candidate_pool`

## 当前限制

`rule` 是轻量启发式，适合解释和 baseline；`cross_encoder` / `bge` 依赖本地模型下载和推理资源。当前 LLM rerank 只是预留，不默认启用。

## 如何改进系统

若 gold 不在 candidate pool：优先 `ANCHORED_PAPER_RETRIEVAL`、analyzer `paper_scope_*`、UI paper anchor。

若 gold 在 pool 但 rank 低：再考虑 `rule` / cross-encoder rerank，或调整 `HYBRID_MIN_PAPER_CHUNKS` / `HYBRID_MIN_SOP_CHUNKS`。
