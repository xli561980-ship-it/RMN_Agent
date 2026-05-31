#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare retrieval metrics before/after ranking optimizations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import ensure_report_dir, markdown_table, timestamp  # noqa: E402
from eval.run_retrieval_eval import evaluate as run_retrieval  # noqa: E402

BASELINE_EVAL = ROOT / "eval" / "reports" / "retrieval_eval_20260531_010709.json"
METRIC_KEYS = [
    "recall@5",
    "recall@10",
    "recall@20",
    "mrr",
    "ndcg@5",
    "doc_type_accuracy",
    "paper_to_sop_confusion_rate",
]
FOCUS_QUESTIONS = ("hybrid_replicate_safety", "missing_evidence")


def _run_failure_analysis() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "eval" / "run_google_embedding_failure_analysis.py")],
        cwd=str(ROOT),
        check=False,
        env={**os.environ, "EMBEDDING_PROVIDER": "google"},
    )


def _extract_metrics(payload: dict[str, Any]) -> dict[str, float]:
    m = payload.get("metrics") or {}
    out: dict[str, float] = {}
    for key in METRIC_KEYS:
        if key in m:
            out[key] = float(m[key])
        elif key == "ndcg@5":
            out[key] = float(m.get("ndcg@5") or m.get("ndcg@k") or 0.0)
    return out


def _focus_ranks(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in payload.get("cases") or []:
        qid = str(row.get("id") or "")
        if qid in FOCUS_QUESTIONS:
            out[qid] = list(row.get("gold_evidence") or [])
    return out


def _delta(a: float, b: float) -> str:
    diff = b - a
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.4f}"


def render_markdown(
    *,
    before_label: str,
    after_label: str,
    before_metrics: dict[str, float],
    after_metrics: dict[str, float],
    before_ranks: dict[str, list[dict[str, Any]]],
    after_ranks: dict[str, list[dict[str, Any]]],
    before_path: Path,
    after_path: Path,
    failure_analysis_path: Path | None,
) -> str:
    lines = [
        "# Ranking Optimization Report",
        "",
        "## Changes applied",
        "",
        "- Dual-path rule reranker with RRF + rule_score fusion",
        "- HYBRID minimum paper/SOP chunk reservation (`HYBRID_MIN_PAPER_CHUNKS`, `HYBRID_MIN_SOP_CHUNKS`)",
        "- Safety/SOP/manual/protocol boosts and generic microgel demotion",
        "- Introduction/discussion/limitations boost for generalization questions",
        "- Retrieval eval now reports recall@5/10/20 and per-evidence `gold_hit_rank`",
        "",
        "## Metric comparison",
        "",
        markdown_table(
            ["metric", before_label, after_label, "delta"],
            [(k, round(before_metrics.get(k, 0.0), 4), round(after_metrics.get(k, 0.0), 4), _delta(before_metrics.get(k, 0.0), after_metrics.get(k, 0.0))) for k in METRIC_KEYS],
        ),
        "",
        "## Focus failure questions: gold_hit_rank",
        "",
    ]
    for qid in FOCUS_QUESTIONS:
        lines.append(f"### `{qid}`")
        before_rows = before_ranks.get(qid) or []
        after_rows = after_ranks.get(qid) or []
        lines.append(
            markdown_table(
                ["section", f"{before_label} rank", f"{after_label} rank", "delta"],
                [
                    (
                        (after_rows[i] if i < len(after_rows) else {}).get("section") or (before_rows[i] if i < len(before_rows) else {}).get("section"),
                        (before_rows[i] if i < len(before_rows) else {}).get("gold_hit_rank"),
                        (after_rows[i] if i < len(after_rows) else {}).get("gold_hit_rank"),
                        _rank_delta(
                            (before_rows[i] if i < len(before_rows) else {}).get("gold_hit_rank"),
                            (after_rows[i] if i < len(after_rows) else {}).get("gold_hit_rank"),
                        ),
                    )
                    for i in range(max(len(before_rows), len(after_rows)))
                ],
            )
        )
        lines.append("")

    lines.extend(
        [
            "## Manual review: `missing_evidence`",
            "",
            "- Failure analysis flagged possible **`gold_label_mismatch`** for this question.",
            "- The current gold evidence points to Wang 2025 Introduction scope (MSCs only), while retrieval often ranks other microgel/stem-cell papers higher.",
            "- **Do not auto-edit gold labels.** Consider whether eval should:",
            "  1. Add gold evidence rows for İyisan / Özkale papers when the question refers to “这些文献”, or",
            "  2. Rewrite the question to explicitly anchor Wang 2025 / a single paper scope.",
            "",
            "## Artifacts",
            "",
            f"- Before eval: `{before_path}`",
            f"- After eval: `{after_path}`",
        ]
    )
    if failure_analysis_path and failure_analysis_path.is_file():
        lines.append(f"- Updated failure analysis: `{failure_analysis_path}`")
    lines.append("")
    return "\n".join(lines)


def _rank_delta(before: Any, after: Any) -> str:
    if before is None and after is None:
        return "n/a"
    if before is None:
        return f"new@{after}"
    if after is None:
        return "lost"
    try:
        diff = int(before) - int(after)
    except (TypeError, ValueError):
        return "n/a"
    if diff > 0:
        return f"↑{diff}"
    if diff < 0:
        return f"↓{abs(diff)}"
    return "same"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare ranking optimization before/after.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--baseline-eval", type=Path, default=BASELINE_EVAL)
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    parser.add_argument("--skip-rerun-baseline", action="store_true", help="Use --baseline-eval JSON as before snapshot.")
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)

    if args.skip_rerun_baseline and args.baseline_eval.is_file():
        before_payload = json.loads(args.baseline_eval.read_text(encoding="utf-8"))
        before_label = args.baseline_eval.stem
        before_path = args.baseline_eval
    else:
        os.environ["RERANKER_PROVIDER"] = "none"
        before_payload = run_retrieval(args.questions, args.evidence, k=5, report_dir=report_dir)
        before_label = "before_rule_rerank"
        before_path = Path((before_payload.get("report_paths") or {}).get("json", ""))

    os.environ["RERANKER_PROVIDER"] = "rule"
    after_payload = run_retrieval(args.questions, args.evidence, k=5, report_dir=report_dir)
    after_path = Path((after_payload.get("report_paths") or {}).get("json", ""))

    _run_failure_analysis()
    failure_analysis_path = ROOT / "eval" / "reports" / "google_embedding_failure_analysis.md"

    md = render_markdown(
        before_label=before_label,
        after_label="after_rule_rerank",
        before_metrics=_extract_metrics(before_payload),
        after_metrics=_extract_metrics(after_payload),
        before_ranks=_focus_ranks(before_payload),
        after_ranks=_focus_ranks(after_payload),
        before_path=before_path,
        after_path=after_path,
        failure_analysis_path=failure_analysis_path,
    )
    out = report_dir / f"ranking_optimization_{timestamp()}.md"
    out.write_text(md, encoding="utf-8")
    print(f"ranking optimization report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
