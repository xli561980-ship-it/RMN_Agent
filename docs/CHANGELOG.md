# RMN Agent 变更日志

本文档记录每一轮主要调整、动机与可量化效果。实验原始报告见 [`eval/reports/`](../eval/reports/)；方法论说明见 [`docs/experiments/`](experiments/)。

---

## 2026-05-31 — Query anchoring + gold label 修正（当前 HEAD）

### 做了什么

| 模块 | 调整 |
|------|------|
| `paper_anchor.py` | 新增论文实体/指示词提取、corpus 软匹配、`enrich_analysis_with_paper_anchor()` |
| `query_analyzer.py` | 集成 paper anchor；「这篇论文/参考论文」+ UI anchor 时强制范围 |
| `rag_core.py` | `_retrieve_paper_with_anchor()`、RRF 合并、HYBRID 候选池 ≥20、`retrieval_diagnostics` |
| `eval/golden_questions.jsonl` | `missing_evidence` 采用 **Scheme A**：保留 corpus-level 问题，扩展 4 篇 gold sources |
| `eval/gold_evidence.jsonl` | 新增 Wang / İyisan×2 / Özkale 四条 Introduction 级 gold evidence |
| `eval/run_retrieval_eval.py` | recall@5/10/20、per-evidence `gold_hit_rank`、anchor 诊断 |
| `eval/run_query_anchor_ablation.py` | `no_anchor` / `analyzer_anchor` / `forced_gold_source_anchor`（仅诊断） |
| `eval/run_google_embedding_failure_analysis.py` | top-20 深潜 + 根因标签；自动读取最新 retrieval eval |
| `tests/test_paper_anchor.py` | 8 项单元测试（Wang 匹配、UI anchor、corpus-level 不误锚定等） |
| `.env.example` | 默认 `RERANKER_PROVIDER=none`；`ANCHORED_PAPER_RETRIEVAL=true` 等 |

### 为什么

1. **Rule reranker 无法解决 recall@5**：`hybrid_replicate_safety` 的 gold 根本未进候选池，主因是 query 未锚定到 Wang 2025。
2. **`missing_evidence` gold label 过窄**：问题问「这些文献是否证明所有干细胞类型」，但 gold 只有 Wang Introduction → 检索合理排 İyisan/Özkale 却被判 miss。

### 效果（Google embedding，`gemini-embedding-001`，362 文件索引，5 题 gold set）

| 指标 / 问题 | 调整前（~0830） | 调整后（084151） |
|-------------|-----------------|------------------|
| **overall recall@5** | ~0.60 | **1.0** |
| `hybrid_replicate_safety` recall@5 | 0.0（no anchor） | **1.0**（analyzer anchor，Wang rank 1） |
| `missing_evidence` recall@5 | 0.0 | **1.0**（4 条 gold 均在 rank ≤4） |
| Failure analysis recall miss @5 | 2 题 | **0 题** |

关键报告：

- [`eval/reports/retrieval_eval_20260531_084151.md`](../eval/reports/retrieval_eval_20260531_084151.md)
- [`eval/reports/query_anchor_ablation_20260531_083412.md`](../eval/reports/query_anchor_ablation_20260531_083412.md)
- [`eval/reports/google_embedding_failure_analysis.md`](../eval/reports/google_embedding_failure_analysis.md)

### 设计决策

- **默认不用 rule reranker**（`RERANKER_PROVIDER=none`）
- **不自动 force gold source anchor**（仅 ablation 诊断）
- **`missing_evidence` 采用 Scheme A**（corpus-level）；Scheme B 为单篇 Wang 2025 改写，见 failure analysis manual review

---

## 2026-05-31 — Rule reranker 与 ranking optimization 实验

### 做了什么

- 新增 `rerankers.py`：双路 rule rerank、RRF + rule_score 融合
- `rag_core.py`：HYBRID 最小 paper/SOP chunk 保留；泛化问题 intro/discussion boost
- `eval/run_ranking_optimization_report.py`：before/after 对比报告

### 效果

| 指标 | before | after rule rerank | delta |
|------|--------|-------------------|-------|
| recall@5 | 0.6 | 0.6 | 0 |
| recall@10 | 0.6 | 0.8 | +0.2 |
| mrr | 0.513 | 0.487 | -0.027 |
| `missing_evidence` gold rank | 15 | 10 | ↑5，仍未进 top-5 |

