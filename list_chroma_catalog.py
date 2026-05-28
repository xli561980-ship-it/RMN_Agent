#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List distinct (source, paper_title, project_id) for doc_type=paper in the persisted Chroma store.

Uses the same paths and embedding stub as ingest so you can verify what titles were stored
without opening the DB manually. Large collections: metadata fetch may take a moment.

Usage:
  python list_chroma_catalog.py
"""
from __future__ import annotations

import sys

from langchain_chroma import Chroma

from ingest import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR, build_embeddings


def main() -> int:
    emb = build_embeddings()
    vs = Chroma(
        collection_name=CHROMA_COLLECTION_NAME,
        persist_directory=str(CHROMA_PERSIST_DIR),
        embedding_function=emb,
    )
    col = vs._collection  # noqa: SLF001 — intentional introspection for batch metadata read
    batch = col.get(include=["metadatas"], limit=100_000)
    metas = batch.get("metadatas") or []
    rows: set[tuple[str, str, str]] = set()
    for m in metas:
        if not m or m.get("doc_type") != "paper":
            continue
        src = str(m.get("source") or "")
        tit = str(m.get("paper_title") or "")
        pid = str(m.get("project_id") or "")
        rows.add((src, tit, pid))
    if not rows:
        print("No paper rows found (empty store or ingest not run).", file=sys.stderr)
        return 1
    print("source\tpaper_title\tproject_id")
    for src, tit, pid in sorted(rows):
        print(f"{src}\t{tit}\t{pid}")
    print(f"# distinct paper (source,title,project_id) tuples: {len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
