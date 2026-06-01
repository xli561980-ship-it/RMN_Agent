# -*- coding: utf-8 -*-
"""Shared helpers for RMN Agent evaluation and benchmark scripts."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

from langchain_core.documents import Document

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "eval" / "reports"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_report_dir(path: Path | None = None) -> Path:
    out = path or DEFAULT_REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    return out


def corpus_preflight() -> list[str]:
    """Return human-readable warnings when local corpus/index is missing."""
    warnings: list[str] = []
    data_docs = list((ROOT / "data" / "papers").glob("*.pdf")) + list((ROOT / "data" / "papers").glob("*.docx"))
    data_docs += list((ROOT / "data" / "manuals").glob("*.pdf")) + list((ROOT / "data" / "manuals").glob("*.docx"))
    if not data_docs:
        warnings.append("未发现真实 paper/SOP 文件：data/papers 与 data/manuals 目前没有 PDF/DOCX。")
    if not (ROOT / "corpus_manifest.json").is_file():
        warnings.append("未发现 corpus_manifest.json；看起来还没有完成可复现入库。")
    if not (ROOT / "chroma_db").is_dir():
        warnings.append("未发现默认 chroma_db；benchmark 指标可能只是空库/未入库状态。")
    return warnings


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        raise FileNotFoundError(f"找不到 JSONL 文件：{path}")
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{i}: invalid JSONL: {exc}") from exc
        if "required_sources" in row and "gold_sources" not in row:
            row["gold_sources"] = row.get("required_sources") or []
        row.setdefault("expected_doc_types", [])
        row.setdefault("gold_sources", [])
        row.setdefault("gold_sections", [])
        row.setdefault("requires_sop", row.get("expected_route") == "SOP_ONLY")
        rows.append(row)
    return rows


def load_gold_evidence(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        return {}
    rows = load_jsonl(path)
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        qid = str(row.get("question_id") or "").strip()
        if qid:
            out.setdefault(qid, []).append(row)
    return out


def doc_source(doc: Document) -> str:
    return str((doc.metadata or {}).get("source") or "").strip()


def doc_type(doc: Document) -> str:
    return str((doc.metadata or {}).get("doc_type") or "").strip()


def doc_section(doc: Document) -> str:
    meta = doc.metadata or {}
    return str(meta.get("section_title") or meta.get("Header 3") or meta.get("Header 2") or meta.get("Header 1") or "").strip()


def flatten_docs(bundle: dict[str, Any], *, k: int | None = None) -> list[Document]:
    paper = list(bundle.get("paper_docs") or [])
    sop = list(bundle.get("sop_docs") or [])
    docs: list[Document] = []
    max_len = max(len(paper), len(sop))
    for i in range(max_len):
        if i < len(paper):
            docs.append(paper[i])
        if i < len(sop):
            docs.append(sop[i])
    return docs if k is None else docs[:k]


def doc_matches_gold(doc: Document, case: dict[str, Any], evidence: Sequence[dict[str, Any]]) -> bool:
    source = doc_source(doc)
    dtype = doc_type(doc)
    text = (doc.page_content or "").casefold()
    section = doc_section(doc).casefold()
    gold_sources = {str(x) for x in case.get("gold_sources") or []}
    if source and source in gold_sources:
        return True
    for ev in evidence:
        ev_source = str(ev.get("source") or "")
        if ev_source and source != ev_source:
            continue
        ev_type = str(ev.get("doc_type") or "")
        if ev_type and dtype != ev_type:
            continue
        ev_section = str(ev.get("section") or "").casefold()
        if ev_section and ev_section not in section:
            continue
        needles = [str(x).casefold() for x in (ev.get("must_contain_any") or []) if str(x).strip()]
        if needles and not any(n in text for n in needles):
            continue
        return True
    return False


def has_local_gold_source(case: dict[str, Any], docs: Sequence[Document]) -> tuple[bool, list[str]]:
    expected = [str(x) for x in (case.get("gold_sources") or []) if str(x).strip()]
    if not expected:
        return True, []
    sources = {doc_source(d) for d in docs}
    missing = [s for s in expected if s not in sources]
    return not missing, missing


def avg(values: Iterable[float]) -> float:
    vals = list(values)
    return mean(vals) if vals else 0.0


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def cell(x: Any) -> str:
        text = str(x)
        return text.replace("|", "\\|").replace("\n", "<br>")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(x) for x in row) + " |" for row in rows)
    return "\n".join(lines)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def numeric_claim_without_citation_count(answer: str) -> int:
    pattern = re.compile(r"\d+(?:\.\d+)?\s*(?:%|°C|℃|h|hr|min|s|mM|mg|g|mL|ml|rpm|kPa|nm|µm|um)\b", re.I)
    count = 0
    for line in (answer or "").splitlines():
        if "[Source:" not in line and pattern.search(line):
            count += 1
    return count
