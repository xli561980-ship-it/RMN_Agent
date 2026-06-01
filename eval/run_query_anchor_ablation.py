#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query anchoring ablation: no_anchor vs analyzer_anchor vs forced gold source (diagnostic)."""

from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import (  # noqa: E402
    doc_matches_gold,
    doc_source,
    flatten_docs,
    load_gold_evidence,
    load_jsonl,
    markdown_table,
    timestamp,
)
from eval.run_retrieval_eval import _evidence_hit_ranks, _evidence_recall_at_k  # noqa: E402
from query_analyzer import analyze_query, heuristic_analyze_query, normalize_analysis  # noqa: E402
from rag_core import fusion_prepare  # noqa: E402

FOCUS_IDS = ("hybrid_replicate_safety", "missing_evidence")


def _strip_anchor_fields(analysis: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(normalize_analysis(analysis))
    out["paper_scope_source"] = None
    out["paper_scope_project_id"] = None
    out["paper_scope_paper_title"] = None
    out["paper_scope_source_hint"] = None
    return out


def _forced_gold_analysis(case: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(normalize_analysis(base))
    sources = [str(s) for s in (case.get("gold_sources") or []) if str(s).startswith("papers/")]
    if sources:
        out["paper_scope_source"] = sources[0]
        out["paper_scope_source_hint"] = sources[0]
    return out


def _top_sources(docs: list[Any], n: int = 20) -> list[str]:
    return [doc_source(d) for d in docs[:n]]


def _run_mode(
    case: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    mode: str,
    deep_k: int,
    use_llm: bool,
) -> dict[str, Any]:
    q = str(case.get("question") or "")
    if mode == "no_anchor":
        analysis = _strip_anchor_fields(heuristic_analyze_query(q, paper_anchor=None))
    elif mode == "analyzer_anchor":
        analysis = analyze_query(q, paper_anchor=None) if use_llm else heuristic_analyze_query(q, paper_anchor=None)
    elif mode == "forced_gold_source_anchor":
        base = heuristic_analyze_query(q, paper_anchor=None)
        analysis = _forced_gold_analysis(case, base)
    else:
        raise ValueError(mode)

    os.environ["RERANKER_PROVIDER"] = "none"
    bundle = fusion_prepare(q, k=deep_k, analysis=analysis)
    docs = flatten_docs(bundle, k=deep_k)
    diag = bundle.get("retrieval_diagnostics") or {}
    docs_before = list(diag.get("docs_before_rerank") or docs)
    ranks = _evidence_hit_ranks(docs, case, evidence)
    return {
        "mode": mode,
        "analysis_scope_source": analysis.get("paper_scope_source"),
        "analysis_title_hint": analysis.get("paper_scope_paper_title") or analysis.get("paper_scope_source_hint"),
        "candidate_pool_size": diag.get("candidate_pool_size", len(docs_before)),
        "anchored_source_detected": diag.get("anchored_source_detected"),
        "anchored_source_hit_count": diag.get("anchored_source_hit_count", 0),
        "recall@5": _evidence_recall_at_k(docs, case, evidence, 5),
        "recall@10": _evidence_recall_at_k(docs, case, evidence, 10),
        "recall@20": _evidence_recall_at_k(docs, case, evidence, 20),
        "gold_evidence": ranks,
        "top20_sources": _top_sources(docs, 20),
        "whether_gold_was_in_candidate_pool": any(
            doc_matches_gold(d, case, [ev]) for ev in evidence for d in docs_before
        ),
    }


def render_markdown(results: list[dict[str, Any]], *, use_llm: bool) -> str:
    lines = [
        "# Query Anchor Ablation",
        "",
        f"- Analyzer: `{'LLM' if use_llm else 'heuristic only'}`",
        f"- Reranker: `none` (default pipeline)",
        f"- Forced gold source mode is **diagnostic only** and not used in production.",
        "",
        "## Summary",
        "",
        markdown_table(
            ["question_id", "mode", "scope_source", "recall@5", "recall@10", "recall@20", "in_pool"],
            [
                (
                    r["question_id"],
                    r["mode"],
                    Path(str(r.get("analysis_scope_source") or r.get("analysis_title_hint") or "")).name or "-",
                    round(float(r.get("recall@5") or 0), 3),
                    round(float(r.get("recall@10") or 0), 3),
                    round(float(r.get("recall@20") or 0), 3),
                    r.get("whether_gold_was_in_candidate_pool"),
                )
                for r in results
            ],
        ),
        "",
        "## Focus questions",
        "",
    ]
    for qid in FOCUS_IDS:
        subset = [r for r in results if r["question_id"] == qid]
        if not subset:
            continue
        lines.append(f"### `{qid}`")
        before = next((r for r in subset if r["mode"] == "no_anchor"), None)
        after = next((r for r in subset if r["mode"] == "analyzer_anchor"), None)
        if before and after:
            lines.append("")
            lines.append("#### gold_hit_rank delta (analyzer vs no_anchor)")
            lines.append(
                markdown_table(
                    ["section", "no_anchor", "analyzer_anchor", "forced_gold"],
                    [
                        (
                            (after.get("gold_evidence") or [{}])[i].get("section"),
                            (before.get("gold_evidence") or [{}])[i].get("gold_hit_rank") if i < len(before.get("gold_evidence") or []) else None,
                            (after.get("gold_evidence") or [{}])[i].get("gold_hit_rank"),
                            (next((x for x in subset if x["mode"] == "forced_gold_source_anchor"), {}).get("gold_evidence") or [{}])[i].get("gold_hit_rank")
                            if i < len(next((x for x in subset if x["mode"] == "forced_gold_source_anchor"), {}).get("gold_evidence") or [])
                            else None,
                        )
                        for i in range(max(len(after.get("gold_evidence") or []), len(before.get("gold_evidence") or [])))
                    ],
                )
            )
        for row in subset:
            lines.extend(
                [
                    "",
                    f"#### `{row['mode']}` top-20 sources",
                    "",
                    markdown_table(
                        ["rank", "source"],
                        [(i + 1, Path(s).name) for i, s in enumerate(row.get("top20_sources") or [])],
                    ),
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- `forced_gold_source_anchor` injects `gold_sources[0]` into analysis for upper-bound diagnosis.",
            "- Production should rely on UI anchor + analyzer hints, not forced gold injection.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run query anchor ablation.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "eval" / "reports")
    parser.add_argument("--heuristic-only", action="store_true", help="Skip LLM analyzer (faster, offline).")
    parser.add_argument("--question-ids", default=",".join(FOCUS_IDS))
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("EMBEDDING_PROVIDER", "google")
    os.environ["RERANKER_PROVIDER"] = "none"

    questions = {row["id"]: row for row in load_jsonl(args.questions)}
    evidence_by_q = load_gold_evidence(args.evidence)
    qids = [x.strip() for x in args.question_ids.split(",") if x.strip()]
    modes = ("no_anchor", "analyzer_anchor", "forced_gold_source_anchor")
    results: list[dict[str, Any]] = []
    for qid in qids:
        case = questions.get(qid)
        if not case:
            continue
        evidence = evidence_by_q.get(qid, [])
        for mode in modes:
            row = _run_mode(
                case,
                evidence,
                mode=mode,
                deep_k=20,
                use_llm=not args.heuristic_only,
            )
            row["question_id"] = qid
            results.append(row)

    out = args.report_dir / f"query_anchor_ablation_{timestamp()}.md"
    out.write_text(render_markdown(results, use_llm=not args.heuristic_only), encoding="utf-8")
    print(f"query anchor ablation report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
