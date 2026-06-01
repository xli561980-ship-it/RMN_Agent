# Google Embedding Retrieval Failure Analysis

## 1. 实验背景

项目在 Google embedding（`gemini-embedding-001`）路径上观察到 **初始 retrieval eval 的 recall@5 偏低**（约 0.44–0.60，视索引恢复阶段而定）。这不能直接等同于「Google embedding 模型差」——在 RAG 系统中，低 recall@5 可能来自：

- **Recall issue**：gold evidence 不在 top-20 候选池；
- **Ranking issue**：gold evidence 在 top-20 中，但未进入 top-5；
- **Query anchoring issue**：问题语义需要锁定某篇论文，但 analyzer / UI 未给出 `paper_scope_source`；
- **Gold label mismatch**：问题语义是 corpus-level，但 gold evidence 过窄；
- **Candidate pool construction**：HYBRID 路径 paper/SOP quota 或 topN 过小。

因此本轮工作的目标不是继续围绕 5 题刷分，而是：**用 failure analysis 定位根因、修正评估标签、修复 anchoring，并扩展更真实的 golden questions**。

## 2. 初始现象

基于 `eval/reports/` 中阶段性 retrieval eval（Google index，5 题小型集）：

| 阶段 | 报告 | recall@5 | recall@10 | 备注 |
| --- | --- | --- | --- | --- |
| 早期（索引/路由未稳定） | `retrieval_eval_20260530_231050.json` | **0.44** | — | 多题 gold 未进 top-5 |
| Anchoring 前（rule rerank 实验前） | `retrieval_eval_20260531_082529.json` | **0.60** | 0.60 | `hybrid_replicate_safety`、`missing_evidence` 仍失败 |
| Query anchor + gold 修正后 | `retrieval_eval_20260531_084151.json` | **1.00** | 1.00 | 5 题小型集调通 |

典型失败形态：**部分问题 top-5 完全未命中 gold evidence**，但 failure analysis deep dive（top-20）显示并非所有 miss 都是 embedding 完全召回失败。

## 3. Failure Analysis 发现

对 top-5 miss 的问题执行 **top-20 deep dive**（`eval/run_google_embedding_failure_analysis.py`）：

### 3.1 Ranking issue

**定义**：gold evidence 出现在 top-20，但未进入 top-5。

- 多个 microgel 相关论文在 corpus 中语义接近，Google embedding 能把正确 source 召回到 top-20，但 **MRR / top-5 排序** 被相近论文、SOP 或错误 section chunk 挤占。
- `missing_evidence` 早期典型：**Wang 2025 Introduction 在 rank≈15**，İyisan / Özkale 论文排在更前——检索行为合理，但 gold 标签过窄导致「假失败」。

### 3.2 Recall issue

**定义**：gold evidence 不在 top-20。

- `hybrid_replicate_safety` 早期失败：**paper gold 不在 candidate pool**（top-20 仍 miss），主因是「参考论文里的 microgel」过泛、未 anchor 到 Wang 2025，以及 HYBRID 候选池偏小。
- 部分 SOP 题为 cross-language（中文问、英文手册），gold 在 pool 内但 rank 低，极端情况下表现为 recall miss。

### 3.3 Gold label mismatch

**定义**：问题语义与 gold evidence 标注范围不一致。

- `missing_evidence` 原 gold 仅标 **Wang 2025 Introduction**；问题是 **corpus-level 泛化**（「所有干细胞类型」）。检索返回多篇 microgel/stem-cell 论文是合理行为，原标签却判定失败。
- Failure analysis 报告标记 **`gold_label_mismatch`**，建议修正 gold 或改写问题，而不是强行把检索锁到单篇论文。

## 4. Rule Reranker 实验

在 `eval/run_rerank_benchmark.py` / `ranking_optimization_20260531_082702.md` 中对比 `RERANKER_PROVIDER=none` vs `rule`：

| 指标 | before (none) | after (rule) | 变化 |
| --- | --- | --- | --- |
| recall@5 | 0.60 | 0.60 | **无提升** |
| recall@10 | 0.60 | 0.80 | +0.20 |
| mrr | 0.513 | 0.487 | **略降** |

Rule reranker 机制包括：

- safety / SOP / protocol 提权；
- 泛化 microgel 词降权；
- generalization 问题的 intro/discussion 提权。

**结论**：Rule reranker 有 **诊断与 ablation 价值**，能解释「候选池内有 gold 但 rank 低」；但 **不是当前最佳默认策略**——它没有提升 recall@5，且 MRR 略降。默认保持 `RERANKER_PROVIDER=none`，`RERANK_RULE_WEIGHT=0.35` 等参数仅用于 benchmark。

## 5. Query Anchoring 修复

新增/强化机制（`paper_anchor.py` + `rag_core.py` anchored retrieval）：

