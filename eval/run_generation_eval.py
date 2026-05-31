#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run generation evaluation and citation checks for RMN Agent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from citation_validator import validate_answer_citations  # noqa: E402
from eval.eval_utils import (  # noqa: E402
    avg,
    doc_source,
    doc_type,
    ensure_report_dir,
    flatten_docs,
    load_jsonl,
    markdown_table,
    numeric_claim_without_citation_count,
    timestamp,
    write_json,
)
from rag_core import build_fusion_rag_chain, fusion_prepare  # noqa: E402


def _llm_available() -> tuple[bool, str]:
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        return False, "缺少 GOOGLE_API_KEY 或 GEMINI_API_KEY，已跳过 generation eval。"
    return True, ""


def evaluate(questions_path: Path, *, k: int, report_dir: Path) -> dict[str, Any]:
    cases = load_jsonl(questions_path)
    available, reason = _llm_available()
    stamp = timestamp()
    if not available:
        payload = {"skipped": True, "reason": reason, "cases": [], "metrics": {}}
        json_path = report_dir / f"generation_eval_{stamp}.json"
        md_path = report_dir / f"generation_eval_{stamp}.md"
        write_json(json_path, payload)
        md_path.write_text(f"# Generation Evaluation Report\n\n{reason}\n", encoding="utf-8")
        payload["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
        return payload

    rows: list[dict[str, Any]] = []
    for case in cases:
        q = str(case.get("question") or "")
        cid = str(case.get("id") or "")
        try:
            bundle = fusion_prepare(q, k=k)
            chain = build_fusion_rag_chain(temperature=0.0, system_prompt=bundle["fusion_system_prompt"])
            answer = chain.invoke({"question": bundle["user_question"]})
            validation = validate_answer_citations(
                answer,
                paper_docs=bundle.get("paper_docs") or [],
                sop_docs=bundle.get("sop_docs") or [],
            )
            docs = flatten_docs(bundle, k=k)
            rows.append(
                {
                    "id": cid,
                    "question": q,
                    "analyzer_result": bundle.get("analysis") or {},
                    "retrieved_sources": [{"source": doc_source(d), "doc_type": doc_type(d)} for d in docs],
                    "generated_answer": answer,
                    "citation_validation": {
                        "ok": validation.ok,
                        "cited_hints": validation.cited_hints,
                        "unknown_hints": validation.unknown_hints,
                        "missing_citation_numeric_claims": validation.missing_citation_numeric_claims,
                        "allowed_hint_count": validation.allowed_hint_count,
                    },
                    "expected_route": case.get("expected_route"),
                    "expected_doc_types": case.get("expected_doc_types") or [],
                    "answer_generated": bool((answer or "").strip()),
                    "citation_present": "[Source:" in (answer or ""),
                    "unknown_citation_count": len(validation.unknown_hints),
                    "numeric_claim_without_citation_count": numeric_claim_without_citation_count(answer),
                    "insufficient_evidence_flag": any(
                        phrase in (answer or "").lower()
                        for phrase in ("insufficient evidence", "not enough evidence", "无法确认", "证据不足", "未提供")
                    ),
                    "ok": True,
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append({"id": cid, "question": q, "ok": False, "error": str(exc)})

    ok_rows = [r for r in rows if r.get("ok")]
    metrics = {
        "cases": len(rows),
        "successful_cases": len(ok_rows),
        "answer_generated_rate": avg(1.0 if r.get("answer_generated") else 0.0 for r in ok_rows),
        "citation_present_rate": avg(1.0 if r.get("citation_present") else 0.0 for r in ok_rows),
        "unknown_citation_rate": avg(1.0 if r.get("unknown_citation_count") else 0.0 for r in ok_rows),
        "numeric_claim_without_citation_count": sum(int(r.get("numeric_claim_without_citation_count") or 0) for r in ok_rows),
        "insufficient_evidence_flag_rate": avg(1.0 if r.get("insufficient_evidence_flag") else 0.0 for r in ok_rows),
    }
    payload = {"skipped": False, "metrics": metrics, "cases": rows, "k": k}
    json_path = report_dir / f"generation_eval_{stamp}.json"
    md_path = report_dir / f"generation_eval_{stamp}.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    payload["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Generation Evaluation Report", ""]
    lines.append(markdown_table(["metric", "value"], [(k, v) for k, v in payload["metrics"].items()]))
    lines.extend(["", "## Case Summary", ""])
    lines.append(
        markdown_table(
            ["id", "generated", "citation", "unknown citations", "numeric no cite", "error"],
            [
                (
                    r.get("id"),
                    r.get("answer_generated"),
                    r.get("citation_present"),
                    r.get("unknown_citation_count", 0),
                    r.get("numeric_claim_without_citation_count", 0),
                    r.get("error", ""),
                )
                for r in payload["cases"]
            ],
        )
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RMN generation evaluation.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("-k", "--k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)
    payload = evaluate(args.questions, k=args.k, report_dir=report_dir)
    print(payload.get("reason") or f"generation eval report: {payload['report_paths']['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
