#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run comparable retrieval evaluation for RMN Agent."""

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

from eval.eval_utils import (  # noqa: E402
    avg,
    doc_matches_gold,
    doc_source,
    doc_type,
    ensure_report_dir,
    flatten_docs,
    has_local_gold_source,
    load_gold_evidence,
    load_jsonl,
    markdown_table,
    timestamp,
    write_json,
)
from eval.metrics import (  # noqa: E402
    confusion_rate,
    doc_type_accuracy,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    source_coverage,
)
from rag_core import fusion_prepare  # noqa: E402


def _evidence_recall_at_k(docs: list[Any], case: dict[str, Any], evidence: list[dict[str, Any]], limit: int) -> float:
    if not evidence:
        return 0.0
    top = docs[:limit]
    hits = sum(1 for ev in evidence if any(doc_matches_gold(d, case, [ev]) for d in top))
    return hits / len(evidence)


def _evidence_hit_ranks(docs: list[Any], case: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, ev in enumerate(evidence):
        rank = None
        for i, doc in enumerate(docs, start=1):
            if doc_matches_gold(doc, case, [ev]):
                rank = i
                break
        rows.append(
            {
                "evidence_index": idx,
                "section": ev.get("section"),
                "source": ev.get("source"),
                "gold_hit_rank": rank,
                "hit@5": rank is not None and rank <= 5,
                "hit@10": rank is not None and rank <= 10,
                "hit@20": rank is not None and rank <= 20,
            }
        )
    return rows


def _evidence_mrr(hit_ranks: list[dict[str, Any]]) -> float:
    if not hit_ranks:
        return 0.0
    scores = [1.0 / int(r["gold_hit_rank"]) for r in hit_ranks if r.get("gold_hit_rank")]
    return sum(scores) / len(hit_ranks) if hit_ranks else 0.0


def _sop_boundary_ok(case: dict[str, Any], docs: list[Any]) -> bool | None:
    expected_route = str(case.get("expected_route") or "")
    requires_sop = bool(case.get("requires_sop"))
    if expected_route not in {"SOP_ONLY", "HYBRID", "PAPER_ONLY"} and not requires_sop:
        return None
    types = [doc_type(d) for d in docs]
    if expected_route == "SOP_ONLY" or requires_sop:
        return "sop" in types
    if expected_route == "PAPER_ONLY":
        return types.count("sop") <= max(1, len(types) // 3)
    return "paper" in types and "sop" in types


def _paper_sop_confusion(case: dict[str, Any], docs: list[Any]) -> float:
    expected = set(case.get("expected_doc_types") or [])
    if not expected:
        route = str(case.get("expected_route") or "")
        if route == "SOP_ONLY":
            expected = {"sop"}
        elif route == "PAPER_ONLY":
            expected = {"paper"}
    if not expected:
        return 0.0
    return confusion_rate(docs, lambda d: doc_type(d) not in expected)


def evaluate(questions_path: Path, evidence_path: Path, *, k: int, report_dir: Path) -> dict[str, Any]:
    cases = load_jsonl(questions_path)
    evidence_by_q = load_gold_evidence(evidence_path)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for case in cases:
        cid = str(case.get("id") or "")
        q = str(case.get("question") or "")
        start = time.perf_counter()
        try:
            deep_k = max(k, 20)
            bundle = fusion_prepare(q, k=deep_k)
            error = ""
        except Exception as exc:
            rows.append({"id": cid, "question": q, "error": str(exc), "ok": False})
            continue
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        analysis = bundle.get("analysis") or {}
        docs_deep = flatten_docs(bundle, k=deep_k)
        docs = docs_deep[:k]
        evidence = evidence_by_q.get(cid, [])
        hits = [doc_matches_gold(d, case, evidence) for d in docs]
        source_list = [doc_source(d) for d in docs]
        type_list = [doc_type(d) for d in docs]
        expected_types = list(case.get("expected_doc_types") or [])
        if not expected_types:
            route = str(case.get("expected_route") or "")
            expected_types = ["paper"] if route == "PAPER_ONLY" else ["sop"] if route == "SOP_ONLY" else ["paper", "sop"]

        local_ok, missing_gold_sources = has_local_gold_source(case, docs_deep)
        if not local_ok:
            warnings.append(f"{cid}: gold_sources not found in retrieved Chroma results: {', '.join(missing_gold_sources)}")

        hit_ids = [i for i, hit in enumerate(hits) if hit]
        rels = [1 if (hit or (type_list[i] in expected_types)) else 0 for i, hit in enumerate(hits)]
        evidence_ranks = _evidence_hit_ranks(docs_deep, case, evidence)
        diag = bundle.get("retrieval_diagnostics") or {}
        docs_before = list(diag.get("docs_before_rerank") or [])
        docs_after = list(diag.get("docs_after_rerank") or docs_deep)
        ranks_before = _evidence_hit_ranks(docs_before, case, evidence) if docs_before else []
        ranks_after = _evidence_hit_ranks(docs_after, case, evidence) if docs_after else evidence_ranks
        pool_docs = docs_before or docs_deep
        whether_in_pool = any(
            doc_matches_gold(d, case, [ev])
            for ev in evidence
            for d in pool_docs
        ) if evidence else False
        row = {
            "id": cid,
            "question": q,
            "expected_route": case.get("expected_route"),
            "predicted_route": analysis.get("intent"),
            "expected_answer_mode": case.get("expected_answer_mode"),
            "predicted_answer_mode": analysis.get("answer_mode"),
            "expected_doc_types": expected_types,
            "top_sources": source_list,
            "top_doc_types": type_list,
            "route_ok": (not case.get("expected_route")) or analysis.get("intent") == case.get("expected_route"),
            "answer_mode_ok": (not case.get("expected_answer_mode")) or analysis.get("answer_mode") == case.get("expected_answer_mode"),
            "doc_type_accuracy": doc_type_accuracy(type_list, expected_types),
            "recall@k": _evidence_recall_at_k(docs_deep, case, evidence, k),
            "recall@5": _evidence_recall_at_k(docs_deep, case, evidence, 5),
            "recall@10": _evidence_recall_at_k(docs_deep, case, evidence, 10),
            "recall@20": _evidence_recall_at_k(docs_deep, case, evidence, 20),
            "precision@k": precision_at_k([i for i, _ in enumerate(docs)], hit_ids, k) if hit_ids else 0.0,
            "mrr": _evidence_mrr(evidence_ranks),
            "ndcg@k": ndcg_at_k(rels, k),
            "source_coverage": source_coverage([doc_source(d) for d in docs_deep], case.get("gold_sources") or []),
            "sop_boundary_ok": _sop_boundary_ok(case, docs_deep[:k]),
            "paper_to_sop_confusion_rate": _paper_sop_confusion(case, docs),
            "gold_hit": any(r.get("hit@5") for r in evidence_ranks) if evidence_ranks else any(hits),
            "gold_evidence": evidence_ranks,
            "candidate_pool_size": diag.get("candidate_pool_size", len(docs_before) or len(docs_deep)),
            "anchored_source_detected": diag.get("anchored_source_detected"),
            "anchored_source_hit_count": diag.get("anchored_source_hit_count", 0),
            "gold_hit_rank_before_rerank": {str(i): r.get("gold_hit_rank") for i, r in enumerate(ranks_before)},
            "gold_hit_rank_after_rerank": {str(i): r.get("gold_hit_rank") for i, r in enumerate(ranks_after)},
            "whether_gold_was_in_candidate_pool": whether_in_pool,
            "missing_gold_sources": missing_gold_sources,
            "latency_ms": latency_ms,
            "ok": True,
            "error": error,
        }
        rows.append(row)

    ok_rows = [r for r in rows if r.get("ok")]
    metrics = {
        "cases": len(rows),
        "successful_cases": len(ok_rows),
        "route_accuracy": avg(1.0 if r.get("route_ok") else 0.0 for r in ok_rows),
        "answer_mode_accuracy": avg(1.0 if r.get("answer_mode_ok") else 0.0 for r in ok_rows if r.get("expected_answer_mode")),
        "doc_type_accuracy": avg(float(r.get("doc_type_accuracy") or 0.0) for r in ok_rows),
        f"recall@{k}": avg(float(r.get("recall@k") or 0.0) for r in ok_rows),
        "recall@5": avg(float(r.get("recall@5") or 0.0) for r in ok_rows),
        "recall@10": avg(float(r.get("recall@10") or 0.0) for r in ok_rows),
        "recall@20": avg(float(r.get("recall@20") or 0.0) for r in ok_rows),
        f"precision@{k}": avg(float(r.get("precision@k") or 0.0) for r in ok_rows),
        "mrr": avg(float(r.get("mrr") or 0.0) for r in ok_rows),
        f"ndcg@{k}": avg(float(r.get("ndcg@k") or 0.0) for r in ok_rows),
        "source_coverage": avg(float(r.get("source_coverage") or 0.0) for r in ok_rows),
        "sop_boundary_accuracy": avg(1.0 if r.get("sop_boundary_ok") else 0.0 for r in ok_rows if r.get("sop_boundary_ok") is not None),
        "paper_to_sop_confusion_rate": avg(float(r.get("paper_to_sop_confusion_rate") or 0.0) for r in ok_rows),
        "avg_retrieval_latency_ms": avg(float(r.get("latency_ms") or 0.0) for r in ok_rows),
    }
    payload = {"metrics": metrics, "cases": rows, "warnings": warnings, "k": k}
    stamp = timestamp()
    json_path = report_dir / f"retrieval_eval_{stamp}.json"
    md_path = report_dir / f"retrieval_eval_{stamp}.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    payload["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    cases = payload["cases"]
    lines = ["# Retrieval Evaluation Report", ""]
    lines.append(markdown_table(["metric", "value"], [(k, round(v, 4) if isinstance(v, float) else v) for k, v in m.items()]))
    lines.extend(["", "## Per-question Results", ""])
    lines.append(
        markdown_table(
            ["id", "route", "expected", "recall@5", "recall@10", "recall@20", "mrr", "gold_hit", "confusion"],
            [
                (
                    r.get("id"),
                    r.get("predicted_route"),
                    r.get("expected_route"),
                    round(float(r.get("recall@5") or 0.0), 3),
                    round(float(r.get("recall@10") or 0.0), 3),
                    round(float(r.get("recall@20") or 0.0), 3),
                    round(float(r.get("mrr") or 0.0), 3),
                    r.get("gold_hit"),
                    round(float(r.get("paper_to_sop_confusion_rate") or 0.0), 3),
                )
                for r in cases
            ],
        )
    )
    lines.extend(["", "## Gold evidence ranks", ""])
    for r in cases:
        ev_rows = r.get("gold_evidence") or []
        if not ev_rows:
            continue
        lines.append(f"### `{r.get('id')}`")
        lines.append(
            markdown_table(
                ["section", "source", "gold_hit_rank", "hit@5", "hit@10", "hit@20"],
                [
                    (
                        e.get("section"),
                        e.get("source"),
                        e.get("gold_hit_rank"),
                        e.get("hit@5"),
                        e.get("hit@10"),
                        e.get("hit@20"),
                    )
                    for e in ev_rows
                ],
            )
        )
        lines.append("")
    failures = [r for r in cases if not r.get("ok") or not r.get("route_ok") or r.get("missing_gold_sources")]
    lines.extend(["", "## Paper / SOP 混淆分析", ""])
    lines.append(f"- 平均混淆率：`{m.get('paper_to_sop_confusion_rate', 0):.3f}`")
    lines.append(f"- SOP boundary accuracy：`{m.get('sop_boundary_accuracy', 0):.3f}`")
    lines.extend(["", "## 失败案例", ""])
    if failures:
        for r in failures:
            reason = r.get("error") or f"route_ok={r.get('route_ok')}, missing_gold_sources={r.get('missing_gold_sources')}"
            lines.append(f"- `{r.get('id')}`: {reason}")
    else:
        lines.append("- 未发现硬失败。")
    lines.extend(["", "## 改进建议", ""])
    lines.append("- 若 `doc_type_accuracy` 低，优先检查 query analysis 路由与 `doc_type` metadata。")
    lines.append("- 若 `recall@k` / `mrr` 低，优先比较 chunking、embedding 与 reranker benchmark。")
    if payload.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {w}" for w in payload["warnings"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RMN retrieval evaluation.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("-k", "--k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)
    payload = evaluate(args.questions, args.evidence, k=args.k, report_dir=report_dir)
    print(f"retrieval eval report: {payload['report_paths']['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