| 机制 | 说明 |
| --- | --- |
| Strong paper anchor signal | `Wang 2025` / `Wang` / `Photothermally Powered` / `mechanically regulate` 等强信号 |
| Corpus soft match | 多候选 microgel 论文 soft match，不强制单篇（corpus-level 问题） |
| UI anchor 强制 | Streamlit 选定论文时，「这篇论文 / 参考论文里」等指代跟随 UI |
| Anchored retrieval | 对 `paper_scope_source` 追加 anchored search，RRF 合并 |
| HYBRID candidate pool | `HYBRID_PAPER_CANDIDATE_TOPN=20`（≥20） |

### hybrid_replicate_safety 案例

- **原问题**：「如果我要参考论文里的 microgel 参数做一次实验，需要同时注意哪些本实验室 SOP 或安全限制？」
- **原失败原因**：「参考论文里的 microgel」过泛；corpus 有多篇 microgel paper；未 anchor → paper gold 不在 pool。
- **修复后**：deictic + microgel + title hint → **Wang 2025**；anchored retrieval 生效。
- **结果**：query anchor ablation 与 full eval 中 `hybrid_replicate_safety` **recall@5 = 1.0**。

**约束（默认 pipeline）**：

- `forced_gold_source_anchor` **仅**在 `eval/run_query_anchor_ablation.py` 中用于诊断；
- **corpus-level 问题不应自动 source anchor**；
- 强 anchor 仅在强信号或 UI anchor 时启用。

## 6. Gold Evidence 修正

### missing_evidence 案例

- **原问题**：「这些文献是否证明了该 microgel 方法在所有干细胞类型中都有效？」
- **问题性质**：corpus-level 泛化边界。
- **原 gold**：仅 Wang 2025 Introduction → **过窄**；İyisan、Özkale 等被排在前面其实合理。

**采用方案 A（已应用）**：

- 保留 corpus-level 问题；
- 扩展 gold evidence 至 4 篇：Wang 2025、İyisan 2024/2025、Özkale 2024；
- `reference_answer` 强调：**不能证明对所有干细胞类型均有效**；
- 修正后 `missing_evidence` **recall@5 = 1.0**（小型集），4 条 gold 可在 top-4 命中。

**未采用方案 B**：

- 若改写为「Wang 2025 这篇论文是否证明……」，可测单篇推理，但 **不适合** 测试 corpus-level 泛化边界。

## 7. 当前结论

1. **主要瓶颈不是 Google embedding 本身**——多数失败是 ranking、anchoring、HYBRID 候选池或 **gold label design**。
2. 小型 5 题 eval 已被调通（recall@5=1.0），**不应继续围绕 5 题过拟合**（调 rule weight、改 anchor 刷分）。
3. 默认配置保持：
   - `RERANKER_PROVIDER=none`（rule reranker 仅 ablation）
   - `ANCHORED_PAPER_RETRIEVAL=true`
   - `forced_gold_source_anchor` 仅 eval 诊断；corpus-level 问题不自动锚定单篇论文
4. 评估体系已扩展为 **31 questions / 69 gold evidence**。

### 扩展集 retrieval 结果（本地 eval，非生产性能）

基于 `retrieval_eval_20260531_090008` / `expanded_eval_summary_20260531_091656`：

| 指标 | 值 |
| --- | --- |
| recall@5 | **0.936** |
| recall@10 | 0.936 |
| recall@20 | 0.968 |
| precision@5 | 0.761 |
| MRR | 0.844 |
| nDCG@5 | 0.996 |
| doc_type_accuracy | 0.987 |
| sop_boundary_accuracy | 0.968 |
| paper_to_sop_confusion_rate | 0.013 |

**最弱类型**：paper-only（recall@5≈0.6），典型 hard negatives 为 Özkale perspective、d2lc 被 Wang / 相近 microgel 论文挤占。后续：paper title/entity query expansion、section-aware retrieval、paper-only failure analysis；cross-encoder rerank 仅在 gold 已在 candidate pool 时评估。

## 8. 后续计划

- [x] 扩展 golden questions 至 **31 题 / 69 gold evidence**；
- [x] 增加 **gold evidence alignment check**（`make eval-gold-check`）；
- [ ] 持续增加 **hard negatives**（相近 microgel 论文、MSDS vs BA 手册、cross-language SOP）；
- [ ] 保留 recall@5/10/20、`gold_hit_rank`、failure analysis 作为固定报告项；
- [ ] **paper-only query expansion** 与 generation eval，而非回退到 5 题刷分或默认启用 rule reranker。

相关命令：

```bash
make eval-gold-check
make eval-retrieval
python eval/run_expanded_eval_summary.py
python eval/run_google_embedding_failure_analysis.py
```
