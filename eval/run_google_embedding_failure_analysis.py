#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Failure analysis for Google embedding retrieval eval (top-20 deep dive)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import (  # noqa: E402
    doc_matches_gold,
    doc_section,
    doc_source,
    doc_type,
    flatten_docs,
    load_gold_evidence,
    load_jsonl,
    markdown_table,
)
from eval.metrics import recall_at_k  # noqa: E402
from rag_core import fusion_prepare  # noqa: E402

CAUSE_LABELS = [
    "query_language_mismatch",
    "right_source_wrong_section",
    "wrong_source",
    "wrong_doc_type",
    "hybrid_quota_issue",
    "chunking_boundary_issue",
    "gold_label_mismatch",
]

DEFAULT_OUT = ROOT / "eval" / "reports" / "google_embedding_failure_analysis.md"


def _latest_retrieval_eval_json() -> Path:
    report_dir = ROOT / "eval" / "reports"
    candidates = sorted(report_dir.glob("retrieval_eval_*.json"), reverse=True)
    return candidates[0] if candidates else Path()


SOURCE_EVAL = _latest_retrieval_eval_json()


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _snippet(text: str, limit: int = 180) -> str:
    one = " ".join((text or "").split())
    return one[: limit - 3] + "..." if len(one) > limit else one


def _evidence_hit(doc, case: dict[str, Any], ev: dict[str, Any]) -> bool:
    return doc_matches_gold(doc, case, [ev])


def _source_in_docs(source: str, docs: list[Any]) -> bool:
    return any(doc_source(d) == source for d in docs)


def _docs_from_source(source: str, docs: list[Any]) -> list[Any]:
    return [d for d in docs if doc_source(d) == source]


def _must_contain_partial(ev: dict[str, Any], docs: list[Any]) -> bool:
    """True when source appears but no chunk contains all must_contain needles."""
    source = str(ev.get("source") or "")
    needles = [str(x).casefold() for x in (ev.get("must_contain_any") or []) if str(x).strip()]
    if not source or not needles:
        return False
    source_docs = _docs_from_source(source, docs)
    if not source_docs:
        return False
    for doc in source_docs:
        text = (doc.page_content or "").casefold()
        if all(n in text for n in needles):
            return False
    return True


def _classify_evidence_miss(
    case: dict[str, Any],
    ev: dict[str, Any],
    docs5: list[Any],
    docs20: list[Any],
    analysis: dict[str, Any],
    *,
    hit5: bool,
    hit20: bool,
) -> list[str]:
    causes: list[str] = []
    q = str(case.get("question") or "")
    ev_source = str(ev.get("source") or "")
    ev_type = str(ev.get("doc_type") or "")
    ev_section = str(ev.get("section") or "")
    expected_route = str(case.get("expected_route") or "")
    predicted_route = str(analysis.get("intent") or "")
    expected_types = set(case.get("expected_doc_types") or [])
    top5_types = [doc_type(d) for d in docs5]
    top20_sources = {doc_source(d) for d in docs20}

    if hit5:
        return causes

    if ev_type and expected_types and ev_type not in expected_types:
        causes.append("gold_label_mismatch")

    if expected_route == "HYBRID":
        paper_n = sum(1 for d in docs20 if doc_type(d) == "paper")
        sop_n = sum(1 for d in docs20 if doc_type(d) == "sop")
        if paper_n == 0 or sop_n == 0:
            causes.append("hybrid_quota_issue")
        if predicted_route != "HYBRID":
            causes.append("hybrid_quota_issue")

    if expected_types and top5_types:
        wrong_type_ratio = sum(1 for t in top5_types if t not in expected_types) / len(top5_types)
        if wrong_type_ratio >= 0.4:
            causes.append("wrong_doc_type")

    if _has_cjk(q) and ev_source.startswith("papers/"):
        causes.append("query_language_mismatch")

    if ev_source and ev_source not in top20_sources:
        causes.append("wrong_source")
    elif ev_source and _must_contain_partial(ev, docs20):
        causes.append("chunking_boundary_issue")
        section_docs = _docs_from_source(ev_source, docs20)
        section_hits = [
            d
            for d in section_docs
            if ev_section.casefold() in doc_section(d).casefold() or doc_section(d).casefold() in ev_section.casefold()
        ]
        if section_hits and not any(_evidence_hit(d, case, ev) for d in section_hits):
            causes.append("right_source_wrong_section")
    elif ev_source and _source_in_docs(ev_source, docs20):
        causes.append("right_source_wrong_section")

    if str(case.get("id") or "") == "missing_evidence" and "所有" in q:
        gold_sources = [str(s) for s in (case.get("gold_sources") or []) if str(s).startswith("papers/")]
        if len(gold_sources) <= 1:
            causes.append("gold_label_mismatch")

    if not causes:
        causes.append("wrong_source" if ev_source not in top20_sources else "right_source_wrong_section")
    return list(dict.fromkeys(causes))


