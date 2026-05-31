#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate expanded retrieval eval summary with per-category breakdown."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import (  # noqa: E402
    ensure_report_dir,
    load_gold_evidence,
    load_jsonl,
    markdown_table,
    timestamp,
    write_json,
)
from eval.run_google_embedding_failure_analysis import analyze_case  # noqa: E402
from eval.run_retrieval_eval import evaluate as run_retrieval_eval  # noqa: E402


def _categorize(case: dict[str, Any]) -> str:
    qid = str(case.get("id") or "")
    notes = str(case.get("notes") or "")
    if "[paper-comparison]" in notes or qid.startswith("paper_compare"):
        return "paper_comparison"
    if "[sop-only]" in notes or qid.startswith("sop_"):
        return "sop_only"
    if "[hybrid]" in notes or qid.startswith("hybrid_"):
        return "hybrid"
    if "[missing-evidence]" in notes or qid.startswith("missing_"):
        return "missing_evidence"
    if "[ambiguous-anchor]" in notes or qid.startswith("anchor_"):
        return "ambiguous_anchor"
    if "[paper-only]" in notes or qid.startswith("paper_"):
        return "paper_only"
    route = str(case.get("expected_route") or "")
    if route == "SOP_ONLY":
        return "sop_only"
    if route == "HYBRID":
        return "hybrid"
    return "paper_only"


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(r.get(key) or 0.0) for r in rows if r.get("ok")]
    return sum(vals) / len(vals) if vals else 0.0


