#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run RMN Agent golden questions and save a comparable JSONL experiment log."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.experiment_utils import (  # noqa: E402
    RUNS_DIR,
    load_config,
    load_jsonl,
    make_run_id,
    sources_from_docs,
    summarize_doc,
    summarize_run,
    temporary_env,
    write_jsonl,
)
from rag_core import fusion_prepare, stream_fusion_rag_from_bundle  # noqa: E402
from citation_validator import validate_answer_citations  # noqa: E402


def _bundle_retrieval(bundle: dict[str, Any]) -> dict[str, Any]:
    paper_docs = [
        summarize_doc(doc, rank=i, path_name="paper")
        for i, doc in enumerate(bundle.get("paper_docs") or [], start=1)
    ]
    sop_docs = [
        summarize_doc(doc, rank=i, path_name="sop")
        for i, doc in enumerate(bundle.get("sop_docs") or [], start=1)
    ]
    sources = sorted(sources_from_docs(paper_docs) | sources_from_docs(sop_docs))
    return {
        "paper_docs": paper_docs,
        "sop_docs": sop_docs,
        "sources": sources,
    }


def _metrics_for_case(
    *,
    case: dict[str, Any],
    bundle: dict[str, Any],
    retrieval: dict[str, Any],
    latency_sec: float,
) -> dict[str, Any]:
    analysis = bundle.get("analysis") or {}
    expected_route = str(case.get("expected_route") or "").strip()
    got_route = str(analysis.get("intent") or "").strip()
    required_sources = [str(x) for x in (case.get("required_sources") or [])]
    got_sources = set(retrieval.get("sources") or [])
    missing = [src for src in required_sources if src not in got_sources]
    route_ok = (got_route == expected_route) if expected_route else None
    required_hit = (not missing) if required_sources else None
    paper_docs = retrieval.get("paper_docs") or []
    sop_docs = retrieval.get("sop_docs") or []
    ok = (route_ok is not False) and (required_hit is not False)
    return {
        "ok": ok,
        "route_ok": route_ok,
        "expected_route": expected_route or None,
        "got_route": got_route or None,
        "required_sources": required_sources,
        "required_sources_hit": required_hit,
        "missing_required_sources": missing,
        "paper_doc_count": len(paper_docs),
        "sop_doc_count": len(sop_docs),
        "distinct_source_count": len(got_sources),
        "latency_sec": round(latency_sec, 3),
    }


def run_case(
    case: dict[str, Any],
    *,
    run_id: str,
    config: dict[str, Any],
    generate_answer: bool,
) -> dict[str, Any]:
    case_id = str(case.get("id") or "no_id")
    question = str(case.get("question") or "")
    k = int(config.get("k", 5))
    strict_protocol_appendix = config.get("strict_protocol_appendix")
    if strict_protocol_appendix is not None:
        if isinstance(strict_protocol_appendix, str):
            strict_protocol_appendix = strict_protocol_appendix.lower() not in ("0", "false", "no")
        else:
            strict_protocol_appendix = bool(strict_protocol_appendix)

    started = time.perf_counter()
    try:
        bundle = fusion_prepare(
            question,
            k=k,
            strict_protocol_appendix=strict_protocol_appendix,
        )
        answer = None
        citation_validation = None
        if generate_answer:
            answer = "".join(stream_fusion_rag_from_bundle(bundle))
            cv = validate_answer_citations(
                answer,
                paper_docs=bundle.get("paper_docs") or [],
                sop_docs=bundle.get("sop_docs") or [],
            )
            citation_validation = {
                "ok": cv.ok,
                "allowed_hint_count": cv.allowed_hint_count,
                "cited_hints": cv.cited_hints,
                "unknown_hints": cv.unknown_hints,
                "missing_citation_numeric_claims": cv.missing_citation_numeric_claims,
            }
        latency = time.perf_counter() - started
        retrieval = _bundle_retrieval(bundle)
        return {
            "run_id": run_id,
            "case_id": case_id,
            "question": question,
            "case": case,
            "config": config,
            "analysis": bundle.get("analysis") or {},
            "retrieval": retrieval,
            "paper_retrieval_note": bundle.get("paper_retrieval_note"),
            "paper_scope_locked": bundle.get("paper_scope_locked"),
            "protocol_rigor_appendix": bundle.get("protocol_rigor_appendix"),
            "answer": answer,
            "citation_validation": citation_validation,
            "metrics": _metrics_for_case(
                case=case,
                bundle=bundle,
                retrieval=retrieval,
                latency_sec=latency,
            ),
            "error": None,
        }
    except Exception as exc:
        latency = time.perf_counter() - started
        expected_route = str(case.get("expected_route") or "").strip() or None
        return {
            "run_id": run_id,
            "case_id": case_id,
            "question": question,
            "case": case,
            "config": config,
            "analysis": {},
            "retrieval": {"paper_docs": [], "sop_docs": [], "sources": []},
            "answer": None,
            "citation_validation": None,
            "metrics": {
                "ok": False,
                "route_ok": False if expected_route else None,
                "expected_route": expected_route,
                "got_route": None,
                "required_sources": [str(x) for x in (case.get("required_sources") or [])],
                "required_sources_hit": False if case.get("required_sources") else None,
                "missing_required_sources": [str(x) for x in (case.get("required_sources") or [])],
                "paper_doc_count": 0,
                "sop_doc_count": 0,
                "distinct_source_count": 0,
                "latency_sec": round(latency, 3),
            },
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def run_experiment(
    *,
    questions_path: Path,
    config_path: Path | None,
    run_id: str | None,
    out_dir: Path,
    generate_answer: bool,
    max_cases: int | None,
) -> tuple[Path, list[dict[str, Any]]]:
    config = load_config(config_path)
    rid = run_id or make_run_id(str(config.get("name") or "run"))
    cases = load_jsonl(questions_path)
    if max_cases is not None:
        cases = cases[:max_cases]
    if not cases:
        raise SystemExit(f"No cases found in {questions_path}")

    rows: list[dict[str, Any]] = []
    with temporary_env(dict(config.get("env") or {})):
        for case in cases:
            row = run_case(case, run_id=rid, config=config, generate_answer=generate_answer)
            rows.append(row)
            metrics = row.get("metrics") or {}
            status = "PASS" if metrics.get("ok") else "FAIL"
            print(
                f"[{status}] {row.get('case_id')} route={metrics.get('got_route')!r} "
                f"paper={metrics.get('paper_doc_count')} sop={metrics.get('sop_doc_count')} "
                f"latency={metrics.get('latency_sec')}s"
            )
            if row.get("error"):
                print(f"       error: {row['error']['type']}: {row['error']['message']}")
            missing = metrics.get("missing_required_sources") or []
            if missing:
                print(f"       missing required sources: {missing}")

    out_path = out_dir / f"{rid}.jsonl"
    write_jsonl(out_path, rows)
    summary = summarize_run(rows)
    print("\nSummary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nSaved run: {out_path}")
    return out_path, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--config", type=Path, default=ROOT / "eval" / "configs" / "baseline.json")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--generate-answer", action="store_true", help="Also call the generation model and validate citations.")
    parser.add_argument("--max-cases", type=int, default=None, help="Only run the first N cases.")
    args = parser.parse_args()
    run_experiment(
        questions_path=args.questions,
        config_path=args.config,
        run_id=args.run_id,
        out_dir=args.out_dir,
        generate_answer=args.generate_answer,
        max_cases=args.max_cases,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
