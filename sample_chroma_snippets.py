#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从持久化 Chroma 中随机抽取若干条 chunk，打印正文与元数据，用于人工检查
PDF 解析后是否有乱码、双栏串行、断行等问题。

用法（在项目根目录、已激活 venv 时）：
  python sample_chroma_snippets.py
  python sample_chroma_snippets.py -n 15
  python sample_chroma_snippets.py --paper-only   # 仅 doc_type=paper（论文路）

依赖 .env 中的 CHROMA_PERSIST_DIR / CHROMA_COLLECTION_NAME（未设置时与 ingest.py 默认一致）。
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import chromadb
from dotenv import load_dotenv


def _persist_and_collection() -> tuple[Path, str]:
    load_dotenv()
    persist = Path(os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")).resolve()
    name = os.getenv("CHROMA_COLLECTION_NAME", "lab_literature_rag")
    return persist, name


def _fmt_meta(meta: dict | None) -> str:
    if not meta:
        return "(无元数据)"
    keys = ("source", "page", "doc_type", "doc_role", "paper_title", "Header 1", "Header 2")
    parts = []
    for k in keys:
        if k in meta and meta[k] is not None:
            parts.append(f"{k}={meta[k]!r}")
    rest = {k: v for k, v in meta.items() if k not in keys}
    if rest:
        parts.append(f"… 另有 {len(rest)} 个字段")
    return " | ".join(parts) if parts else repr(meta)


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Chroma 随机打印文本片段")
    parser.add_argument("-n", type=int, default=10, help="抽样条数（默认 10）")
    parser.add_argument(
        "--paper-only",
        action="store_true",
        help="只从 doc_type=paper 的记录中抽样（会一次性读入所有匹配行，库很大时慎用）",
    )
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现同一批样本")
    args = parser.parse_args()

    if args.n < 1:
        print("错误: -n 至少为 1", file=sys.stderr)
        return 1

    if args.seed is not None:
        random.seed(args.seed)

    persist, coll_name = _persist_and_collection()
    if not persist.is_dir():
        print(f"错误: Chroma 目录不存在: {persist}", file=sys.stderr)
        return 1

    client = chromadb.PersistentClient(path=str(persist))
    try:
        coll = client.get_collection(coll_name)
    except Exception as e:
        print(f"错误: 无法打开集合 {coll_name!r}: {e}", file=sys.stderr)
        return 1

    where = {"doc_type": "paper"} if args.paper_only else None
    include = ["documents", "metadatas"]

    if where is None:
        total = coll.count()
        if total == 0:
            print("集合为空，请先运行入库（ingest）。")
            return 0
        k = min(args.n, total)
        offsets = sorted(random.sample(range(total), k))
        batches = [
            coll.get(limit=1, offset=o, include=include) for o in offsets
        ]
        docs_list: list[str | None] = []
        metas_list: list[dict | None] = []
        for b in batches:
            d = (b.get("documents") or [None])[0]
            m = (b.get("metadatas") or [None])[0]
            docs_list.append(d)
            metas_list.append(m)
    else:
        res = coll.get(where=where, include=include)
        ids = res.get("ids") or []
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        if not ids:
            print("没有符合 doc_type=paper 的记录。")
            return 0
        m = min(args.n, len(ids))
        idxs = sorted(random.sample(range(len(ids)), m))
        docs_list = [docs[i] if i < len(docs) else None for i in idxs]
        metas_list = [metas[i] if i < len(metas) else None for i in idxs]

    print(f"Chroma: {persist}\n集合: {coll_name}\n抽样数: {len(docs_list)}\n{'=' * 72}\n")

    for i, (text, meta) in enumerate(zip(docs_list, metas_list), start=1):
        print(f"### [{i}] {_fmt_meta(meta)}\n")
        body = text if text is not None else "(无 document 文本)"
        print(body)
        print(f"\n{'-' * 72}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
