# Reranker Benchmark

## 为什么做

基础向量召回容易把论文方法和 SOP 操作片段混在一起。reranker 的目标是在不改变 query analyzer 的前提下，对候选 chunk 排序，让最终上下文更符合问题路线。

## 默认策略说明

**`rule` reranker 不是当前默认 pipeline，也不应作为生产默认策略。** 2026-05 的 ranking optimization 显示：

- `rule` 提升了 `recall@10`，但**没有提升 `recall@5`**
- **MRR 略降**
- 主因常是 **query anchoring / candidate pool recall**，而非 rerank 权重

因此默认配置为 **`RERANKER_PROVIDER=none`**。`RERANK_RULE_WEIGHT=0.35` 等参数保留，**仅供 benchmark / ablation 对照**。

**诊断边界**：

- `forced_gold_source_anchor` 只能在 `eval/run_query_anchor_ablation.py` 中使用；
- corpus-level 问题不应自动锚定到单篇 source；
- gold evidence 标签必须与问题语义一致（见 `make eval-gold-check`）。

当前生产默认优先：**anchored retrieval**（`ANCHORED_PAPER_RETRIEVAL=true`）与 **HYBRID 候选池 ≥20**。

## 如何运行

默认（不依赖 HuggingFace 下载）：

```bash
make bench-rerank          # none vs rule
make bench-rerank-hf       # BGE reranker（需本地模型）
```

或：

```bash
RERANKER_PROVIDER=rule python eval/run_rerank_benchmark.py --rerankers none,rule --k 5
python eval/run_rerank_benchmark.py --rerankers bge --k 5
```

Query anchoring 对比：

```bash
python eval/run_query_anchor_ablation.py --heuristic-only
```

## 输出文件

- Rerank：`eval/reports/rerank_benchmark_<timestamp>.json/.md`
- Anchor ablation：`eval/reports/query_anchor_ablation_<timestamp>.md`

## 支持模式

- `none`：**默认**，不改变检索顺序。
- `rule`：轻量启发式 rerank，**仅 ablation**；有诊断价值但不是默认最优。
- `cross_encoder`：可选本地 cross-encoder，缺依赖或模型不可用时 fallback。
- `bge`：可选 BGE reranker（`make bench-rerank-hf`），默认 `BAAI/bge-reranker-base`。
- `cohere_optional` / `llm_optional`：预留，默认关闭。

## 与当前扩展 eval 的关系

31 题扩展集 retrieval eval（`recall@5=0.936`）表明：**paper-only hard negatives** 仍是主要短板。cross-encoder rerank 仅建议在 gold 已在 candidate pool 时评估；不应为刷分默认启用 rule reranker。

## 指标解释

重点看 `mrr` 是否提升、`paper_to_sop_confusion_rate` 是否下降、`sop_boundary_accuracy` 是否保持，以及 failure cases 是否新增。

同时查看 retrieval eval 中的：

- `candidate_pool_size`
- `anchored_source_detected` / `anchored_source_hit_count`
- `gold_hit_rank_before_rerank` / `gold_hit_rank_after_rerank`
- `whether_gold_was_in_candidate_pool`

## 如何改进系统

若 gold 不在 candidate pool：优先 `ANCHORED_PAPER_RETRIEVAL`、analyzer `paper_scope_*`、UI paper anchor。

若 gold 在 pool 但 rank 低：再考虑 cross-encoder rerank 或 query expansion；**rule reranker 默认仍保持 none**。