def _distribution(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for case in cases:
        counts[_categorize(case)] += 1
    return dict(counts)


def _route_distribution(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for case in cases:
        counts[str(case.get("expected_route") or "unknown")] += 1
    return dict(counts)


def _build_failure_rows(
    questions: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
    evidence_by_q: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    eval_by_id = {str(r.get("id")): r for r in eval_rows}
    failures: list[dict[str, Any]] = []
    for case in questions:
        qid = str(case.get("id") or "")
        ev = evidence_by_q.get(qid, [])
        analyzed = analyze_case(case, ev, k_eval=5, k_deep=20)
        eval_row = eval_by_id.get(qid, {})
        if not analyzed.get("is_recall_miss") and eval_row.get("route_ok", True):
            continue
        failures.append(
            {
                "question_id": qid,
                "question": case.get("question"),
                "category": _categorize(case),
                "expected_route": case.get("expected_route"),
                "predicted_route": eval_row.get("predicted_route"),
                "gold_sources": case.get("gold_sources"),
                "top_retrieved_sources": eval_row.get("top_sources"),
                "recall@5": eval_row.get("recall@5"),
                "issue_types": analyzed.get("issue_types") or [],
                "possible_cause": ", ".join(analyzed.get("cause_tags") or []) or "route_or_ranking",
            }
        )
    return failures


def _category_metrics(
    questions: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    qcat = {str(q.get("id")): _categorize(q) for q in questions}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eval_rows:
        if not row.get("ok"):
            continue
        grouped[qcat.get(str(row.get("id")), "other")].append(row)
    out: dict[str, dict[str, float]] = {}
    for cat, rows in grouped.items():
        out[cat] = {
            "count": float(len(rows)),
            "recall@5": _avg(rows, "recall@5"),
            "recall@10": _avg(rows, "recall@10"),
            "recall@20": _avg(rows, "recall@20"),
            "mrr": _avg(rows, "mrr"),
            "doc_type_accuracy": _avg(rows, "doc_type_accuracy"),
        }
    return out


def _recommendations(payload: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    m = payload["overall_metrics"]
    cat = payload.get("category_metrics") or {}
    failures = payload.get("failure_cases") or []

    if m.get("recall@5", 1.0) < 0.85:
        recs.append("recall@5 在扩展集上低于 85%：优先检查 gold evidence 对齐、query anchoring 与 HYBRID 候选池，而非继续调 rule reranker 权重。")
    if (cat.get("ambiguous_anchor") or {}).get("recall@5", 1.0) < 0.8:
        recs.append("ambiguous anchor 类问题表现偏弱：检查 paper_anchor.py 是否误锚定 corpus-level 问题。")
    if (cat.get("paper_comparison") or {}).get("recall@5", 1.0) < 0.7:
        recs.append("paper comparison 类 recall 偏低：可能需要 multi-source retrieval 或 query rewrite，但仍不应为刷分收窄 gold。")
    if (cat.get("sop_only") or {}).get("recall@5", 1.0) < 0.8:
        recs.append("SOP-only 问题偏弱：检查 doc_type 路由、手册 chunking 与 cross-language query。")
    ranking = sum(1 for f in failures if "ranking_issue" in (f.get("issue_types") or []))
    recall = sum(1 for f in failures if "recall_issue" in (f.get("issue_types") or []))
    if ranking > recall and ranking > 0:
        recs.append("failure analysis 以 ranking_issue 为主：candidate pool 内排序或 quota 问题，可评估 reranker / hybrid quota，但 rule reranker 默认仍保持 none。")
    if recall > 0:
        recs.append("存在 recall_issue：优先扩大 topN、anchored retrieval 或检查 embedding/index 覆盖。")
    if not recs:
        recs.append("扩展集整体可接受；下一步继续增加 hard negatives 与 generation/citation eval，而非围绕当前集过拟合。")
    recs.append("若 chunking_boundary_issue 频繁出现：考虑 header-aware / parent-child 对比实验。")
    recs.append("若 gold_label_mismatch 出现：用 eval-gold-check 修正标签，而非改 retrieval 逻辑刷分。")
    return recs


def render_markdown(payload: dict[str, Any]) -> str:
    m = payload["overall_metrics"]
    lines = [
        "# Expanded Retrieval Eval Summary",
        "",
        f"- Timestamp: `{payload['timestamp']}`",
        f"- Questions: **{payload['question_count']}**",
        f"- Gold evidence rows: **{payload['evidence_count']}**",
        "",
        "## 1. 评估集规模",
        "",
        "### Question type 分布",
        "",
        markdown_table(["category", "count"], sorted(payload["category_distribution"].items())),
        "",
        "### Route 分布",
        "",
        markdown_table(["expected_route", "count"], sorted(payload["route_distribution"].items())),
        "",
        f"- Paper / SOP / hybrid（按 route）：{payload['route_distribution']}",
        "",
        "## 2. 总体指标",
        "",
        markdown_table(
            ["metric", "value"],
            [
                ("recall@5", round(m.get("recall@5", 0), 4)),
                ("recall@10", round(m.get("recall@10", 0), 4)),
                ("recall@20", round(m.get("recall@20", 0), 4)),
                ("precision@5", round(m.get("precision@5", 0), 4)),
                ("mrr", round(m.get("mrr", 0), 4)),
                ("ndcg@5", round(m.get("ndcg@5", 0), 4)),
                ("doc_type_accuracy", round(m.get("doc_type_accuracy", 0), 4)),
                ("sop_boundary_accuracy", round(m.get("sop_boundary_accuracy", 0), 4)),
                ("paper_to_sop_confusion_rate", round(m.get("paper_to_sop_confusion_rate", 0), 4)),
            ],
        ),
        "",
        "## 3. 各类型指标",
        "",
    ]
    cat_rows = []
    for cat, cm in sorted((payload.get("category_metrics") or {}).items()):
        cat_rows.append(
            (
                cat,
                int(cm.get("count", 0)),
                round(cm.get("recall@5", 0), 3),
                round(cm.get("recall@10", 0), 3),
                round(cm.get("recall@20", 0), 3),
                round(cm.get("mrr", 0), 3),
            )
        )
    lines.append(
        markdown_table(
            ["category", "n", "recall@5", "recall@10", "recall@20", "mrr"],
            cat_rows,
        )
    )
    lines.extend(["", "## 4. Failure analysis 汇总", ""])
    fa = payload.get("failure_analysis") or {}
    lines.append(
        markdown_table(
            ["issue_type", "count"],
            sorted((fa.get("issue_types") or {}).items()),
        )
    )
    lines.extend(["", "## 5. Top failure cases", ""])
    failures = payload.get("failure_cases") or []
    if failures:
        lines.append(
            markdown_table(
                ["question_id", "category", "expected_route", "predicted_route", "recall@5", "possible_cause"],
                [
                    (
                        f.get("question_id"),
                        f.get("category"),
                        f.get("expected_route"),
                        f.get("predicted_route"),
                        f.get("recall@5"),
                        f.get("possible_cause"),
                    )
                    for f in failures[:15]
                ],
            )
        )
        for f in failures[:8]:
            lines.extend(
                [
                    "",
                    f"### `{f.get('question_id')}`",
                    f"- Question: {f.get('question')}",
                    f"- Gold sources: `{f.get('gold_sources')}`",
                    f"- Top retrieved: `{f.get('top_retrieved_sources')}`",
                    f"- Issues: `{f.get('issue_types')}`",
                ]
            )
    else:
        lines.append("_No recall misses at @5 in this run._")
    lines.extend(["", "## 6. 下一步建议", ""])
    for r in payload.get("recommendations") or []:
        lines.append(f"- {r}")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- Retrieval eval JSON: `{payload.get('retrieval_eval_json')}`")
    lines.append(f"- Gold alignment: `{payload.get('gold_alignment_json', 'n/a')}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run expanded retrieval eval summary.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "eval" / "reports")
    parser.add_argument("--skip-retrieval", action="store_true", help="Use latest retrieval_eval_*.json")
    parser.add_argument("--skip-gold-check", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("EMBEDDING_PROVIDER", "google")
    report_dir = ensure_report_dir(args.report_dir)

    gold_alignment_json = ""
    if not args.skip_gold_check:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "eval" / "check_gold_evidence_alignment.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        latest = sorted(report_dir.glob("gold_evidence_alignment_*.json"), reverse=True)
        gold_alignment_json = str(latest[0]) if latest else ""

    if args.skip_retrieval:
        candidates = sorted(report_dir.glob("retrieval_eval_*.json"), reverse=True)
        if not candidates:
            print("No retrieval_eval_*.json found", file=sys.stderr)
            return 1
        retrieval_payload = json.loads(candidates[0].read_text(encoding="utf-8"))
        retrieval_json = str(candidates[0])
    else:
        retrieval_payload = run_retrieval_eval(args.questions, args.evidence, k=5, report_dir=report_dir)
        retrieval_json = retrieval_payload["report_paths"]["json"]

    questions = load_jsonl(args.questions)
    evidence_by_q = load_gold_evidence(args.evidence)
    eval_rows = retrieval_payload.get("cases") or []
    failures = _build_failure_rows(questions, eval_rows, evidence_by_q)

    issue_counter: Counter = Counter()
    for case in questions:
        qid = str(case.get("id") or "")
        analyzed = analyze_case(case, evidence_by_q.get(qid, []), k_eval=5, k_deep=20)
        for ev in analyzed.get("evidence_rows") or []:
            if ev.get("issue_type"):
                issue_counter[str(ev["issue_type"])] += 1

    stamp = timestamp()
    payload = {
        "timestamp": stamp,
        "question_count": len(questions),
        "evidence_count": sum(len(v) for v in evidence_by_q.values()),
        "category_distribution": _distribution(questions),
        "route_distribution": _route_distribution(questions),
        "overall_metrics": retrieval_payload.get("metrics") or {},
        "category_metrics": _category_metrics(questions, eval_rows),
        "failure_analysis": {"issue_types": dict(issue_counter)},
        "failure_cases": failures,
        "recommendations": [],
        "retrieval_eval_json": retrieval_json,
        "gold_alignment_json": gold_alignment_json,
    }
    payload["recommendations"] = _recommendations(payload)

    md_path = report_dir / f"expanded_eval_summary_{stamp}.md"
    json_path = report_dir / f"expanded_eval_summary_{stamp}.json"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"expanded eval summary: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
