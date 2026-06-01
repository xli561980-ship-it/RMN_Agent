#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate gold evidence rows against corpus_manifest and Chroma chunks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
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

WANG = (
    "papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels "
    "Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf"
)
IYISAN24 = (
    "papers/Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells "
    "in Microgels Using a 3D‐Printed Stimulation Device.pdf"
)
IYISAN25 = (
    "papers/Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic "
    "Differentiation of Single Stem Cells in 3D (1).pdf"
)
OZKALE = (
    "papers/Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with "
    "Dynamically Switchable Properties Would be a Great.pdf"
)
LITESIZER = "manuals/Litesizer 500 Instruction Manual .pdf"
GENERAL_LAB = "manuals/General Lab Rules MRBL-2.pdf"
BIO_S1 = "manuals/BioelectronicsLab-S1-SafetyBriefing.pdf"
MAG_STIR = "manuals/BA Magnetic stirrer_eng.pdf"
LASER_SOP = "manuals/Laser Safety and Alignment.pdf"
FUME_HOOD = "manuals/BA Fume hood_eng.pdf"
D2LC = "papers/d2lc00203e1.pdf"
FEM = (
    "papers/Investigating_Temperature_Strain_and_Force_Generation_in_Nanorobotic_"
    "Microgels_via_Finite_Element_Modeling.pdf"
)


def _load_manifest_sources(manifest_path: Path) -> dict[str, str]:
    if not manifest_path.is_file():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for source, entry in (payload.get("files") or {}).items():
        out[str(entry.get("source") or source)] = str(entry.get("doc_type") or "")
    return out


