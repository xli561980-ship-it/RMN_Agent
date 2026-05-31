# RAG Evaluation Framework

## 为什么做

RMN Agent 的核心风险不是“答不上来”，而是论文证据、SOP 约束和引用线索混淆。评估框架把 retrieval、generation 与可选 RAGAS 拆开，便于比较不同检索、切分、embedding 和 reranker 配置。

## 如何运行

```bash
make eval-retrieval
make eval-generation
make eval-ragas
make eval-all
```

也可以直接运行：

```bash
python eval/run_retrieval_eval.py --questions eval/golden_questions.jsonl --k 5
```

## 输出文件

报告写入 `eval/reports/`：

- `retrieval_eval_<timestamp>.json/.md`
- `generation_eval_<timestamp>.json/.md`
- `ragas_eval_<timestamp>.json/.md`
- `rag_eval_summary_<timestamp>.md`

## 指标解释

- `route_accuracy`：query analyzer 的 `intent` 是否符合 gold route。
- `answer_mode_accuracy`：`answer_mode` 是否符合预期回答模式。
- `doc_type_accuracy`：召回 chunk 的 `doc_type` 是否落在预期类型内。
- `recall@k`、`precision@k`、`mrr`、`ndcg@k`：基于 gold source / evidence 的简化检索指标。
- `source_coverage`：gold sources 中有多少被召回。
- `sop_boundary_accuracy`：SOP / 操作型问题是否召回 SOP。
- `paper_to_sop_confusion_rate`：论文问题混入 SOP 或 SOP 问题混入论文的比例。

## 当前限制

仓库不包含真实客户语料，默认 gold 文件是模板示例。RAGAS 为可选依赖；没有 `ragas` 或 reference answer 时不会阻塞其他评估。

## 如何改进系统

先看失败案例列表：如果 route 错，优先改 `query_analyzer.py`；如果 doc_type 错，优先查 ingest metadata 和 reranker；如果 gold source 找不到，先确认本地 Chroma 是否已经用同一 embedding 配置重建。
