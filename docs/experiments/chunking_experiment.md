# Chunking Strategy 对比实验

## 为什么做

科研论文适合按章节和方法片段检索，SOP / 手册更需要保留完整步骤和上下文。单一 chunk size 很容易让论文参数召回不精确，或让 SOP 操作边界被切碎。

## 如何运行

默认不会重建用户向量库：

```bash
make bench-chunking
```

如需明确按策略重建索引：

```bash
python eval/run_chunking_benchmark.py --strategies fixed,header_aware,parent_child --k 5 --rebuild
```

## 输出文件

结果写入 `eval/reports/chunking_benchmark_<timestamp>.json/.md`。

## 策略说明

- `fixed`：固定字符窗口，作为 baseline。
- `header_aware`：按 Markdown / 论文常见标题切分，metadata 包含 `section_title`、`section_type`、`chunk_index`、`chunk_strategy`。
- `semantic_placeholder`：轻量段落合并占位，不依赖 embedding，不等同完整语义切分。
- `parent_child`：SOP / 手册场景，child chunk 用于检索，metadata 中保留 `parent_id`、`child_id`、`parent_text_preview`。

## 指标解释

重点看 `total_chunks`、`avg_chunk_chars`、`recall@5`、`mrr`、`doc_type_accuracy`。如果 chunk 数暴涨但 MRR 不升，可能是切分过碎；如果 SOP boundary 变差，可能需要 parent-child 或更大的 parent window。

## 当前限制

benchmark 只有在 `--rebuild` 时才会真正重建不同策略的索引。默认模式用于检查当前库，不会覆盖 Chroma。

## 如何改进系统

论文方法类问题优先尝试 `header_aware`，SOP 操作类优先尝试 `parent_child`。如果中文问题检索英文论文失败，下一步应结合 embedding benchmark 一起看。
