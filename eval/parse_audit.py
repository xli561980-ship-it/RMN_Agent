#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare document parser outputs without touching Chroma or ingest records."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.experiment_utils import content_hash, write_jsonl  # noqa: E402
from ingest import (  # noqa: E402
    DATA_DIR,
    DATA_MANUALS_DIR,
    DATA_PAPERS_DIR,
    PAPER_CHUNK_OVERLAP,
    PAPER_CHUNK_SIZE,
    SOP_CHUNK_OVERLAP,
    SOP_CHUNK_SIZE,
    _build_markdown_header_splitter,
    _build_recursive_splitter,
    _docx_paragraphs_to_markdown,
    _pdfplumber_fallback_markdown_pages,
    _split_markdown_into_page_segments,
    assess_text_quality,
    hierarchical_chunk_markdown_segment,
    is_supported_ingest_file,
    parse_file_with_llama_parse,
    pdf_source_key,
)


ParserFn = Callable[[Path, str], list[Any]]


def _fallback_segments(path: Path, source_key: str) -> list[Any]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdfplumber_fallback_markdown_pages(path, source_key)
    if suffix == ".docx":
        md = _docx_paragraphs_to_markdown(path)
        if not md:
            raise RuntimeError("empty docx markdown")
        return _split_markdown_into_page_segments(md, source_key)
    raise ValueError(f"unsupported suffix: {path.suffix}")


def _doc_type_for_source(source_key: str) -> str:
    return "paper" if source_key.startswith("papers/") else "sop"


def _chunk_segments(path: Path, source_key: str, segments: Sequence[Any]) -> list[Any]:
    doc_type = _doc_type_for_source(source_key)
    role = "main_text" if doc_type == "paper" else "manual"
    recursive = (
        _build_recursive_splitter(PAPER_CHUNK_SIZE, PAPER_CHUNK_OVERLAP)
        if doc_type == "paper"
        else _build_recursive_splitter(SOP_CHUNK_SIZE, SOP_CHUNK_OVERLAP)
    )
    header_splitter = _build_markdown_header_splitter()
    meta = {
        "source": source_key,
        "doc_type": doc_type,
        "doc_role": role,
        "paper_title": path.stem.replace("_", " "),
        "project_id": path.stem.replace(" ", "_")[:120],
    }
    chunks: list[Any] = []
    for seg in segments:
        chunks.extend(
            hierarchical_chunk_markdown_segment(
                seg,
                header_splitter,
                recursive,
                global_file_metadata=meta,
            )
        )
    return chunks


def _quality_summary(texts: Sequence[str]) -> dict[str, Any]:
    if not texts:
        return {
            "avg_score": None,
            "low_quality_count": 0,
            "warnings": {},
            "avg_whitespace_ratio": None,
            "long_alpha_tokens": 0,
        }
    warnings = Counter()
    scores: list[float] = []
    whitespace: list[float] = []
    long_alpha_tokens = 0
    for text in texts:
        q = assess_text_quality(text)
        scores.append(float(q["score"]))
        whitespace.append(float(q["whitespace_ratio"]))
        long_alpha_tokens += int(q["long_alpha_tokens"])
        warning = str(q.get("warning") or "")
        for part in warning.split(","):
            if part:
                warnings[part] += 1
    return {
        "avg_score": round(mean(scores), 3) if scores else None,
        "low_quality_count": sum(1 for s in scores if s < 0.75),
        "warnings": dict(warnings),
        "avg_whitespace_ratio": round(mean(whitespace), 4) if whitespace else None,
        "long_alpha_tokens": long_alpha_tokens,
    }


def _markdown_heading_count(texts: Sequence[str]) -> int:
    return sum(
        1
        for text in texts
        for line in (text or "").splitlines()
        if line.lstrip().startswith("#")
    )