def _chunk_row(rank: int, doc: Any, case: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [_evidence_hit(doc, case, ev) for ev in evidence]
    matched = [evidence[i] for i, h in enumerate(hits) if h]
    return {
        "rank": rank,
        "source": doc_source(doc),
        "doc_type": doc_type(doc),
        "section": doc_section(doc) or "(none)",
        "gold_match": bool(matched),
        "matched_sections": [str(ev.get("section") or "") for ev in matched],
        "snippet": _snippet(doc.page_content or ""),
    }


def analyze_case(
    case: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    k_eval: int,
    k_deep: int,
) -> dict[str, Any]:
    qid = str(case.get("id") or "")
    # Request extra depth so interleaved paper/SOP flattening still yields k_deep slots.
    bundle = fusion_prepare(str(case.get("question") or ""), k=max(k_deep, k_deep + 10))
    analysis = bundle.get("analysis") or {}
    docs20 = flatten_docs(bundle, k=k_deep)
    docs5 = docs20[:k_eval]

    ev_rows: list[dict[str, Any]] = []
    miss_evidence: list[dict[str, Any]] = []
    for ev in evidence:
        hit5 = any(_evidence_hit(d, case, ev) for d in docs5)
        hit20 = any(_evidence_hit(d, case, ev) for d in docs20)
        if not hit5:
            miss_evidence.append(ev)
        issue = None
        if not hit5:
            issue = "ranking_issue" if hit20 else "recall_issue"
        causes = _classify_evidence_miss(case, ev, docs5, docs20, analysis, hit5=hit5, hit20=hit20) if not hit5 else []
        ev_rows.append(
            {
                "section": ev.get("section"),
                "source": ev.get("source"),
                "must_contain_any": ev.get("must_contain_any"),
                "hit@5": hit5,
                "hit@20": hit20,
                "issue_type": issue,
                "causes": causes,
            }
        )

    hit_ids5 = [i for i, d in enumerate(docs5) if doc_matches_gold(d, case, evidence)]
    recall5 = recall_at_k(hit_ids5, list(range(len(docs5))), k_eval) if docs5 else 0.0
    is_miss = bool(miss_evidence)

    chunk_rows = [_chunk_row(i + 1, d, case, evidence) for i, d in enumerate(docs20)]
    issue_types = Counter(r["issue_type"] for r in ev_rows if r.get("issue_type"))
    cause_counter = Counter(c for r in ev_rows for c in r.get("causes") or [])

    return {
        "id": qid,
        "question": case.get("question"),
        "expected_route": case.get("expected_route"),
        "predicted_route": analysis.get("intent"),
        "recall@5": recall5,
        "is_recall_miss": is_miss,
        "evidence_rows": ev_rows,
        "top20_chunks": chunk_rows,
        "issue_type_counts": dict(issue_types),
        "cause_counts": dict(cause_counter),
        "missing_gold_at_5": [r for r in ev_rows if not r["hit@5"]],
    }


def render_markdown(
    *,
    source_eval: Path,
    source_payload: dict[str, Any],
    k_eval: int,
    k_deep: int,
    cases: list[dict[str, Any]],
    miss_cases: list[dict[str, Any]],
    global_causes: Counter,
    global_issues: Counter,
    index_note: str,
) -> str:
    orig_cases = {str(c.get("id")): c for c in source_payload.get("cases") or []}
    lines = [
        "# Google Embedding Failure Analysis",
        "",
        f"- Source eval: `{source_eval.name}`",
        f"- Embedding provider: `google` / `{os.getenv('GOOGLE_EMBEDDING_MODEL', 'gemini-embedding-001')}`",
        f"- Eval @k: `{k_eval}`; deep dive @k: `{k_deep}`",
        f"- Index note: {index_note}",
        "",
        "## Summary",
        "",
        f"- Total questions: **{len(cases)}**",
        f"- Recall miss questions (@{k_eval}, gold-evidence level): **{len(miss_cases)}**",
        "",
        "### Original eval snapshot (@k=5 from source JSON)",
        "",
        markdown_table(
            ["id", f"recall@{k_eval}", "gold_hit", "missing_gold_sources"],
            [
                (
                    cid,
                    round(float((orig_cases.get(cid) or {}).get("recall@k") or 0), 2),
                    (orig_cases.get(cid) or {}).get("gold_hit"),
                    len((orig_cases.get(cid) or {}).get("missing_gold_sources") or []),
                )
                for cid in [c["id"] for c in cases]
            ],
        ),
        "",
        "> Deep-dive re-runs use the restored Google index (362 files). Query routing may vary slightly between runs because `analyze_query` uses an LLM.",
        "",
        "### Issue type (missed gold evidence items)",
        "",
        markdown_table(
            ["issue_type", "count"],
            [(k, v) for k, v in sorted(global_issues.items())],
        )
        if global_issues
        else "_No missed evidence items._",
        "",
        "### Root-cause tags (missed gold evidence items; multi-label)",
        "",
        markdown_table(
            ["cause", "count", "share"],
            [
                (cause, global_causes.get(cause, 0), f"{(global_causes.get(cause, 0) / max(1, sum(global_causes.values()))):.1%}")
                for cause in CAUSE_LABELS
                if global_causes.get(cause, 0)
            ],
        )
        if global_causes
        else "_No cause tags._",
        "",
        "## Per-question Analysis",
        "",
    ]

    for row in miss_cases:
        lines.extend(
            [
                f"### `{row['id']}`",
                "",
                f"**Question:** {row['question']}",
                "",
                f"- Expected route: `{row.get('expected_route')}` | Predicted: `{row.get('predicted_route')}`",
                f"- recall@{k_eval}: `{row.get('recall@5', 0):.2f}`",
                "",
                "#### Missed gold evidence",
                "",
            ]
        )
        lines.append(
            markdown_table(
                ["section", "source", "hit@5", "hit@20", "issue_type", "causes"],
                [
                    (
                        r.get("section"),
                        Path(str(r.get("source") or "")).name,
                        r.get("hit@5"),
                        r.get("hit@20"),
                        r.get("issue_type"),
                        ", ".join(r.get("causes") or []),
                    )
                    for r in row.get("missing_gold_at_5") or []
                ],
            )
        )
        lines.extend(["", f"#### Top-{k_deep} retrieved chunks", ""])
        lines.append(
            markdown_table(
                ["rank", "source", "doc_type", "section", "gold_match", "snippet"],
                [
                    (
                        c["rank"],
                        Path(c["source"]).name,
                        c["doc_type"],
                        c["section"],
                        c["gold_match"],
                        c["snippet"],
                    )
                    for c in row.get("top20_chunks") or []
                ],
            )
        )
        lines.append("")

    if not miss_cases:
        lines.append("_No recall misses at eval k; all gold evidence found in top-{k_eval}._".format(k_eval=k_eval))

    lines.extend(
        [
            "",
            "## Manual review: `missing_evidence`",
            "",
            "- **Scheme A (applied):** corpus-level generalization question; gold evidence spans Wang 2025, İyisan 2024/2025, and Özkale 2024 microgel/stem-cell papers.",
            "- Expected answer: evidence does **not** prove efficacy across **all** stem cell types; each paper covers specific cell types or conditions.",
            "- Do **not** force `paper_scope_source` anchor in the default pipeline; `forced_gold_source_anchor` remains eval ablation only.",
            "- Alternative **Scheme B:** rewrite to “Wang 2025 这篇论文是否证明…” if testing single-paper reasoning.",
            "",
        ]
    )

    lines.extend(
        [
            "## Method",
            "",
            f"1. Reload questions from `eval/golden_questions.jsonl` and gold spans from `eval/gold_evidence.jsonl`.",
            f"2. Treat a question as recall miss when any gold evidence item is absent from top-{k_eval}.",
            f"3. Re-run `fusion_prepare(..., k={k_deep})` and inspect top-{k_deep} chunks.",
            f"4. If gold evidence appears in top-{k_deep} but not top-{k_eval} → **ranking_issue**; otherwise **recall_issue**.",
            "5. Cause tags are heuristic and may co-occur on one missed evidence item.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Google embedding retrieval failure analysis.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--source-eval", type=Path, default=SOURCE_EVAL)
    parser.add_argument("--k-eval", type=int, default=5)
    parser.add_argument("--k-deep", type=int, default=20)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    os.environ.setdefault("EMBEDDING_PROVIDER", "google")

    questions = load_jsonl(args.questions)
    evidence_by_q = load_gold_evidence(args.evidence)

    processed_n = 0
    pf = ROOT / "processed_files.json"
    if pf.is_file():
        try:
            processed_n = len(json.loads(pf.read_text(encoding="utf-8")).get("files") or {})
        except json.JSONDecodeError:
            processed_n = 0
    index_note = f"`processed_files.json` has {processed_n} files indexed (expect ~363 for full Google corpus)."

    analyzed: list[dict[str, Any]] = []
    for case in questions:
        qid = str(case.get("id") or "")
        analyzed.append(
            analyze_case(
                case,
                evidence_by_q.get(qid, []),
                k_eval=args.k_eval,
                k_deep=args.k_deep,
            )
        )

    miss_cases = [r for r in analyzed if r.get("is_recall_miss")]
    global_issues: Counter = Counter()
    global_causes: Counter = Counter()
    for row in miss_cases:
        for ev in row.get("evidence_rows") or []:
            if ev.get("issue_type"):
                global_issues[ev["issue_type"]] += 1
            for c in ev.get("causes") or []:
                global_causes[c] += 1

    source_payload: dict[str, Any] = {}
    if args.source_eval.is_file():
        source_payload = json.loads(args.source_eval.read_text(encoding="utf-8"))

    md = render_markdown(
        source_eval=args.source_eval,
        source_payload=source_payload,
        k_eval=args.k_eval,
        k_deep=args.k_deep,
        cases=analyzed,
        miss_cases=miss_cases,
        global_causes=global_causes,
        global_issues=global_issues,
        index_note=index_note,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"failure analysis report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
