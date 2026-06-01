#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit disk documents, processed registry, and Chroma sources for coverage gaps."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402

from ingest import (  # noqa: E402
    CHROMA_COLLECTION_NAME,
    CHROMA_PERSIST_DIR,
    DATA_MANUALS_DIR,
    DATA_PAPERS_DIR,
    PROCESSED_FILES_JSON,
    is_supported_ingest_file,
    iter_ingest_jobs,
    pdf_source_key,
)


def _scan_disk(*, recursive: bool) -> set[str]:
    paths: list[Path] = []
    for root in (DATA_PAPERS_DIR, DATA_MANUALS_DIR):
        iterator = root.rglob("*") if recursive else root.iterdir()
        paths.extend(p for p in iterator if is_supported_ingest_file(p))
    return {pdf_source_key(p) for p in paths}


def _load_processed() -> set[str]:
    if not PROCESSED_FILES_JSON.is_file():
        return set()
    data = json.loads(PROCESSED_FILES_JSON.read_text(encoding="utf-8"))
    return set((data.get("files") or {}).keys())


def _load_chroma_sources() -> tuple[set[str], dict[str, int]]:
    persist = Path(os.getenv("CHROMA_PERSIST_DIR", str(CHROMA_PERSIST_DIR))).resolve()
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", CHROMA_COLLECTION_NAME)
    if not persist.is_dir():
        return set(), {}
    client = chromadb.PersistentClient(path=str(persist))
    try:
        collection = client.get_collection(collection_name)
    except Exception:
        return set(), {}
    batch = collection.get(include=["metadatas"], limit=1_000_000)
    metas = batch.get("metadatas") or []
    counts: Counter[str] = Counter()
    for meta in metas:
        source = str((meta or {}).get("source") or "").strip()
        if source:
            counts[source] += 1
    return set(counts), dict(counts)


def build_audit() -> dict[str, Any]:
    disk_first_level = _scan_disk(recursive=False)
    disk_recursive = _scan_disk(recursive=True)
    current_ingest_sources = {pdf_source_key(path) for path, _ in iter_ingest_jobs()}
    processed = _load_processed()
    chroma_sources, chroma_chunk_counts = _load_chroma_sources()
    nested_supported = sorted(disk_recursive - disk_first_level)
    return {
        "counts": {
            "disk_first_level_supported": len(disk_first_level),
            "disk_recursive_supported": len(disk_recursive),
            "current_ingest_supported": len(current_ingest_sources),
            "nested_supported": len(nested_supported),
            "recursive_disk_not_seen_by_current_ingest": len(disk_recursive - current_ingest_sources),
            "processed_sources": len(processed),
            "chroma_sources": len(chroma_sources),
            "chroma_chunks": sum(chroma_chunk_counts.values()),
        },
        "nested_supported": nested_supported,
        "recursive_disk_not_seen_by_current_ingest": sorted(disk_recursive - current_ingest_sources),
        "disk_without_processed": sorted(disk_recursive - processed),
        "processed_without_disk": sorted(processed - disk_recursive),
        "disk_without_chroma": sorted(disk_recursive - chroma_sources),
        "processed_without_chroma": sorted(processed - chroma_sources),
        "chroma_without_processed": sorted(chroma_sources - processed),
        "zero_chunk_suspects": sorted((processed & disk_recursive) - chroma_sources),
        "chroma_chunk_counts": chroma_chunk_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON report path.")
    parser.add_argument("--preview", type=int, default=20)
    args = parser.parse_args()

    report = build_audit()
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2, sort_keys=True))
    for key in (
        "nested_supported",
        "recursive_disk_not_seen_by_current_ingest",
        "disk_without_processed",
        "processed_without_chroma",
        "chroma_without_processed",
        "zero_chunk_suspects",
    ):
        values = report.get(key) or []
        print(f"\n{key}: {len(values)}")
        for value in values[: args.preview]:
            print(f"- {value}")
        if len(values) > args.preview:
            print(f"- ... {len(values) - args.preview} more")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nSaved audit: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
