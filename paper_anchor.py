# -*- coding: utf-8 -*-
"""Paper anchor extraction and corpus-backed source resolution."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fusion_scope import title_similarity_for_scope

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "corpus_manifest.json"

_DEICTIC_PAPER_RE = re.compile(
    r"(这篇论文|该论文|此论文|参考论文|论文里|论文中的|论文参数|paper's|this paper|the paper|that paper|parameters in the paper)",
    flags=re.IGNORECASE,
)

_ENTITY_TITLE_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bwang\s*2025\b", re.I), "Wang 2025 Photothermally Powered"),
    (re.compile(r"\bwang\b.*2025|\b2025\b.*\bwang\b", re.I), "Wang 2025"),
    (re.compile(r"\bwang\b", re.I), "Wang Photothermally Powered 3D Microgels"),
    (re.compile(r"photothermally\s+powered", re.I), "Photothermally Powered 3D Microgels"),
    (re.compile(r"mechanically\s+regulate", re.I), "Photothermally Powered 3D Microgels Mechanically Regulate"),
    (re.compile(r"3d\s+microgels?", re.I), "3D Microgels"),
    (re.compile(r"microfluidic\s+fabrication", re.I), "microfluidic fabrication"),
)

_ENTITY_EXTRACT_RE = re.compile(
    r"(\bWang\b|Wang\s*2025|Photothermally\s+Powered|3D\s+Microgels|mechanically\s+regulate|microfluidic\s+fabrication)",
    flags=re.IGNORECASE,
)

_CORPUS_LEVEL_RE = re.compile(
    r"(这些文献|多篇|语料|corpus|literature|papers?\s+(show|prove|demonstrate)|"
    r"所有(?:干细胞|细胞)类型|across\s+all\s+stem\s+cell)",
    flags=re.IGNORECASE,
)

_STRONG_ANCHOR_RE = re.compile(
    r"(wang\s*2025|\bwang\b|photothermally\s+powered|mechanically\s+regulate)",
    flags=re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _load_paper_catalog() -> list[dict[str, str]]:
    if not MANIFEST_PATH.is_file():
        return []
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows: list[dict[str, str]] = []
    for source, entry in (payload.get("files") or {}).items():
        if str(entry.get("doc_type") or "") != "paper":
            continue
        meta = entry.get("metadata") or {}
        rows.append(
            {
                "source": str(entry.get("source") or source),
                "paper_title": str(meta.get("paper_title") or ""),
                "project_id": str(meta.get("project_id") or ""),
            }
        )
    return rows


def extract_paper_entities(text: str) -> list[str]:
    found: list[str] = []
    for match in _ENTITY_EXTRACT_RE.finditer(text or ""):
        token = match.group(1).strip()
        if token and token not in found:
            found.append(token)
    return found


def extract_title_hints(text: str) -> list[str]:
    hints: list[str] = []
    for pattern, hint in _ENTITY_TITLE_HINTS:
        if pattern.search(text or "") and hint not in hints:
            hints.append(hint)
    if references_paper_deictically(text) and re.search(r"microgel", text, re.I):
        if "Photothermally Powered 3D Microgels" not in hints:
            hints.append("Photothermally Powered 3D Microgels")
    return hints


def is_corpus_level_question(text: str) -> bool:
    return bool(_CORPUS_LEVEL_RE.search(text or ""))


def has_strong_paper_anchor_signal(text: str) -> bool:
    return bool(_STRONG_ANCHOR_RE.search(text or ""))


def resolve_source_candidates(title_hint: str, *, min_similarity: float = 0.35) -> list[tuple[float, str]]:
    hint = (title_hint or "").strip()
    if not hint:
        return []
    scored: list[tuple[float, str]] = []
    for row in _load_paper_catalog():
        title = row.get("paper_title") or ""
        sim = title_similarity_for_scope(hint, title)
        if sim >= min_similarity:
            scored.append((sim, row["source"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def resolve_sources_by_title_hint(title_hint: str, *, min_similarity: float = 0.35) -> list[str]:
    return [src for _, src in resolve_source_candidates(title_hint, min_similarity=min_similarity)]


def resolve_best_source(title_hint: str, source_hint: str = "") -> Optional[str]:
    if (source_hint or "").strip():
        return source_hint.strip()
    candidates = resolve_source_candidates(title_hint)
    return candidates[0][1] if candidates else None


def pick_best_resolved_hint(title_hints: list[str]) -> tuple[Optional[str], Optional[str], float]:
    best_hint = ""
    best_source: Optional[str] = None
    best_score = -1.0
    for hint in title_hints:
        candidates = resolve_source_candidates(hint)
        if not candidates:
            continue
        score, source = candidates[0]
        if score > best_score:
            best_score = score
            best_source = source
            best_hint = hint
    if best_source is None:
        return None, None, 0.0
    return best_hint, best_source, best_score


def references_paper_deictically(text: str) -> bool:
    return bool(_DEICTIC_PAPER_RE.search(text or ""))


def enrich_analysis_with_paper_anchor(
    analysis: dict[str, Any],
    user_query: str,
    *,
    paper_anchor: Optional[str] = None,
) -> dict[str, Any]:
    """Merge rule-based anchor signals into analyzer output."""
    out = dict(analysis)
    text = user_query or ""
    anchor = (paper_anchor or "").strip()
    entities = list(out.get("entities") or [])
    for ent in extract_paper_entities(text):
        if ent not in entities:
            entities.append(ent)
    out["entities"] = entities

    title_hints = extract_title_hints(text)
    if title_hints and not (out.get("paper_scope_paper_title") or "").strip():
        out["paper_scope_paper_title"] = title_hints[0]
    if title_hints:
        out["paper_scope_source_hint"] = title_hints[0]

    if anchor and (references_paper_deictically(text) or not (out.get("paper_scope_source") or "").strip()):
        out["paper_scope_source"] = anchor
        out["paper_scope_source_hint"] = anchor

    source = str(out.get("paper_scope_source") or "").strip()
    title = str(out.get("paper_scope_paper_title") or out.get("paper_scope_source_hint") or "").strip()
    corpus_level = is_corpus_level_question(text)
    soft = (os.getenv("ANCHORED_SOURCE_SOFT_MATCH", "true") or "").lower() not in ("0", "false", "no")
    if soft and not source and title_hints and not corpus_level:
        best_hint, resolved, _ = pick_best_resolved_hint(title_hints)
        if resolved:
            out["paper_scope_source_hint"] = best_hint or title_hints[0]
            if references_paper_deictically(text) or has_strong_paper_anchor_signal(text):
                out["paper_scope_source"] = resolved

    if source and not out.get("paper_scope_source_hint"):
        out["paper_scope_source_hint"] = source
    return out


def anchored_source_from_analysis(analysis: dict[str, Any]) -> str:
    return str(analysis.get("paper_scope_source") or "").strip()


def anchored_title_hint_from_analysis(analysis: dict[str, Any]) -> str:
    return str(
        analysis.get("paper_scope_paper_title")
        or analysis.get("paper_scope_source_hint")
        or ""
    ).strip()
