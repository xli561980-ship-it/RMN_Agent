# -*- coding: utf-8 -*-
"""Markdown helpers for chunking benchmark reports."""

from __future__ import annotations

from typing import Any, Sequence


def render_strategy_notes(rows: Sequence[dict[str, Any]]) -> str:
    lines = ["## 策略观察", ""]
    for row in rows:
        strategy = row.get("strategy")
        lines.append(f"- `{strategy}`: total_chunks={row.get('total_chunks', 0)}, avg_chunk_chars={row.get('avg_chunk_chars', 0)}")
    if not rows:
        lines.append("- 没有可比较结果。请确认已 ingest 文档并配置可用 embedding。")
    return "\n".join(lines)