结论：**rerank 只能微调排序，无法补候选池 recall** → 转向 query anchoring。

报告：[`eval/reports/ranking_optimization_20260531_082702.md`](../eval/reports/ranking_optimization_20260531_082702.md)

---

## 2026-05-31 — Google embedding 全量索引 + failure analysis

### 做了什么

- 用 `EMBEDDING_PROVIDER=google` 重建 Chroma：**362 文件，14,731 chunks**
- 新增 `eval/run_google_embedding_failure_analysis.py`
- 首次 failure analysis 定位两大 miss：`hybrid_replicate_safety`（recall）、`missing_evidence`（rank 16）

### 效果（初版 eval，`retrieval_eval_20260531_010709`）

| id | recall@5 |
|----|----------|
| sop_litesizer_basic | 1.0 |
| paper_protocol_microgel | 0.4 |
| hybrid_replicate_safety | **0.0** |
| paper_compare | 0.8 |
| missing_evidence | **0.0** |

---

## 2026-05-30 — RAG 实验框架与 benchmark 基础设施

### 做了什么

| 新增 | 说明 |
|------|------|
| `chunking/` | fixed / header_aware / parent_child / semantic_placeholder 策略 |
| `eval/run_retrieval_eval.py` | 结构化 retrieval 评估 |
| `eval/run_generation_eval.py` | 完整 RAG 生成 + citation 检查 |
| `eval/run_ragas_eval.py` | 可选 RAGAS |
| `eval/run_chunking_benchmark.py` | 切分策略对比 |
| `eval/run_embedding_benchmark.py` | google / bge_m3 / e5 等 provider 对比 |
| `eval/run_rerank_benchmark.py` | none / rule / bge reranker 对比 |
| `eval/run_all_eval.py` | 一键跑全套 |
| `eval/gold_evidence.jsonl` | span 级 gold evidence |
| `eval/metrics.py`, `eval/eval_utils.py` | 共享指标与工具 |
| `docs/experiments/*.md` | 各实验说明 |
| `tests/test_*.py` | chunking、embedding、eval metrics、rerankers 单元测试 |

### ingest 增强

- 多 embedding provider 支持（Google / HuggingFace bge-m3 / e5）
- `corpus_manifest.json` / `processed_files.json` 追踪入库状态
- 论文 embedding prefix、header-aware chunk metadata

### Makefile 新 target

`eval-retrieval`, `eval-generation`, `eval-ragas`, `eval-all`, `bench-chunking`, `bench-embedding`, `bench-rerank`

### 效果

建立了可重复的实验流水线；具体 benchmark 数值见 `eval/reports/chunking_benchmark_*`、`embedding_benchmark_*`、`rerank_benchmark_*`。

---

## 2026-05-29 — 文档与作品集定位

### 做了什么

- 完善中文 README、架构说明、演示脚本、presales 定位文档
- Git commits: `Initial project import` → `Polish Chinese presales` → `Refine Chinese RMN Agent documentation`

### 效果

项目从「可运行原型」升级为「可讲解、可演示、可写进作品集」的文档体系。

---

## 版本对照（Git tags 建议）

| 阶段 | 建议 tag | 核心能力 |
|------|----------|----------|
| 初始导入 | `v0.1.0` | Streamlit + 双路 RAG + citation validator |
| 文档完善 | `v0.2.0` | 中文 README / architecture / demo |
| 实验框架 | `v0.3.0` | eval + chunking + embedding/rerank benchmark |
| Query anchoring | **`v0.4.0`** | paper_anchor + gold 修正 + recall@5 1.0 |

---

## 如何复现当前最佳结果

```bash
cp .env.example .env   # 填写 GOOGLE_API_KEY
make ingest            # 或 REBUILD_CHROMA=1 make rebuild
make test              # 46 tests
EMBEDDING_PROVIDER=google RERANKER_PROVIDER=none make eval-retrieval
.venv/bin/python eval/run_google_embedding_failure_analysis.py
.venv/bin/python eval/run_query_anchor_ablation.py --heuristic-only
```

预期：5 题 gold set 上 **recall@5 = 1.0**（需本地 Chroma 与仓库 gold 文件一致）。