def run_parser(path: Path, source_key: str, parser_name: str, parser_fn: ParserFn) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        segments = parser_fn(path, source_key)
        if not segments:
            raise RuntimeError("parser returned no readable segments")
        chunks = _chunk_segments(path, source_key, segments)
        if not chunks:
            raise RuntimeError("parser produced no chunks")
        seg_texts = [getattr(seg, "page_content", "") or "" for seg in segments]
        chunk_texts = [getattr(chunk, "page_content", "") or "" for chunk in chunks]
        first_text = "\n\n".join(seg_texts[:2])
        return {
            "parser": parser_name,
            "ok": True,
            "seconds": round(time.perf_counter() - started, 3),
            "segment_count": len(segments),
            "chunk_count": len(chunks),
            "char_count": sum(len(x) for x in seg_texts),
            "heading_count": _markdown_heading_count(seg_texts),
            "segment_quality": _quality_summary(seg_texts),
            "chunk_quality": _quality_summary(chunk_texts),
            "first_content_hash": content_hash(first_text),
            "first_preview": " ".join(first_text.split())[:500],
            "error": None,
        }
    except Exception as exc:
        return {
            "parser": parser_name,
            "ok": False,
            "seconds": round(time.perf_counter() - started, 3),
            "segment_count": 0,
            "chunk_count": 0,
            "char_count": 0,
            "heading_count": 0,
            "segment_quality": {},
            "chunk_quality": {},
            "first_content_hash": "",
            "first_preview": "",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _parser_score(result: dict[str, Any]) -> float:
    if not result.get("ok"):
        return -1.0
    chunk_q = result.get("chunk_quality") or {}
    avg_score = float(chunk_q.get("avg_score") or 0.0)
    low_quality = int(chunk_q.get("low_quality_count") or 0)
    chunks = max(1, int(result.get("chunk_count") or 0))
    char_count = int(result.get("char_count") or 0)
    char_bonus = min(0.15, char_count / 100000.0)
    heading_bonus = min(0.05, int(result.get("heading_count") or 0) / 200.0)
    penalty = min(0.25, low_quality / chunks)
    return round(avg_score + char_bonus + heading_bonus - penalty, 4)


def compare_result_pair(fallback: dict[str, Any] | None, llama: dict[str, Any] | None) -> dict[str, Any]:
    if fallback is None or llama is None:
        return {"preferred": None, "reason": "single_parser_only"}
    if not fallback.get("ok") and not llama.get("ok"):
        return {
            "preferred": "both_failed",
            "fallback_score": _parser_score(fallback),
            "llama_score": _parser_score(llama),
            "char_delta_llama_minus_fallback": 0,
            "chunk_delta_llama_minus_fallback": 0,
            "heading_delta_llama_minus_fallback": 0,
        }
    if fallback.get("ok") and not llama.get("ok"):
        preferred = "fallback"
    elif llama.get("ok") and not fallback.get("ok"):
        preferred = "llama"
    else:
        preferred = None
    fs = _parser_score(fallback)
    ls = _parser_score(llama)
    if preferred is None:
        if abs(fs - ls) < 0.03:
            preferred = "tie"
        else:
            preferred = "llama" if ls > fs else "fallback"
    return {
        "preferred": preferred,
        "fallback_score": fs,
        "llama_score": ls,
        "char_delta_llama_minus_fallback": int(llama.get("char_count") or 0) - int(fallback.get("char_count") or 0),
        "chunk_delta_llama_minus_fallback": int(llama.get("chunk_count") or 0) - int(fallback.get("chunk_count") or 0),
        "heading_delta_llama_minus_fallback": int(llama.get("heading_count") or 0) - int(fallback.get("heading_count") or 0),
    }


def _scan_paths(*, recursive: bool) -> list[Path]:
    roots = [DATA_PAPERS_DIR, DATA_MANUALS_DIR]
    paths: list[Path] = []
    for root in roots:
        iterator = root.rglob("*") if recursive else root.iterdir()
        paths.extend(sorted(p for p in iterator if is_supported_ingest_file(p)))
    return sorted(paths, key=lambda p: pdf_source_key(p))


def _source_key_for_path(path: Path) -> str:
    try:
        return pdf_source_key(path)
    except Exception:
        try:
            return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()
        except ValueError:
            return path.name


def audit_paths(paths: Sequence[Path], *, parser: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        source_key = _source_key_for_path(path)
        results: dict[str, Any] = {}
        if parser in ("fallback", "both"):
            results["fallback"] = run_parser(path, source_key, "fallback", _fallback_segments)
        if parser in ("llama", "both"):
            results["llama"] = run_parser(path, source_key, "llama", parse_file_with_llama_parse)
        comparison = compare_result_pair(results.get("fallback"), results.get("llama"))
        rows.append(
            {
                "source": source_key,
                "path": str(path),
                "suffix": path.suffix.lower(),
                "doc_type": _doc_type_for_source(source_key),
                "results": results,
                "comparison": comparison,
            }
        )
        status = comparison.get("preferred") or next(iter(results))
        print(f"[audit] {source_key}: {status}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="*", help="Specific PDF/DOCX files to audit.")
    parser.add_argument("--parser", choices=["fallback", "llama", "both"], default="fallback")
    parser.add_argument("--recursive", action="store_true", help="When no paths are given, include nested data files.")
    parser.add_argument("--limit", type=int, default=None, help="Limit scanned files for a quick sample.")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "runs" / "parse_audit.jsonl")
    args = parser.parse_args()

    paths = [p for p in args.paths if is_supported_ingest_file(p)]
    if not paths:
        paths = _scan_paths(recursive=args.recursive)
    if args.limit is not None:
        paths = paths[: args.limit]
    if not paths:
        raise SystemExit("No supported PDF/DOCX paths found.")

    rows = audit_paths(paths, parser=args.parser)
    write_jsonl(args.out, rows)
    print(f"\nSaved parse audit: {args.out}")

    if args.parser == "both":
        counts = Counter((row.get("comparison") or {}).get("preferred") for row in rows)
        print("Preferred parser counts:")
        print(json.dumps(dict(counts), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
