#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare chunking strategies with retrieval metrics."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import corpus_preflight, ensure_report_dir, markdown_table, timestamp, write_json  # noqa: E402
from eval.run_retrieval_eval import evaluate as run_retrieval  # noqa: E402


def _chroma_stats() -> dict[str, Any]:
    try:
        from rag_core import get_vectorstore

        batch = get_vectorstore()._collection.get(include=["documents", "metadatas"], limit=20000)  # noqa: SLF001
        docs = batch.get("documents") or []
        metas = batch.get("metadatas") or []
        return {
            "total_chunks": len(docs),
            "avg_chunk_chars": round(sum(len(d or "") for d in docs) / len(docs), 1) if docs else 0,
            "paper_chunks": sum(1 for m in metas if isinstance(m, dict) and m.get("doc_type") == "paper"),
            "sop_chunks": sum(1 for m in metas if isinstance(m, dict) and m.get("doc_type") == "sop"),
        }
    except Exception as exc:
        return {"total_chunks": 0, "avg_chunk_chars": 0, "paper_chunks": 0, "sop_chunks": 0, "stats_warning": str(exc)}


def _maybe_rebuild(strategy: str, rebuild: bool) -> tuple[bool, str, float]:
    if not rebuild:
        return False, "未传入 --rebuild，未重建向量库；将使用当前 Chroma 结果作为对照。", 0.0
    env = dict(os.environ)
    env.update({"CHUNK_STRATEGY": strategy, "PAPER_CHUNK_STRATEGY": strategy, "SOP_CHUNK_STRATEGY": strategy, "REBUILD_CHROMA": "1"})
    start = time.perf_counter()
    proc = subprocess.run([sys.executable, str(ROOT / "ingest.py")], cwd=str(ROOT), env=env, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        return True, f"rebuild failed: {proc.stderr.strip() or proc.stdout.strip()}", elapsed
    return True, "rebuild ok", elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run chunking benchmark.")
    parser.add_argument("--strategies", default="fixed,header_aware,parent_child")
    parser.add_argument("--rebuild", action="store_true", help="明确允许每种策略重建 Chroma。")
    parser.add_argument("-k", "--k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)
    rows: list[dict[str, Any]] = []
    for strategy in [s.strip() for s in args.strategies.split(",") if s.strip()]:
        rebuilt, note, build_time = _maybe_rebuild(strategy, args.rebuild)
        os.environ["CHUNK_STRATEGY"] = strategy
        stats = _chroma_stats()
        try:
            result = run_retrieval(args.questions, args.evidence, k=args.k, report_dir=report_dir)
            metrics = result.get("metrics") or {}
        except Exception as exc:
            metrics = {"error": str(exc)}
        rows.append(
            {
                "strategy": strategy,
                "rebuilt": rebuilt,
                "note": note,
                "index_build_time_sec": round(build_time, 2),
                **stats,
                f"recall@{args.k}": metrics.get(f"recall@{args.k}", 0),
                "mrr": metrics.get("mrr", 0),
                "doc_type_accuracy": metrics.get("doc_type_accuracy", 0),
                "citation_coverage_if_available": metrics.get("source_coverage", 0),
            }
        )
    payload = {"rows": rows, "k": args.k, "preflight_warnings": corpus_preflight()}
    stamp = timestamp()
    json_path = report_dir / f"chunking_benchmark_{stamp}.json"
    md_path = report_dir / f"chunking_benchmark_{stamp}.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload, args.k), encoding="utf-8")
    print(f"chunking benchmark report: {md_path}")
    return 0


def render_markdown(payload: dict[str, Any], k: int) -> str:
    rows = payload["rows"]
    table_rows = [
        (
            r["strategy"],
            r["total_chunks"],
            r["avg_chunk_chars"],
            r["paper_chunks"],
            r["sop_chunks"],
            round(float(r.get(f"recall@{k}") or 0), 3),
            round(float(r.get("mrr") or 0), 3),
            round(float(r.get("doc_type_accuracy") or 0), 3),
            r["note"],
        )
        for r in rows
    ]
    warnings = payload.get("preflight_warnings") or []
    warning_text = ""
    if warnings:
        warning_text = "## Preflight Warnings\n\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n"
    return "# Chunking Benchmark\n\n" + warning_text + markdown_table(
        ["strategy", "total_chunks", "avg_chunk_chars", "paper_chunks", "sop_chunks", f"recall@{k}", "mrr", "doc_type_accuracy", "note"],
        table_rows,
    ) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