def _load_chroma_chunks_by_source() -> dict[str, list[dict[str, Any]]]:
    try:
        import chromadb
        from dotenv import load_dotenv
    except ImportError:
        return {}

    load_dotenv(ROOT / ".env")
    persist = Path(os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")).resolve()
    coll_name = os.getenv("CHROMA_COLLECTION_NAME", "lab_literature_rag")
    if not persist.is_dir():
        return {}

    client = chromadb.PersistentClient(path=str(persist))
    try:
        coll = client.get_collection(coll_name)
    except Exception:
        return {}

    result = coll.get(include=["documents", "metadatas"], limit=100_000)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for doc, meta in zip(result.get("documents") or [], result.get("metadatas") or []):
        source = str((meta or {}).get("source") or "")
        if not source:
            continue
        section = str(
            (meta or {}).get("section_title")
            or (meta or {}).get("Header 3")
            or (meta or {}).get("Header 2")
            or (meta or {}).get("Header 1")
            or ""
        )
        by_source.setdefault(source, []).append(
            {
                "text": doc or "",
                "doc_type": str((meta or {}).get("doc_type") or ""),
                "section": section,
                "page": (meta or {}).get("page"),
            }
        )
    return by_source


def _section_matches(ev_section: str, chunk_section: str) -> bool:
    ev = (ev_section or "").strip().casefold()
    sec = (chunk_section or "").strip().casefold()
    if not ev:
        return True
    if ev in sec or sec in ev:
        return True
    # Loose match for Chinese page headers vs English gold labels.
    if ev.startswith("第") and sec.startswith("第"):
        return True
    return False


def _keywords_match(needles: list[str], text: str) -> bool:
    if not needles:
        return True
    hay = (text or "").casefold()
    return any(str(n).casefold() in hay for n in needles if str(n).strip())


def check_evidence_row(
    row: dict[str, Any],
    *,
    manifest_sources: dict[str, str],
    chunks_by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source = str(row.get("source") or "")
    expected_type = str(row.get("doc_type") or "")
    section = str(row.get("section") or "")
    needles = list(row.get("must_contain_any") or [])
    issues: list[str] = []
    suggestions: list[str] = []

    if source not in manifest_sources:
        issues.append("source_missing")
        suggestions.append(f"Source not in corpus_manifest: `{source}`")
    elif expected_type and manifest_sources.get(source) != expected_type:
        issues.append("doc_type_mismatch")
        suggestions.append(
            f"Manifest doc_type for `{source}` is `{manifest_sources.get(source)}`, "
            f"gold row expects `{expected_type}`."
        )

    chunks = chunks_by_source.get(source) or []
    if source in manifest_sources and not chunks:
        issues.append("source_missing")
        suggestions.append(f"Source in manifest but no Chroma chunks found: `{source}`")

    section_hits = [c for c in chunks if _section_matches(section, c.get("section", ""))]
    keyword_pool = section_hits if section_hits else chunks
    keyword_ok = any(_keywords_match(needles, c.get("text", "")) for c in keyword_pool)

    if section and chunks and not section_hits:
        issues.append("section_missing")
        suggestions.append(
            f"No chunk section matches `{section}` for `{source}`; "
            "consider empty section or a substring from Chroma metadata."
        )

    if needles and chunks and not keyword_ok:
        issues.append("keywords_missing")
        suggestions.append(
            f"None of {needles!r} found in matching chunks for `{source}` / `{section}`."
        )

    if (
        section
        and chunks
        and section_hits
        and needles
        and not keyword_ok
        and "keywords_missing" not in issues
    ):
        issues.append("possible_label_too_strict")
        suggestions.append(
            "Section matches but keywords fail only in section-filtered chunks; "
            "keywords may exist elsewhere in the source."
        )

    status = "ok" if not issues else issues[0]
    return {
        "question_id": row.get("question_id"),
        "source": source,
        "section": section,
        "must_contain_any": needles,
        "status": status,
        "issues": issues,
        "suggestions": suggestions,
        "chunk_count": len(chunks),
        "section_match_count": len(section_hits),
    }


def run_alignment_check(
    questions_path: Path,
    evidence_path: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    questions = load_jsonl(questions_path)
    evidence_rows: list[dict[str, Any]] = []
    for qid, rows in load_gold_evidence(evidence_path).items():
        evidence_rows.extend(rows)

    manifest_sources = _load_manifest_sources(manifest_path or ROOT / "corpus_manifest.json")
    chunks_by_source = _load_chroma_chunks_by_source()

    checked: list[dict[str, Any]] = []
    for row in evidence_rows:
        checked.append(
            check_evidence_row(
                row,
                manifest_sources=manifest_sources,
                chunks_by_source=chunks_by_source,
            )
        )

    status_counts = Counter(r["status"] for r in checked)
    qids = {str(q.get("id")) for q in questions}
    orphan_evidence = sorted({r["question_id"] for r in checked if r["question_id"] not in qids})
    missing_evidence_qids = sorted(qids - {r["question_id"] for r in checked})

    return {
        "questions": len(questions),
        "evidence_rows": len(checked),
        "status_counts": dict(status_counts),
        "orphan_evidence_question_ids": orphan_evidence,
        "questions_without_evidence": missing_evidence_qids,
        "rows": checked,
        "chroma_sources_loaded": len(chunks_by_source),
        "manifest_sources": len(manifest_sources),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Gold Evidence Alignment Report",
        "",
        f"- Questions: **{payload['questions']}**",
        f"- Gold evidence rows: **{payload['evidence_rows']}**",
        f"- Manifest sources: **{payload['manifest_sources']}**",
        f"- Chroma sources loaded: **{payload['chroma_sources_loaded']}**",
        "",
        "## Status counts",
        "",
        markdown_table(
            ["status", "count"],
            sorted((k, v) for k, v in (payload.get("status_counts") or {}).items()),
        ),
        "",
    ]
    bad = [r for r in payload.get("rows") or [] if r.get("status") != "ok"]
    lines.extend(["## Issues", ""])
    if bad:
        lines.append(
            markdown_table(
                ["question_id", "source", "section", "status", "issues"],
                [
                    (
                        r.get("question_id"),
                        (str(r.get("source") or "")[:50] + "…")
                        if len(str(r.get("source") or "")) > 50
                        else r.get("source"),
                        r.get("section"),
                        r.get("status"),
                        ", ".join(r.get("issues") or []),
                    )
                    for r in bad
                ],
            )
        )
        lines.append("")
        lines.append("## Suggestions")
        lines.append("")
        for r in bad:
            for s in r.get("suggestions") or []:
                lines.append(f"- `{r.get('question_id')}` / `{r.get('source')}`: {s}")
    else:
        lines.append("_All gold evidence rows passed alignment checks._")

    if payload.get("orphan_evidence_question_ids"):
        lines.extend(["", "## Orphan evidence question_ids", ""])
        lines.extend(f"- `{x}`" for x in payload["orphan_evidence_question_ids"])
    if payload.get("questions_without_evidence"):
        lines.extend(["", "## Questions without gold evidence", ""])
        lines.extend(f"- `{x}`" for x in payload["questions_without_evidence"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check gold evidence alignment with corpus and Chroma.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--manifest", type=Path, default=ROOT / "corpus_manifest.json")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "eval" / "reports")
    args = parser.parse_args()

    report_dir = ensure_report_dir(args.report_dir)
    payload = run_alignment_check(args.questions, args.evidence, manifest_path=args.manifest)
    stamp = timestamp()
    json_path = report_dir / f"gold_evidence_alignment_{stamp}.json"
    md_path = report_dir / f"gold_evidence_alignment_{stamp}.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"gold evidence alignment report: {md_path}")
    non_ok = sum(1 for r in payload["rows"] if r.get("status") != "ok")
    return 1 if non_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
