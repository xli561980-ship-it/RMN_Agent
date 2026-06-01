# Lab Fusion RAG Agent

一个面向实验室知识工作的双路 RAG 原型：论文路径提供历史实验参数、方法和结果，SOP/手册路径提供规范流程与安全约束，最后生成带引用、可追溯的回答。

## 核心能力

- 双路检索：`paper` 与 `sop` 分开入库、分开检索，再融合生成。
- 意图路由：`SOP_ONLY`、`PAPER_ONLY`、`HYBRID`，并区分 `SCHOLARLY` / `OPERATIONAL` / `HYBRID` answer mode。
- 论文范围控制：支持 UI 锁定单篇论文、metadata filter、标题软匹配重排。
- 补充材料增强：正文命中后自动拉取同 `project_id` 的 supplementary information。
- 安全优先：涉及可执行实验时，SOP 是规范来源；论文参数不能单独替代本地 SOP。
- 引用约束：回答使用本轮检索片段中的 `citation_hint`，并可做生成后引用校验。
- 入库可追踪：增量入库记录文件指纹，并写入 `corpus_manifest.json` 记录 chunk/解析质量摘要。

## 架构

```mermaid
flowchart LR
    Q["User question"] --> A["Query analyzer"]
    A --> R1["Paper retriever"]
    A --> R2["SOP retriever"]
    R1 --> F["Fusion prompt"]
    R2 --> F
    F --> L["LLM generation"]
    L --> V["Citation validator"]
    V --> UI["Streamlit UI"]
```

## 本地启动

1. 准备环境变量：

```bash
cp .env.example .env
```

2. 安装依赖。推荐使用本项目本地虚拟环境；Python 版本建议 `3.10` 或 `3.11`。

```bash
pip install -r requirements.txt
pip install pytest
```

默认文档解析是本地路线：PDF 使用 `pdfplumber`，Word 使用 `python-docx`。不需要 LlamaParse，也不会消耗 LlamaParse credits。

3. 入库：

```bash
make ingest
```

全量重建：

```bash
make rebuild
```

4. 启动 UI：

```bash
make app
```

5. 测试与烟测：

```bash
make test
make smoke
```

## 调试与实验比较

本项目建议把每次调参当作一次可复现实验，而不是只看 Streamlit 当前回答。

1. 跑 baseline 并保存完整检索记录：

```bash
.venv/bin/python eval/run_experiment.py \
  --questions eval/golden_questions.jsonl \
  --config eval/configs/baseline.json
```

结果会写入 `eval/runs/<run_id>.jsonl`。每个 case 会记录 config、query analysis、检索到的 paper/SOP chunks、source、latency 和基础 metrics。
这些 JSONL 是本地调试产物，可能包含检索片段和生成答案，默认不提交到 GitHub。

2. 对比两次或多次运行：

```bash
.venv/bin/python eval/compare_runs.py \
  eval/runs/<baseline>.jsonl \
  eval/runs/<candidate>.jsonl \
  --out compare_baseline_candidate.md
```

报告会列出 route accuracy、required source hit、citation ok（若生成答案）、latency、自动 score，以及逐 case 的 improvements/regressions。自动 score 只用于筛选候选，不替代人工审查实验安全类答案。

3. 审计知识库覆盖：

```bash
.venv/bin/python eval/audit_corpus.py --out eval/reports/corpus_audit.json
```

该脚本对齐磁盘文档、`processed_files.json` 和 Chroma `source`，用于发现“磁盘有但未入库”“processed 记录存在但 Chroma 无 chunk”等问题。当前 ingest 会递归扫描 `data/papers/` 与 `data/manuals/`。

4. 审计本地解析质量（不写 Chroma）：

```bash
.venv/bin/python eval/parse_audit.py --parser fallback --limit 5 \
  --out eval/runs/parse_audit_local_sample.jsonl
```

5. 可选：比较 LlamaParse 与本地 fallback（默认不推荐，可能消耗付费 credits）：

```bash
.venv/bin/python eval/parse_audit.py --parser both --limit 5 \
  --out eval/runs/parse_audit_sample.jsonl
```

只有在安装 `llama-parse`、设置 `INGEST_USE_LLAMAPARSE=true` 并配置 `LLAMA_CLOUD_API_KEY` 时，入库才会尝试 LlamaParse。否则主线始终使用本地解析。

## 目录说明

- `app.py`：Streamlit 交互入口。
- `ingest.py`：PDF/Word 解析、元数据抽取、分层切分、Chroma 入库。
- `query_analyzer.py`：结构化 query 分析与 LLM 失败降级。
- `rag_core.py`：双路检索、标题软匹配、SI 增强、prompt bundle 准备。
- `fusion_prompts.py`：融合生成 system prompt 片段。
- `citation_validator.py`：生成后引用校验。
- `eval/`：RAG golden questions 与本地评估脚本。
- `tests/`：不依赖外部 API 的单元测试。

## 推荐 Demo 问题

- “这篇论文里 microgel 的制备步骤和关键参数是什么？”
- “如果我要复现实验，哪些步骤需要遵守本实验室 SOP？”
- “对比两篇 photothermal microgel 论文的刺激方式和参数差异。”
- “Leica DMi8 的基础使用/安全注意事项是什么？”
- “当前上下文里没有提供哪些 protocol 细节？”

## 注意

本项目面向实验室知识辅助，不替代实验室 PI、安全员或机构 SOP。涉及真实实验操作时，必须以本地批准 SOP 和风险评估为准。
