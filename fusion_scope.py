# -*- coding: utf-8 -*-
"""
Paper-path Chroma metadata filters and k heuristics (no heavy deps; easy to unit test).

`paper_scope_paper_title` is intentionally not applied as a Chroma where-clause (exact match
was brittle). It is returned as a soft hint for Python-side reranking in rag_core.
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _ui_paper_scope_is_active(ui: str) -> bool:
    """Sidebar placeholder values (e.g. '(None — all papers)') must not become a Chroma `source` filter."""
    s = (ui or "").strip()
    if not s:
        return False
    low = s.lower()
    if low.startswith("(none"):
        return False
    # Legacy Chinese UI sentinel, if ever passed from API/session
    if s.startswith("（"):
        return False
    return True


def build_paper_scope_chroma_filter(
    analysis: Dict[str, Any],
    paper_source_scope: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    """
    Build extra Chroma metadata conditions for the paper path (excluding doc_type).
    UI `paper_source_scope` (path under data/, e.g. papers/a.pdf) wins over analyzer fields.

    Returns (extra_filter_or_none, paper_scope_is_locked, paper_title_soft_hint).
    `paper_title` is never written into the Chroma filter (exact equality caused empty hits);
    the third value carries `paper_scope_paper_title` for fuzzy reranking downstream.
    """
    out: Dict[str, Any] = {}
    tit = (analysis.get("paper_scope_paper_title") or "").strip()
    title_hint: Optional[str] = tit or None
    ui = (paper_source_scope or "").strip()
    if _ui_paper_scope_is_active(ui):
        out["source"] = ui
        return out, True, title_hint
    s = (analysis.get("paper_scope_source") or "").strip()
    if s:
        out["source"] = s
    pid = (analysis.get("paper_scope_project_id") or "").strip()
    if pid:
        out["project_id"] = pid
    if not out:
        return None, False, title_hint
    return out, True, title_hint


def paper_retrieval_pool_k(base_k: int, title_soft_hint: Optional[str]) -> int:
    """Larger candidate pool when a title hint is present so reranking can disambiguate papers."""
    bk = max(int(base_k), 1)
    if not (title_soft_hint or "").strip():
        return bk
    return min(max(bk * 5, 30), 100)


def _normalize_title_text(s: str) -> str:
    t = (s or "").strip().casefold()
    t = re.sub(r"\s+", " ", t)
    return t


def title_similarity_for_scope(a: str, b: str) -> float:
    """
    Fuzzy similarity between two titles (punctuation / case / whitespace tolerant).
    Used for reranking retrieved chunks; exported for unit tests.
    """
    na, nb = _normalize_title_text(a), _normalize_title_text(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return max(difflib.SequenceMatcher(None, na, nb).ratio(), 0.82)
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _doc_title_relevance(doc: Document, title_hint: str, paper_query: str) -> float:
    meta = doc.metadata or {}
    stored = str(meta.get("paper_title") or "")
    s_hint = title_similarity_for_scope(title_hint, stored)
    pq = (paper_query or "").strip()
    if not pq:
        return s_hint
    s_q = title_similarity_for_scope(pq, stored)
    return max(s_hint, s_q * 0.92)


def rerank_paper_docs_by_title_hint(
    docs: List[Document],
    title_hint: str,
    paper_query: str,
    k: int,
) -> Tuple[List[Document], str]:
    """
    Re-order similarity hits using metadata title vs. analyzer hint / paper query.
    If nothing matches strongly enough, fall back to the original embedding order (first k).
    """
    hint = (title_hint or "").strip()
    kk = max(int(k), 1)
    if not hint or not docs:
        return docs[:kk], ""

    scored: List[Tuple[float, int, Document]] = []
    for i, d in enumerate(docs):
        scored.append((_doc_title_relevance(d, hint, paper_query), i, d))
    max_s = max((t[0] for t in scored), default=0.0)
    # Below this, title signal is noise — keep vector retrieval order to avoid empty/wrong trims.
    fallback_below = 0.22
    if max_s < fallback_below:
        logger.info(
            "paper_title soft-hint weak (max=%.3f vs stored titles); using embedding order",
            max_s,
        )
        return docs[:kk], (
            "Title hint matched stored `paper_title` weakly; kept embedding-ranked hits "
            "(re-ingest with ingest.py embeds a `[DOC]` line into each paper chunk for better title recall)."
        )

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t[2] for t in scored[:kk]], ""


def effective_paper_k(base_k: int, answer_mode: str, paper_locked: bool) -> int:
    """Slightly higher recall for scholarly or locked single-paper retrieval."""
    bk = max(int(base_k), 1)
    if paper_locked:
        return max(bk, 8)
    if (answer_mode or "").upper() == "SCHOLARLY":
        return max(bk, 8)
    return bk
