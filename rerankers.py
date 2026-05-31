# -*- coding: utf-8 -*-
"""Optional rerankers for RMN Agent retrieval candidates."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from langchain_core.documents import Document

from fusion_scope import title_similarity_for_scope


PAPER_NUMERIC_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|°C|℃|h|hr|min|s|mM|µM|uM|mg|g|mL|ml|rpm|kPa|nm|µm|um)\b", re.I)
PAPER_METHOD_TERMS = (
    "method",
    "methods",
    "supplementary",
    "microfluidic",
    "fabrication",
    "protocol",
    "result",
    "concentration",
    "temperature",
    "crosslink",
    "材料",
    "方法",
    "结果",
    "浓度",
    "温度",
    "制备",
    "微流控",
)
SOP_TERMS = (
    "must",
    "should",
    "warning",
    "caution",
    "procedure",
    "operation",
    "calibration",
    "safety",
    "manual",
    "msds",
    "注意",
    "警告",
    "校准",
    "安全",
    "步骤",
    "必须",
    "手册",
)
GENERALIZATION_TERMS = (
    "all ",
    "every",
    "prove",
    "generaliz",
    "universal",
    "所有",
    "全部",
    "每种",
    "证明",
    "泛化",
    "有效",
)
HYBRID_SOP_BOOST_TERMS = (
    "sop",
    "manual",
    "safety",
    "安全",
    "规范",
    "手册",
    "操作",
    "限制",
    "msds",
    "warning",
    "caution",
    "calibration",
)


@dataclass
class RerankResult:
    docs: list[Document]
    provider: str = "none"
    warning: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def _analysis_intent(analysis: dict[str, Any]) -> str:
    return str((analysis or {}).get("intent") or "HYBRID")


def _is_generalization_question(query: str, analysis: dict[str, Any]) -> bool:
    q = (query or "").casefold()
    if any(term in q or term in (query or "") for term in GENERALIZATION_TERMS):
        return True
    claim = str((analysis or {}).get("claim_type") or "").casefold()
    return claim in {"insufficient_evidence", "generalization"}


def _target_scope_signals(analysis: dict[str, Any]) -> tuple[str, str, str]:
    a = analysis or {}
    return (
        str(a.get("paper_scope_paper_title") or "").strip(),
        str(a.get("paper_scope_source") or "").strip(),
        str(a.get("paper_scope_project_id") or "").strip(),
    )


def _doc_target_match(doc: Document, title_hint: str, source_hint: str, project_hint: str) -> float:
    meta = doc.metadata or {}
    score = 0.0
    stored_title = str(meta.get("paper_title") or "")
    stored_source = str(meta.get("source") or "")
    stored_pid = str(meta.get("project_id") or "")
    if source_hint and stored_source == source_hint:
        score += 2.5
    if project_hint and stored_pid == project_hint:
        score += 2.0
    if title_hint and stored_title:
        score += title_similarity_for_scope(title_hint, stored_title) * 2.0
    return score


def _generic_microgel_penalty(doc: Document, query: str, analysis: dict[str, Any]) -> float:
    meta = doc.metadata or {}
    if str(meta.get("doc_type") or "") != "paper":
        return 0.0
    title = str(meta.get("paper_title") or meta.get("source") or "").casefold()
    if "microgel" not in title and "alginate" not in title:
        return 0.0
    title_hint, source_hint, project_hint = _target_scope_signals(analysis)
    match = _doc_target_match(doc, title_hint, source_hint, project_hint)
    if match >= 1.0:
        return 0.0
    q = (query or "").casefold()
    if any(term in title for term in ("guideline", "review", "why ", "would be a great", "tool-box")):
        return 1.8
    if title_hint or source_hint or project_hint:
        return 1.4
    if any(term in q for term in ("safety", "sop", "安全", "限制", "实验")):
        return 0.8
    return 0.0


def _rule_score(doc: Document, query: str, analysis: dict[str, Any], *, path: str | None = None) -> float:
    meta = doc.metadata or {}
    text = (doc.page_content or "").casefold()
    dtype = str(meta.get("doc_type") or "")
    section_type = str(meta.get("section_type") or "").casefold()
    doc_role = str(meta.get("doc_role") or "").casefold()
    answer_mode = str((analysis or {}).get("answer_mode") or "").upper()
    intent = _analysis_intent(analysis)
    query_text = query or ""
    query_low = query_text.casefold()
    score = 0.0

    if intent == "PAPER_ONLY":
        score += 2.0 if dtype == "paper" else -1.0
    elif intent == "SOP_ONLY":
        score += 2.0 if dtype == "sop" else -1.0
    elif intent == "HYBRID":
        score += 0.3 if dtype in {"paper", "sop"} else 0.0
        if answer_mode == "OPERATIONAL" and dtype == "sop":
            score += 0.6
        if answer_mode == "SCHOLARLY" and dtype == "paper":
            score += 0.6
        if any(term in query_low or term in query_text for term in HYBRID_SOP_BOOST_TERMS) and dtype == "sop":
            score += 4.2
        if any(term in query_low or term in query_text for term in ("paper", "study", "论文", "文献", "参数", "结果")) and dtype == "paper":
            score += 0.6

    if dtype == "paper":
        if section_type in {"methods", "supplementary_methods", "results"}:
            score += 1.4
        if any(term in text for term in ("microfluidic", "fabrication", "supplementary methods", "protocol")):
            score += 0.9
        if PAPER_NUMERIC_RE.search(doc.page_content or ""):
            score += 0.8
        score += min(1.2, sum(1 for term in PAPER_METHOD_TERMS if term.casefold() in text) * 0.2)
        if doc_role == "supplementary_info" and "protocol" in query_low:
            score += 0.7
        score += _doc_target_match(doc, *_target_scope_signals(analysis))
        score -= _generic_microgel_penalty(doc, query, analysis)
        if _is_generalization_question(query, analysis) and section_type in {"introduction", "discussion", "limitations"}:
            score += 2.4
    elif dtype == "sop":
        if section_type in {"safety", "operation", "calibration", "protocol"}:
            score += 1.5
        if doc_role in {"manual", "sop", "safety"}:
            score += 0.6
        score += min(1.8, sum(1 for term in SOP_TERMS if term.casefold() in text) * 0.28)
        if "msds" in text or "material safety" in text:
            score += 0.5

    if path == "paper" and dtype != "paper":
        score -= 2.0
    if path == "sop" and dtype != "sop":
        score -= 2.0
    return score


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _copy_with_scores(
    doc: Document,
    *,
    original_rank: int,
    rule_score: float,
    rerank_score: float,
    final_rank: int,
    final_score: float | None = None,
) -> Document:
    meta = dict(doc.metadata or {})
    meta["original_rank"] = original_rank
    meta["rule_score"] = round(rule_score, 4)
    meta["rerank_score"] = round(rerank_score, 4)
    meta["final_rank"] = final_rank
    if final_score is not None:
        meta["final_score"] = round(final_score, 4)
    return Document(page_content=doc.page_content, metadata=meta)


def _score_candidates(
    docs: Sequence[Document],
    query: str,
    analysis: dict[str, Any],
    *,
    path: str,
) -> list[tuple[float, float, int, Document]]:
    weight = float(os.getenv("RERANK_RULE_WEIGHT", "0.25"))
    rrf_k = int(os.getenv("RERANK_RRF_K", "60"))
    scored: list[tuple[float, float, int, Document]] = []
    for idx, doc in enumerate(docs):
        rs = _rule_score(doc, query, analysis, path=path)
        base = _rrf(idx + 1, rrf_k)
        final = base + weight * rs
        scored.append((final, rs, idx, doc))
    scored.sort(key=lambda x: (-x[0], x[2]))
    return scored


def _effective_hybrid_minimums(limit: int, min_paper: int, min_sop: int) -> tuple[int, int]:
    limit = max(1, limit)
    min_paper = max(0, min_paper)
    min_sop = max(0, min_sop)
    if min_paper + min_sop <= limit:
        return min_paper, min_sop
    if min_paper and min_sop:
        paper_eff = max(1, round(limit * min_paper / (min_paper + min_sop)))
        paper_eff = min(paper_eff, limit - 1)
        return paper_eff, limit - paper_eff
    if min_paper:
        return min(limit, min_paper), 0
    return 0, min(limit, min_sop)


def _select_hybrid_final_context(
    scored: Sequence[tuple[float, float, int, Document]],
    *,
    limit: int,
    min_paper: int,
    min_sop: int,
) -> list[Document]:
    min_paper, min_sop = _effective_hybrid_minimums(limit, min_paper, min_sop)
    papers = [(s, rs, idx, d) for s, rs, idx, d in scored if (d.metadata or {}).get("doc_type") == "paper"]
    sops = [(s, rs, idx, d) for s, rs, idx, d in scored if (d.metadata or {}).get("doc_type") == "sop"]
    selected: list[Document] = []
    selected_ids: set[int] = set()

    for bucket, need in ((papers, min_paper), (sops, min_sop)):
        have = 0
        for item in bucket:
            if have >= need:
                break
            doc = item[3]
            if id(doc) in selected_ids:
                continue
            selected.append(doc)
            selected_ids.add(id(doc))
            have += 1

    for item in sorted(scored, key=lambda x: (-x[0], x[2])):
        if len(selected) >= limit:
            break
        doc = item[3]
        if id(doc) in selected_ids:
            continue
        selected.append(doc)
        selected_ids.add(id(doc))
    score_lookup = {id(item[3]): item[0] for item in scored}
    selected.sort(key=lambda d: (-score_lookup.get(id(d), 0.0),))
    return selected[:limit]


def _enforce_hybrid_balance(docs: list[Document], original: Sequence[Document]) -> list[Document]:
    min_paper = int(os.getenv("HYBRID_MIN_PAPER_CHUNKS", "2"))
    min_sop = int(os.getenv("HYBRID_MIN_SOP_CHUNKS", "2"))
    limit = len(docs) or int(os.getenv("FINAL_CONTEXT_K", "8"))
    weight = float(os.getenv("RERANK_RULE_WEIGHT", "0.25"))
    rrf_k = int(os.getenv("RERANK_RRF_K", "60"))
    scored: list[tuple[float, float, int, Document]] = []
    for idx, doc in enumerate(original):
        rs = _rule_score(doc, "", {"intent": "HYBRID"})
        scored.append((_rrf(idx + 1, rrf_k) + weight * rs, rs, idx, doc))
    for idx, doc in enumerate(docs):
        if id(doc) not in {id(x[3]) for x in scored}:
            rs = _rule_score(doc, "", {"intent": "HYBRID"})
            scored.append((_rrf(idx + 1, rrf_k) + weight * rs, rs, idx, doc))
    return _select_hybrid_final_context(scored, limit=limit, min_paper=min_paper, min_sop=min_sop)


def _finalize_ranked_docs(scored: Sequence[tuple[float, float, int, Document]]) -> list[Document]:
    out: list[Document] = []
    for final_idx, (final_score, rs, original_idx, doc) in enumerate(scored, start=1):
        out.append(
            _copy_with_scores(
                doc,
                original_rank=original_idx + 1,
                rule_score=rs,
                rerank_score=final_score,
                final_rank=final_idx,
                final_score=final_score,
            )
        )
    return out


def rule_rerank_path(
    docs: Sequence[Document],
    query: str,
    analysis: dict[str, Any],
    *,
    path: str,
    final_k: int | None = None,
) -> RerankResult:
    start = time.perf_counter()
    limit = final_k or int(os.getenv("FINAL_CONTEXT_K", str(len(docs) or 8)))
    scored = _score_candidates(docs, query, analysis, path=path)
    ranked = _finalize_ranked_docs(scored[:limit])
    return RerankResult(docs=ranked, provider="rule", latency_ms=(time.perf_counter() - start) * 1000, metadata={"path": path})


def rule_rerank(docs: Sequence[Document], query: str, analysis: dict[str, Any], *, final_k: int | None = None) -> RerankResult:
    start = time.perf_counter()
    limit = final_k or int(os.getenv("FINAL_CONTEXT_K", str(len(docs) or 8)))
    scored = _score_candidates(docs, query, analysis, path="mixed")
    if _analysis_intent(analysis) == "HYBRID":
        ranked_raw = _select_hybrid_final_context(
            scored,
            limit=limit,
            min_paper=int(os.getenv("HYBRID_MIN_PAPER_CHUNKS", "2")),
            min_sop=int(os.getenv("HYBRID_MIN_SOP_CHUNKS", "2")),
        )
        out = []
        lookup = {id(doc): (final, rs, idx) for final, rs, idx, doc in scored}
        for final_idx, doc in enumerate(ranked_raw, start=1):
            final_score, rs, original_idx = lookup.get(id(doc), (0.0, 0.0, final_idx - 1))
            out.append(
                _copy_with_scores(
                    doc,
                    original_rank=original_idx + 1,
                    rule_score=rs,
                    rerank_score=final_score,
                    final_rank=final_idx,
                    final_score=final_score,
                )
            )
        return RerankResult(docs=out, provider="rule", latency_ms=(time.perf_counter() - start) * 1000)

    out = _finalize_ranked_docs(scored[:limit])
    return RerankResult(docs=out, provider="rule", latency_ms=(time.perf_counter() - start) * 1000)


def rerank_dual_path(
    paper_docs: Sequence[Document],
    sop_docs: Sequence[Document],
    query: str,
    analysis: dict[str, Any],
    *,
    paper_limit: int | None = None,
    sop_limit: int | None = None,
) -> tuple[list[Document], list[Document], RerankResult]:
    """Rerank paper and SOP paths separately, then return path-ordered lists."""
    start = time.perf_counter()
    intent = _analysis_intent(analysis)
    top_n = int(os.getenv("RERANK_TOP_N", "20"))
    paper_k = paper_limit or int(os.getenv("FINAL_CONTEXT_K", "8"))
    sop_k = sop_limit or int(os.getenv("FINAL_CONTEXT_K", "8"))

    paper_candidates = list(paper_docs[:top_n])
    sop_candidates = list(sop_docs[:top_n])

    if intent == "PAPER_ONLY":
        paper_out = rule_rerank_path(paper_candidates, query, analysis, path="paper", final_k=paper_k).docs
        meta = {"mode": "paper_only", "paper_count": len(paper_out), "sop_count": 0}
        return paper_out, [], RerankResult(docs=paper_out, provider="rule", latency_ms=(time.perf_counter() - start) * 1000, metadata=meta)

    if intent == "SOP_ONLY":
        sop_out = rule_rerank_path(sop_candidates, query, analysis, path="sop", final_k=sop_k).docs
        meta = {"mode": "sop_only", "paper_count": 0, "sop_count": len(sop_out)}
        return [], sop_out, RerankResult(docs=sop_out, provider="rule", latency_ms=(time.perf_counter() - start) * 1000, metadata=meta)

    min_paper = int(os.getenv("HYBRID_MIN_PAPER_CHUNKS", "2"))
    min_sop = int(os.getenv("HYBRID_MIN_SOP_CHUNKS", "2"))
    paper_scored = _score_candidates(paper_candidates, query, analysis, path="paper")
    sop_scored = _score_candidates(sop_candidates, query, analysis, path="sop")

    paper_out = _finalize_ranked_docs(paper_scored[: max(paper_k, min_paper)])
    sop_out = _finalize_ranked_docs(sop_scored[: max(sop_k, min_sop)])

    merged_scored = [(s, rs, idx, d) for s, rs, idx, d in paper_scored] + [
        (s, rs, idx + len(paper_scored), d) for s, rs, idx, d in sop_scored
    ]
    _select_hybrid_final_context(
        merged_scored,
        limit=max(paper_k + sop_k, min_paper + min_sop),
        min_paper=min_paper,
        min_sop=min_sop,
    )

    meta = {
        "mode": "dual_path",
        "paper_count": len(paper_out),
        "sop_count": len(sop_out),
        "min_paper": min_paper,
        "min_sop": min_sop,
    }
    return (
        paper_out,
        sop_out,
        RerankResult(
            docs=paper_out + sop_out,
            provider="rule",
            latency_ms=(time.perf_counter() - start) * 1000,
            metadata=meta,
        ),
    )


def cross_encoder_rerank(docs: Sequence[Document], query: str, *, model_name: str, final_k: int | None = None) -> RerankResult:
    start = time.perf_counter()
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception as exc:
        return RerankResult(list(docs[: final_k or len(docs)]), provider="cross_encoder", warning=f"sentence-transformers unavailable: {exc}")
    try:
        model = CrossEncoder(model_name)
        pairs = [(query, d.page_content or "") for d in docs]
        scores = list(model.predict(pairs))
    except Exception as exc:
        return RerankResult(list(docs[: final_k or len(docs)]), provider="cross_encoder", warning=f"cross-encoder rerank failed: {exc}")
    scored = sorted(zip(scores, range(len(docs)), docs), key=lambda x: (-float(x[0]), x[1]))
    out = [
        _copy_with_scores(doc, original_rank=idx + 1, rule_score=0.0, rerank_score=float(score), final_rank=rank)
        for rank, (score, idx, doc) in enumerate(scored[: final_k or len(docs)], start=1)
    ]
    return RerankResult(out, provider="cross_encoder", latency_ms=(time.perf_counter() - start) * 1000)


def rerank_documents(docs: Sequence[Document], query: str, analysis: dict[str, Any], *, provider: str | None = None, final_k: int | None = None) -> RerankResult:
    provider = (provider or os.getenv("RERANKER_PROVIDER", "none")).strip().lower()
    top_n = int(os.getenv("RERANK_TOP_N", "20"))
    candidates = list(docs[:top_n])
    if provider in ("", "none"):
        return RerankResult(list(docs[: final_k or len(docs)]), provider="none")
    if provider == "rule":
        return rule_rerank(candidates, query, analysis, final_k=final_k)
    if provider in ("cross_encoder", "bge"):
        model = os.getenv("BGE_RERANKER_MODEL" if provider == "bge" else "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        return cross_encoder_rerank(candidates, query, model_name=model, final_k=final_k)
    if provider == "cohere_optional":
        if not os.getenv("COHERE_API_KEY"):
            return RerankResult(list(docs[: final_k or len(docs)]), provider=provider, warning="COHERE_API_KEY not set; skipped.")
    if provider == "llm_optional":
        return RerankResult(list(docs[: final_k or len(docs)]), provider=provider, warning="LLM reranker is reserved and disabled by default.")
    return RerankResult(list(docs[: final_k or len(docs)]), provider=provider, warning=f"Unsupported reranker provider: {provider}")
