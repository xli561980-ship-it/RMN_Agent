#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run all RMN Agent evaluation stages and write a summary report."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import ensure_report_dir, markdown_table, timestamp  # noqa: E402
from eval.run_generation_eval import evaluate as run_generation  # noqa: E402
from eval.run_ragas_eval import evaluate as run_ragas  # noqa: E402
from eval.run_retrieval_eval import evaluate as run_retrieval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval, generation and optional RAGAS eval.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("-k", "--k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)

    reports = {
        "retrieval": run_retrieval(args.questions, args.evidence, k=args.k, report_dir=report_dir),
        "generation": run_generation(args.questions, k=args.k, report_dir=report_dir),
        "ragas": run_ragas(args.questions, report_dir=report_dir),
    }
    summary_path = report_dir / f"rag_eval_summary_{timestamp()}.md"
    rows = []
    for name, payload in reports.items():
        metrics = payload.get("metrics") or {}
        rows.append((name, payload.get("skipped", False), payload.get("reason", ""), (payload.get("report_paths") or {}).get("markdown", ""), len(metrics)))
    text = "# RAG Evaluation Summary\n\n" + markdown_table(
        ["stage", "skipped", "reason", "report", "metric_count"],
        rows,
    ) + "\n"
    summary_path.write_text(text, encoding="utf-8")
    print(f"summary report: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
