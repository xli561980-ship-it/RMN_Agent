#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare reranker providers with retrieval metrics."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import corpus_preflight, ensure_report_dir, markdown_table, timestamp, write_json  # noqa: E402
from eval.run_retrieval_eval import evaluate as run_retrieval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reranker benchmark.")
    parser.add_argument("--rerankers", default="none,rule,bge")
    parser.add_argument("-k", "--k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)
    rows: list[dict[str, Any]] = []
    for reranker in [r.strip() for r in args.rerankers.split(",") if r.strip()]:
        os.environ["RERANKER_PROVIDER"] = reranker
        start = time.perf_counter()
        try:
            result = run_retrieval(args.questions, args.evidence, k=args.k, report_dir=report_dir)
            metrics = result.get("metrics") or {}
            failure_cases = [c.get("id") for c in result.get("cases", []) if not c.get("gold_hit") or not c.get("route_ok")]
        except Exception as exc:
            metrics = {"error": str(exc)}
            failure_cases = []
        total_ms = (time.perf_counter() - start) * 1000
        rows.append(
            {
                "reranker": reranker,
                f"recall@{args.k}": metrics.get(f"recall@{args.k}", 0),
                f"precision@{args.k}": metrics.get(f"precision@{args.k}", 0),
                "mrr": metrics.get("mrr", 0),
                f"ndcg@{args.k}": metrics.get(f"ndcg@{args.k}", 0),
                "sop_boundary_accuracy": metrics.get("sop_boundary_accuracy", 0),
                "paper_to_sop_confusion_rate": metrics.get("paper_to_sop_confusion_rate", 0),
                "avg_rerank_latency_ms": 0,
                "avg_total_retrieval_latency_ms": metrics.get("avg_retrieval_latency_ms", round(total_ms, 2)),
                "failure_cases": failure_cases,
            }
        )
    payload = {"rows": rows, "k": args.k, "preflight_warnings": corpus_preflight()}
    stamp = timestamp()
    json_path = report_dir / f"rerank_benchmark_{stamp}.json"
    md_path = report_dir / f"rerank_benchmark_{stamp}.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload, args.k), encoding="utf-8")
    print(f"rerank benchmark report: {md_path}")
    return 0


def render_markdown(payload: dict[str, Any], k: int) -> str:
    rows = payload["rows"]
    lines = ["# Reranker Benchmark", ""]
    if payload.get("preflight_warnings"):
        lines.extend(["## Preflight Warnings", ""])
        lines.extend(f"- {w}" for w in payload["preflight_warnings"])
        lines.append("")
    lines.append(
        markdown_table(
            ["reranker", f"recall@{k}", f"precision@{k}", "mrr", f"ndcg@{k}", "sop_boundary", "confusion", "failures"],
            [
                (
                    r["reranker"],
                    round(float(r.get(f"recall@{k}") or 0), 3),
                    round(float(r.get(f"precision@{k}") or 0), 3),
                    round(float(r.get("mrr") or 0), 3),
                    round(float(r.get(f"ndcg@{k}") or 0), 3),
                    round(float(r.get("sop_boundary_accuracy") or 0), 3),
                    round(float(r.get("paper_to_sop_confusion_rate") or 0), 3),
                    ", ".join(r.get("failure_cases") or []),
                )
                for r in rows
            ],
        )
    )
    lines.extend(["", "## 观察重点", "- `rule` 是否降低 paper/SOP 混淆。", "- `bge` 或 cross-encoder 是否提升 MRR。", "- rerank 后是否牺牲 hybrid doc_type 平衡。"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
