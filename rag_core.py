# -*- coding: utf-8 -*-
"""
rag_core.py — Fusion RAG：意图解析 → 双路过滤检索（Paper / SOP）→ 融合生成

流程：
1. 调用 `query_analyzer.analyze_query` 得到 intent、answer_mode、paper_scope_* 与双路检索 query。
2. 按 intent 向 Chroma 发起带 `doc_type` 及可选 scope（source / project_id）过滤的检索；`paper_scope_paper_title` 仅作题录软重排，不参与 Chroma 精确 where。
3. 对论文路结果保留「补充材料 SI」增强检索（同 project_id；与 scope 不冲突）。
4. 按 `answer_mode` 用 `fusion_prompts.compose_fusion_system_prompt` 组装 System Prompt 后生成。
"""

from __future__ import annotations

import os
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from fusion_prompts import compose_fusion_system_prompt
from fusion_scope import (
    build_paper_scope_chroma_filter,
    effective_paper_k,
    paper_retrieval_pool_k,
    rerank_paper_docs_by_title_hint,
)
from ingest import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR, build_embeddings
from paper_anchor import (
    anchored_source_from_analysis,
    anchored_title_hint_from_analysis,
    resolve_best_source,
    resolve_sources_by_title_hint,
)
from query_analyzer import analyze_query, normalize_analysis
from rerankers import rerank_documents, rerank_dual_path

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)

SI_BOOST_KEYWORDS: Tuple[str, ...] = (
    "method",
    "protocol",
    "reagent",
    "reagents",
    "material",
    "materials",
    "procedure",
    "buffer",
    "concentration",
    "dilution",
    "recipe",
    "步骤",
    "试剂",
    "方案",
)

DEFAULT_RETRIEVER_K = 5
SI_EXTRA_K = 6
SI_TOP_AFTER_RANK = 3
_LEXICAL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+\-_/]{1,}|[\u4e00-\u9fff]{2,}")

# Protocol-rigor path: higher paper recall (env-tunable). Used when appendix rules activate.
def _paper_protocol_k_bounds() -> Tuple[int, int]:
    return (
        max(1, int(os.getenv("PAPER_PROTOCOL_K_MIN", "12"))),
        max(1, int(os.getenv("PAPER_PROTOCOL_K_MAX", "20"))),
    )


def _multi_source_supplement_params() -> Tuple[int, int]:
    return (
        max(1, int(os.getenv("PAPER_MULTI_SOURCE_SUPPLEMENT_K", "5"))),
        max(0, int(os.getenv("PAPER_MULTI_SOURCE_MAX_ADD", "12"))),
    )


_PROTOCOL_TERMS_EN: Tuple[str, ...] = (
    "protocol",
    "synthesis",
    "synthetic",
    "fabrication",
    "prepare",
    "preparation",
    "replicate",
    "replication",
    "step",
    "steps",
    "procedure",
    "workflow",
    "fabricate",
    "assemble",
    "how to make",
    "how to prepare",
)
_PROTOCOL_TERMS_ZH: Tuple[str, ...] = (
    "步骤",
    "制备",
    "流程",
    "复现",
    "合成",
    "方案",
    "操作",
    "实验方案",
    "工艺",
)


def _question_triggers_protocol_rigor(text: str) -> bool:
    t = (text or "").lower()
    if any(x in t for x in _PROTOCOL_TERMS_EN):
        return True
    raw = text or ""
    return any(z in raw for z in _PROTOCOL_TERMS_ZH)


def _question_suggests_cross_paper(text: str) -> bool:
    t = (text or "").lower()
    raw = text or ""
    if any(x in t for x in ("compare", "comparison", "versus", "differs", "difference")):
        return True
    return any(z in raw for z in ("对比", "差异", "比较", "两篇", "多篇"))


def _strict_protocol_appendix_from_env() -> bool:
    return (os.getenv("STRICT_PROTOCOL_APPENDIX", "true") or "").lower() not in ("0", "false", "no")


def _protocol_rigor_should_activate(
    analysis: Dict[str, Any],
    question: str,
    *,
    strict_protocol_appendix: bool,
) -> bool:
    if not strict_protocol_appendix:
        return False
    if (analysis.get("intent") or "") == "SOP_ONLY":
        return False
    if analysis.get("requires_full_protocol") is True:
        return True
    return _question_triggers_protocol_rigor(question)


def _bump_paper_k_for_protocol(base_pk: int, protocol_active: bool, question: str) -> int:
    if not protocol_active:
        return base_pk
    kmin, kmax = _paper_protocol_k_bounds()
    bumped = max(base_pk, kmin)
    if _question_suggests_cross_paper(question):
        bumped = max(bumped, min(16, kmax))
    return min(bumped, kmax)


def _summarize_retrieved_paper_sources(docs: Sequence[Document]) -> str:
    srcs: List[str] = []
    seen: Set[str] = set()
    for d in docs:
        m = d.metadata or {}
        s = str(m.get("source") or "").strip()
        if s and s not in seen:
            seen.add(s)
            srcs.append(s)
    if not srcs:
        return ""
    preview = ", ".join(srcs[:24])
    extra = f" (+{len(srcs) - 24} more)" if len(srcs) > 24 else ""
    return f"Distinct paper `source` values in this bundle ({len(srcs)}): {preview}{extra}."


def _supplement_multi_source_paper_chunks(
    vectorstore: Chroma,
    paper_docs: List[Document],
    paper_query: str,
    paper_extra_filter: Optional[Dict[str, Any]],
) -> List[Document]:
    """
    When ≥2 paper sources appear in hits and the bundle is not locked to a single `source`,
    pull a few extra chunks per source so parallel full-protocol sections have coverage.
    """
    if not paper_docs or not (paper_query or "").strip():
        return paper_docs
    if paper_extra_filter and str(paper_extra_filter.get("source") or "").strip():
        return paper_docs
    srcs: List[str] = []
    seen_src: Set[str] = set()
    for d in paper_docs:
        s = str((d.metadata or {}).get("source") or "").strip()
        if s and s not in seen_src:
            seen_src.add(s)
            srcs.append(s)
    if len(srcs) < 2:
        return paper_docs
    per_k, max_add = _multi_source_supplement_params()
    per_k = max(2, per_k)
    budget_per_source = max(1, max_add // len(srcs)) if max_add else per_k
    seen_fp: Set[Tuple] = {_doc_fingerprint(d) for d in paper_docs}
    out = list(paper_docs)
    added = 0
    for sk in srcs:
        if added >= max_add:
            break
        merged_extra = {**(paper_extra_filter or {}), "source": sk}
        extra_batch = _similarity_search_filtered(
            vectorstore, paper_query, per_k, "paper", merged_extra
        )
        got_this_source = 0
        for d in extra_batch:
            if added >= max_add or got_this_source >= budget_per_source:
                break
            fp = _doc_fingerprint(d)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            out.append(d)
            added += 1
            got_this_source += 1
    return out


def get_vectorstore() -> Chroma:
    """加载已持久化的 Chroma 集合（需先运行 ingest.py）。"""
    emb = build_embeddings()
    return Chroma(
        collection_name=CHROMA_COLLECTION_NAME,
        persist_directory=str(CHROMA_PERSIST_DIR),
        embedding_function=emb,
    )


def _doc_fingerprint(d: Document) -> Tuple:
    m = d.metadata or {}
    return (m.get("source"), m.get("page"), (d.page_content or "")[:120])


def _retrieval_mode() -> str:
    return (os.getenv("RAG_RETRIEVAL_MODE") or "hybrid").strip().lower()


def _hybrid_lexical_weight() -> float:
    try:
        return max(0.0, min(2.0, float(os.getenv("HYBRID_LEXICAL_WEIGHT", "0.35"))))
    except ValueError:
        return 0.35


def _hybrid_lexical_pool_limit() -> int:
    try:
        return max(100, int(os.getenv("HYBRID_LEXICAL_POOL_LIMIT", "20000")))
    except ValueError:
        return 20000


def _lexical_tokens(text: str) -> List[str]:
    toks = [t.casefold() for t in _LEXICAL_TOKEN_RE.findall(text or "")]
    stop = {"the", "and", "for", "with", "that", "this", "what", "how", "are", "was", "were"}
    return [t for t in toks if t not in stop]


def _doc_lexical_score(query_tokens: Set[str], doc: Document) -> float:
    if not query_tokens:
        return 0.0
    meta = doc.metadata or {}
    title_source = " ".join(
        str(meta.get(k) or "")
        for k in ("paper_title", "source", "project_id", "experiment_keywords", "doc_role")
    ).casefold()
    body = (doc.page_content or "").casefold()
    score = 0.0
    for tok in query_tokens:
        if tok in title_source:
            score += 3.0
        if tok in body:
            score += 1.0
    return score / max(len(query_tokens), 1)


def _lexical_search_filtered(
    vectorstore: Chroma,
    query: str,
    k: int,
    doc_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> List[Document]:
    """Local lexical recall path over Chroma documents, used for hybrid retrieval."""
    qtokens = set(_lexical_tokens(query))
    if not qtokens:
        return []
    flt = _merge_chroma_filter(doc_type, extra)
    limit = _hybrid_lexical_pool_limit()
    try:
        col = vectorstore._collection  # noqa: SLF001 - Chroma metadata/document batch read for local lexical path
        batch = col.get(where=flt, include=["documents", "metadatas"], limit=limit)
    except Exception as exc:
        logger.warning("Chroma lexical get with filter failed; falling back to local metadata filter: %s", exc)
        try:
            col = vectorstore._collection  # noqa: SLF001
            batch = col.get(include=["documents", "metadatas"], limit=limit)
        except Exception as inner:
            logger.warning("Chroma lexical fallback get failed; disabling lexical path: %s", inner)
            return []
    docs_raw = batch.get("documents") or []
    metas_raw = batch.get("metadatas") or []
    scored: List[Tuple[float, int, Document]] = []
    for i, text in enumerate(docs_raw):
        meta = metas_raw[i] if i < len(metas_raw) and isinstance(metas_raw[i], dict) else {}
        doc = Document(page_content=text or "", metadata=meta)
        if not _doc_matches_metadata_filter(doc, doc_type, extra):
            continue
        score = _doc_lexical_score(qtokens, doc)
        if score <= 0:
            continue
        scored.append((score, i, doc))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [d for _, _, d in scored[: max(k, 1)]]


def _anchored_paper_retrieval_enabled() -> bool:
    return (os.getenv("ANCHORED_PAPER_RETRIEVAL", "true") or "").lower() not in ("0", "false", "no")


def _anchored_paper_min_chunks() -> int:
    return max(1, int(os.getenv("ANCHORED_PAPER_MIN_CHUNKS", "3")))


def _anchored_paper_title_boost() -> float:
    try:
        return float(os.getenv("ANCHORED_PAPER_TITLE_BOOST", "0.25"))
    except ValueError:
        return 0.25


def _anchored_source_soft_match() -> bool:
    return (os.getenv("ANCHORED_SOURCE_SOFT_MATCH", "true") or "").lower() not in ("0", "false", "no")


def _hybrid_path_candidate_topn(k: int) -> int:
    return max(int(k), 20, int(os.getenv("HYBRID_PAPER_CANDIDATE_TOPN", "20")))


def _rrf_merge_multiple(
    ranked_lists: Sequence[Sequence[Document]],
    k: int,
    *,
    list_boosts: Sequence[float] | None = None,
) -> List[Document]:
    if not ranked_lists:
        return []
    boosts = list(list_boosts or [1.0] * len(ranked_lists))
    scores: Dict[Tuple, float] = {}
    docs_by_fp: Dict[Tuple, Document] = {}
    for list_idx, docs in enumerate(ranked_lists):
        weight = boosts[list_idx] if list_idx < len(boosts) else 1.0
        for rank, doc in enumerate(docs):
            fp = _doc_fingerprint(doc)
            docs_by_fp.setdefault(fp, doc)
            scores[fp] = scores.get(fp, 0.0) + weight / (rank + 1)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
    return [docs_by_fp[fp] for fp, _ in ordered[: max(k, 1)]]


def _dedupe_docs(docs: Sequence[Document]) -> List[Document]:
    out: List[Document] = []
    seen: Set[Tuple] = set()
    for doc in docs:
        fp = _doc_fingerprint(doc)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(doc)
    return out


def _resolve_anchor_source(analysis: Dict[str, Any], title_soft_hint: Optional[str]) -> str:
    source = anchored_source_from_analysis(analysis)
    if source:
        return source
    if not _anchored_source_soft_match():
        return ""
    hint = anchored_title_hint_from_analysis(analysis) or (title_soft_hint or "").strip()
    if not hint:
        return ""
    return resolve_best_source(hint) or ""


def _retrieve_paper_with_anchor(
    vectorstore: Chroma,
    query: str,
    analysis: Dict[str, Any],
    pool_k: int,
    *,
    paper_extra_filter: Optional[Dict[str, Any]] = None,
    title_soft_hint: Optional[str] = None,
) -> Tuple[List[Document], Dict[str, Any]]:
    anchor_source = _resolve_anchor_source(analysis, title_soft_hint)
    min_chunks = _anchored_paper_min_chunks()
    boost = _anchored_paper_title_boost()
    locked = bool(paper_extra_filter and str(paper_extra_filter.get("source") or "").strip())

    anchored_docs: List[Document] = []
    if _anchored_paper_retrieval_enabled() and anchor_source and not locked:
        anchored_docs = _similarity_search_filtered(
            vectorstore,
            query,
            max(pool_k, min_chunks),
            "paper",
            {"source": anchor_source},
        )
    elif _anchored_paper_retrieval_enabled() and not locked:
        hint = anchored_title_hint_from_analysis(analysis) or (title_soft_hint or "").strip()
        if hint:
            for src in resolve_sources_by_title_hint(hint)[:3]:
                anchored_docs.extend(
                    _similarity_search_filtered(vectorstore, query, min_chunks, "paper", {"source": src})
                )
            anchored_docs = _dedupe_docs(anchored_docs)

    semantic_docs = _similarity_search_filtered(vectorstore, query, pool_k, "paper", paper_extra_filter)

    if anchored_docs and not locked:
        merged = _rrf_merge_multiple(
            [anchored_docs, semantic_docs],
            pool_k,
            list_boosts=[1.0 + boost, 1.0],
        )
        anchor_fps = {_doc_fingerprint(d) for d in anchored_docs}
        front = [d for d in merged if _doc_fingerprint(d) in anchor_fps][:min_chunks]
        rest = [d for d in merged if _doc_fingerprint(d) not in {_doc_fingerprint(x) for x in front}]
        merged = _dedupe_docs(front + rest)[:pool_k]
    else:
        merged = semantic_docs[:pool_k]

    hit_count = 0
    if anchor_source:
        hit_count = sum(1 for d in merged if str((d.metadata or {}).get("source") or "") == anchor_source)
    diag = {
        "anchored_source_detected": anchor_source or None,
        "anchored_source_hit_count": hit_count,
        "paper_candidate_pool_size": len(merged),
        "anchored_candidate_count": len(anchored_docs),
    }
    return merged, diag


def _merge_ranked_docs(vector_docs: List[Document], lexical_docs: List[Document], k: int) -> List[Document]:
    if not lexical_docs:
        return vector_docs[:k]
    if not vector_docs:
        return lexical_docs[:k]
    weight = _hybrid_lexical_weight()
    scores: Dict[Tuple, float] = {}
    docs_by_fp: Dict[Tuple, Document] = {}
    for rank, doc in enumerate(vector_docs):
        fp = _doc_fingerprint(doc)
        docs_by_fp.setdefault(fp, doc)
        scores[fp] = scores.get(fp, 0.0) + 1.0 / (rank + 1)
    for rank, doc in enumerate(lexical_docs):
        fp = _doc_fingerprint(doc)
        docs_by_fp.setdefault(fp, doc)
        scores[fp] = scores.get(fp, 0.0) + weight / (rank + 1)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
    return [docs_by_fp[fp] for fp, _ in ranked[: max(k, 1)]]


def _score_si_method_content(doc: Document) -> int:
    text = (doc.page_content or "").lower()
    return sum(1 for kw in SI_BOOST_KEYWORDS if kw in text)


def _merge_chroma_filter(doc_type: str, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    conditions: List[Dict[str, Any]] = [{"doc_type": doc_type}]
    if extra:
        for ek, ev in extra.items():
            if ev is not None and str(ev).strip() != "":
                conditions.append({str(ek): ev})
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _doc_matches_metadata_filter(doc: Document, doc_type: str, extra: Optional[Dict[str, Any]]) -> bool:
    m = doc.metadata or {}
    if m.get("doc_type") != doc_type:
        return False
    if not extra:
        return True
    for ek, ev in extra.items():
        if ev is None or str(ev).strip() == "":
            continue
        if m.get(ek) != ev:
            return False
    return True


def _vector_similarity_search_filtered(
    vectorstore: Chroma,
    query: str,
    k: int,
    doc_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> List[Document]:
    """
    带 doc_type 与可选 extra（如 source、project_id、paper_title）的相似度检索；
    若底层 Chroma 对 filter 报错，则回退为扩大检索后本地过滤。
    """
    if not (query or "").strip():
        return []
    flt = _merge_chroma_filter(doc_type, extra)
    try:
        return vectorstore.similarity_search(query, k=k, filter=flt)
    except Exception as exc:
        logger.warning(
            "Chroma vector search with filter failed; falling back to wider local filter. doc_type=%s extra=%s error=%s",
            doc_type,
            extra,
            exc,
        )
        pool = vectorstore.similarity_search(query, k=max(k * 4, 12))
        out = [d for d in pool if _doc_matches_metadata_filter(d, doc_type, extra)]
        return out[:k]


def _similarity_search_filtered(
    vectorstore: Chroma,
    query: str,
    k: int,
    doc_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> List[Document]:
    """Retrieval wrapper: vector-only or local hybrid vector+lexical, controlled by RAG_RETRIEVAL_MODE."""
    vector_docs = _vector_similarity_search_filtered(vectorstore, query, k, doc_type, extra)
    if _retrieval_mode() not in ("hybrid", "hybrid_local", "lexical_vector"):
        return vector_docs
    lexical_docs = _lexical_search_filtered(vectorstore, query, k, doc_type, extra)
    merged = _merge_ranked_docs(vector_docs, lexical_docs, k)
    logger.info(
        "retrieval mode=hybrid doc_type=%s k=%s vector_hits=%s lexical_hits=%s merged_hits=%s extra=%s",
        doc_type,
        k,
        len(vector_docs),
        len(lexical_docs),
        len(merged),
        extra,
    )
    return merged


def _apply_si_boost(
    vectorstore: Chroma,
    paper_docs: List[Document],
    query: str,
) -> List[Document]:
    """
    若论文路结果中含正文 main_text，则按 project_id 追加 supplementary_info 片段（仍属 doc_type=paper）。
    """
    seen: Set[Tuple] = {_doc_fingerprint(d) for d in paper_docs}
    out: List[Document] = list(paper_docs)
    main_pids: Set[str] = set()
    for d in paper_docs:
        m = d.metadata or {}
        if m.get("doc_role") == "main_text" and m.get("project_id"):
            main_pids.add(str(m["project_id"]))
    for pid in main_pids:
        flt = {"project_id": str(pid), "doc_role": "supplementary_info"}
        try:
            si_pool = vectorstore.similarity_search(query, k=SI_EXTRA_K, filter=flt)
        except Exception:
            si_pool = [
                d
                for d in vectorstore.similarity_search(query, k=SI_EXTRA_K * 2)
                if (d.metadata or {}).get("project_id") == pid
                and (d.metadata or {}).get("doc_role") == "supplementary_info"
            ][:SI_EXTRA_K]
        ranked = sorted(si_pool, key=_score_si_method_content, reverse=True)
        for d in ranked[:SI_TOP_AFTER_RANK]:
            if _score_si_method_content(d) == 0:
                continue
            fp = _doc_fingerprint(d)
            if fp in seen:
                continue
            seen.add(fp)
            out.append(d)
    return out


def retrieve_dual_path_filtered(
    question: str,
    analysis: Dict[str, Any],
    k: int = DEFAULT_RETRIEVER_K,
    *,
    vectorstore: Chroma | None = None,
    paper_extra_filter: Optional[Dict[str, Any]] = None,
    paper_title_soft_hint: Optional[str] = None,
    paper_k: Optional[int] = None,
    sop_k: Optional[int] = None,
) -> Tuple[List[Document], List[Document], str, Dict[str, Any]]:
    """
    根据解析出的 intent，向 Chroma 发起带 doc_type 的检索。

    - `paper_extra_filter`：附加 metadata（如 source、project_id），与 doc_type=paper 合并为 Chroma where
      （不含 paper_title 精确过滤；题录软匹配见 `paper_title_soft_hint`）。
    - `paper_title_soft_hint`：来自解析器的标题提示，用于扩大候选池并在 Python 侧重排。
    - `paper_k` / `sop_k`：可选覆盖各路 k（用于锁定单篇或 SCHOLARLY 提高论文路召回）。
    - HYBRID：paper / sop 两路并行；PAPER_ONLY / SOP_ONLY：单路。

    返回 (paper_docs, sop_docs, paper_path_note, retrieval_diagnostics)。
    """
    vs = vectorstore or get_vectorstore()
    sq = analysis.get("search_queries") or {}
    paper_q = (sq.get("paper_query") or "").strip() or question.strip()
    sop_q = (sq.get("sop_query") or "").strip() or question.strip()
    intent = analysis.get("intent") or "HYBRID"
    pk = int(paper_k) if paper_k is not None else int(k)
    sk = int(sop_k) if sop_k is not None else int(k)
    if intent == "HYBRID":
        sk = max(sk, _hybrid_path_candidate_topn(k))
        pool_k = max(paper_retrieval_pool_k(pk, paper_title_soft_hint), _hybrid_path_candidate_topn(k))
    else:
        pool_k = paper_retrieval_pool_k(pk, paper_title_soft_hint)

    paper_docs: List[Document] = []
    sop_docs: List[Document] = []
    paper_note = ""
    retrieval_diag: Dict[str, Any] = {
        "anchored_source_detected": None,
        "anchored_source_hit_count": 0,
        "paper_candidate_pool_size": 0,
        "sop_candidate_pool_size": 0,
    }

    if intent == "HYBRID":
        paper_docs, paper_diag = _retrieve_paper_with_anchor(
            vs,
            paper_q,
            analysis,
            pool_k,
            paper_extra_filter=paper_extra_filter,
            title_soft_hint=paper_title_soft_hint,
        )
        sop_docs = _similarity_search_filtered(vs, sop_q, sk, "sop", None)
        retrieval_diag.update(paper_diag)
        retrieval_diag["sop_candidate_pool_size"] = len(sop_docs)
    elif intent == "PAPER_ONLY":
        paper_docs, paper_diag = _retrieve_paper_with_anchor(
            vs,
            paper_q,
            analysis,
            pool_k,
            paper_extra_filter=paper_extra_filter,
            title_soft_hint=paper_title_soft_hint,
        )
        retrieval_diag.update(paper_diag)
    elif intent == "SOP_ONLY":
        sop_docs = _similarity_search_filtered(vs, sop_q, sk, "sop", None)
        retrieval_diag["sop_candidate_pool_size"] = len(sop_docs)
    else:
        paper_docs, paper_diag = _retrieve_paper_with_anchor(
            vs,
            paper_q,
            analysis,
            pool_k,
            paper_extra_filter=paper_extra_filter,
            title_soft_hint=paper_title_soft_hint,
        )
        sop_docs = _similarity_search_filtered(vs, sop_q, sk, "sop", None)
        retrieval_diag.update(paper_diag)
        retrieval_diag["sop_candidate_pool_size"] = len(sop_docs)

    if intent != "SOP_ONLY":
        paper_docs, rnote = rerank_paper_docs_by_title_hint(
            paper_docs,
            paper_title_soft_hint or anchored_title_hint_from_analysis(analysis) or "",
            paper_q,
            pk,
        )
        paper_note = rnote or ""
        retrieval_diag["paper_candidate_pool_size"] = len(paper_docs)

    paper_docs = _apply_si_boost(vs, paper_docs, paper_q)
    retrieval_diag["candidate_pool_size"] = len(paper_docs) + len(sop_docs)
    return paper_docs, sop_docs, paper_note, retrieval_diag


def format_paper_context_blocks(docs: Sequence[Document]) -> str:
    """Format paper-path chunks (incl. SI) with citation hints for the LLM."""
    if not docs:
        return "(No paper chunks retrieved for this round.)"
    blocks: List[str] = []
    for i, d in enumerate(docs, start=1):
        m = d.metadata or {}
        title = m.get("paper_title") or m.get("project_id") or "unknown_document"
        page = m.get("page", "?")
        src = m.get("source", "")
        role = m.get("doc_role", "")
        quality_warning = str(m.get("text_quality_warning") or "").strip()
        if role == "supplementary_info":
            cite_hint = f"[Source: {title} — supplementary material p.{page}]"
        else:
            cite_hint = f"[Source: `{src}` p.{page}] (paper_title: {title})"
        header = (
            f"--- Paper chunk {i} ---\n"
            f"citation_hint: {cite_hint}\n"
            f"doc_role: {role or 'unknown'}\n"
            f"source: {src}\n"
        )
        if quality_warning:
            header += f"text_quality_warning: {quality_warning}\n"
        blocks.append(header + (d.page_content or "").strip())
    return "\n\n".join(blocks)


def format_sop_context_blocks(docs: Sequence[Document]) -> str:
    """Format SOP-path chunks with citation hints for the LLM."""
    if not docs:
        return "(No SOP chunks retrieved for this round.)"
    blocks: List[str] = []
    for i, d in enumerate(docs, start=1):
        m = d.metadata or {}
        title = m.get("paper_title") or m.get("project_id") or "Manual"
        page = m.get("page", "?")
        src = m.get("source", "")
        quality_warning = str(m.get("text_quality_warning") or "").strip()
        cite_hint = f"[Source: SOP `{src}` p.{page}] (title: {title})"
        header = (
            f"--- SOP chunk {i} ---\n"
            f"citation_hint: {cite_hint}\n"
            f"doc_type: sop\n"
            f"source: {src}\n"
        )
        if quality_warning:
            header += f"text_quality_warning: {quality_warning}\n"
        blocks.append(header + (d.page_content or "").strip())
    return "\n\n".join(blocks)


# Legacy single system template ({paper_context}/{sop_context}). Prefer fusion_prompts.compose_fusion_system_prompt.
FUSION_RAG_SYSTEM_PROMPT = """You are a rigorous senior laboratory AI assistant. Answer using only the references below.

【Reference 1: Lab papers (Papers)】 — parameters and findings
{paper_context}

【Reference 2: SOPs】 — safety and standard procedures
{sop_context}

Safety first. If you take concrete run parameters from Reference 1, embed them in a safe procedure aligned with Reference 2.

Structured output when operational:
🧪 Key parameters (with citations)
⚠️ Safety & compliance (from SOP)
📋 Integrated procedure

Do not hallucinate. If parameters are missing, say so. If safety SOP is missing for an operational question, warn the user to contact an administrator.
"""


def _flatten_bundle_docs(paper_docs: Sequence[Document], sop_docs: Sequence[Document], k: int) -> List[Document]:
    docs: List[Document] = []
    max_len = max(len(paper_docs), len(sop_docs))
    for i in range(max_len):
        if i < len(paper_docs):
            docs.append(paper_docs[i])
        if i < len(sop_docs):
            docs.append(sop_docs[i])
    return docs[: max(k, 1)]


def fusion_prepare(
    question: str,
    k: int = DEFAULT_RETRIEVER_K,
    *,
    vectorstore: Chroma | None = None,
    analysis: Optional[Dict[str, Any]] = None,
    paper_source_scope: Optional[str] = None,
    strict_protocol_appendix: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    完整准备 Fusion RAG：Query 解析 + 双路检索 + 文本块 + 本回合静态 fusion_system_prompt。

    `paper_source_scope`：UI「锚定论文」的 metadata.source（如 papers/foo.pdf），优先于解析器中的 paper_scope_*。
    `strict_protocol_appendix`：若为 None，则使用环境变量 STRICT_PROTOCOL_APPENDIX（默认开启）。

    返回 dict 含：analysis, paper_docs, sop_docs, paper_context, sop_context, user_question,
    fusion_system_prompt, paper_retrieval_note, paper_scope_locked。
    """
    q = (question or "").strip()
    if analysis is None:
        analysis = (
            normalize_analysis(analyze_query(q, paper_anchor=paper_source_scope))
            if q
            else normalize_analysis(analyze_query("", paper_anchor=paper_source_scope))
        )
    else:
        analysis = normalize_analysis(analysis)

    if strict_protocol_appendix is None:
        strict_protocol_appendix = _strict_protocol_appendix_from_env()
    protocol_active = _protocol_rigor_should_activate(
        analysis, q, strict_protocol_appendix=strict_protocol_appendix
    )

    paper_extra, locked, title_hint = build_paper_scope_chroma_filter(analysis, paper_source_scope)
    answer_mode = str(analysis.get("answer_mode") or "HYBRID")
    paper_k = effective_paper_k(k, answer_mode, locked)
    paper_k = _bump_paper_k_for_protocol(paper_k, protocol_active, q)

    if locked and paper_extra:
        note = f"Paper retrieval locked with metadata filter: {paper_extra} (reduces cross-paper leakage)."
    elif (title_hint or "").strip() and not locked:
        note = (
            "Paper retrieval: title hint used for reranking only (no strict metadata lock); "
            "library-wide similarity with title-aware ordering."
        )
    else:
        note = "Paper retrieval: not locked to a single document (library-wide similarity); SCHOLARLY mode may use a higher paper-path k."
    if protocol_active:
        note = f"{note} Protocol-rigor appendix active; paper-path k={paper_k} (caps PAPER_PROTOCOL_K_MIN/MAX)."

    vs = vectorstore or get_vectorstore()
    paper_docs, sop_docs, path_note, retrieval_diag = retrieve_dual_path_filtered(
        q,
        analysis,
        k=k,
        vectorstore=vs,
        paper_extra_filter=paper_extra,
        paper_title_soft_hint=title_hint,
        paper_k=paper_k,
        sop_k=k,
    )
    if path_note:
        note = f"{note} {path_note}"

    sq = analysis.get("search_queries") or {}
    paper_q = (sq.get("paper_query") or "").strip() or q
    if protocol_active and paper_docs:
        paper_docs = _supplement_multi_source_paper_chunks(vs, paper_docs, paper_q, paper_extra)
        paper_docs = _apply_si_boost(vs, paper_docs, paper_q)

    docs_before_rerank = _flatten_bundle_docs(paper_docs, sop_docs, max(k, 20))
    retrieval_diag["candidate_pool_size"] = len(docs_before_rerank)

    rerank_info: Dict[str, Any] = {"provider": os.getenv("RERANKER_PROVIDER", "none"), "warning": "", "latency_ms": 0.0}
    rerank_provider = (os.getenv("RERANKER_PROVIDER", "none") or "").strip().lower()
    if rerank_provider not in ("", "none"):
        try:
            intent = str(analysis.get("intent") or "HYBRID")
            if rerank_provider == "rule" and intent in {"HYBRID", "PAPER_ONLY", "SOP_ONLY"}:
                paper_docs, sop_docs, reranked = rerank_dual_path(
                    paper_docs,
                    sop_docs,
                    q,
                    analysis,
                    paper_limit=len(paper_docs),
                    sop_limit=len(sop_docs),
                )
            else:
                final_k = max(1, int(os.getenv("FINAL_CONTEXT_K", str(k))))
                reranked = rerank_documents(
                    list(paper_docs) + list(sop_docs),
                    q,
                    analysis,
                    final_k=final_k,
                )
                paper_docs = [d for d in reranked.docs if (d.metadata or {}).get("doc_type") == "paper"]
                sop_docs = [d for d in reranked.docs if (d.metadata or {}).get("doc_type") == "sop"]
            rerank_info = {
                "provider": reranked.provider,
                "warning": reranked.warning,
                "latency_ms": round(reranked.latency_ms, 2),
                "metadata": reranked.metadata,
            }
            if reranked.warning:
                logger.warning("Reranker warning: %s", reranked.warning)
        except Exception as exc:
            rerank_info = {"provider": os.getenv("RERANKER_PROVIDER", "none"), "warning": str(exc), "latency_ms": 0.0}
            logger.warning("Reranker failed; falling back to original retrieval order: %s", exc)

    docs_after_rerank = _flatten_bundle_docs(paper_docs, sop_docs, max(k, 20))
    retrieval_diag["candidate_pool_size_after_rerank"] = len(docs_after_rerank)
    retrieval_diag["paper_docs_pre_rerank_count"] = len(docs_before_rerank)
    retrieval_diag["docs_before_rerank"] = docs_before_rerank
    retrieval_diag["docs_after_rerank"] = docs_after_rerank

    paper_ctx = format_paper_context_blocks(paper_docs)
    sop_ctx = format_sop_context_blocks(sop_docs)
    src_line = _summarize_retrieved_paper_sources(paper_docs) if protocol_active else ""
    fusion_system_prompt = compose_fusion_system_prompt(
        answer_mode,
        paper_context=paper_ctx,
        sop_context=sop_ctx,
        protocol_rigor_appendix=protocol_active,
        retrieved_paper_sources_summary=src_line,
        paper_only_intent=(analysis.get("intent") == "PAPER_ONLY"),
    )
    return {
        "analysis": analysis,
        "paper_docs": paper_docs,
        "sop_docs": sop_docs,
        "paper_context": paper_ctx,
        "sop_context": sop_ctx,
        "user_question": q,
        "fusion_system_prompt": fusion_system_prompt,
        "paper_retrieval_note": note,
        "paper_scope_locked": locked,
        "protocol_rigor_appendix": protocol_active,
        "rerank_info": rerank_info,
        "retrieval_diagnostics": retrieval_diag,
    }


def _escape_prompt_template_braces(text: str) -> str:
    """Escape `{`/`}` for ChatPromptTemplate so literal braces in context do not become variables."""
    return (text or "").replace("{", "{{").replace("}", "}}")


def _build_fusion_llm(*, temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Set GOOGLE_API_KEY or GEMINI_API_KEY to use ChatGoogleGenerativeAI.")
    return ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_LLM_MODEL", "gemini-3-flash-preview"),
        google_api_key=api_key,
        temperature=temperature,
    )


def build_fusion_rag_chain(*, temperature: float = 0.2, system_prompt: Optional[str] = None):
    """
    Build the Fusion LCEL chain: `system_prompt` is the fully expanded system string per request
    (normally from `fusion_prepare`). If omitted, a minimal placeholder system is used for legacy callers.
    """
    llm = _build_fusion_llm(temperature=temperature)
    sp = (system_prompt or "").strip() or compose_fusion_system_prompt(
        "HYBRID",
        paper_context="(No context)",
        sop_context="(No context)",
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _escape_prompt_template_braces(sp)),
            ("human", "{question}"),
        ]
    )
    return prompt | llm | StrOutputParser()


def invoke_fusion_rag(
    question: str,
    k: int = DEFAULT_RETRIEVER_K,
    *,
    paper_source_scope: Optional[str] = None,
) -> str:
    """非流式：内部完成解析与检索后一次性生成。"""
    bundle = fusion_prepare(question, k=k, paper_source_scope=paper_source_scope)
    chain = build_fusion_rag_chain(temperature=0.2, system_prompt=bundle["fusion_system_prompt"])
    return chain.invoke({"question": bundle["user_question"]})


def stream_fusion_rag_from_bundle(bundle: Dict[str, Any], *, temperature: float = 0.2):
    """流式生成：调用方需先 `fusion_prepare` 拿到 bundle，以便 UI 先展示解析/检索状态。"""
    sp = bundle.get("fusion_system_prompt")
    if not (sp or "").strip():
        sp = compose_fusion_system_prompt(
            str((bundle.get("analysis") or {}).get("answer_mode") or "HYBRID"),
            paper_context=bundle.get("paper_context") or "",
            sop_context=bundle.get("sop_context") or "",
            protocol_rigor_appendix=bool(bundle.get("protocol_rigor_appendix")),
            retrieved_paper_sources_summary="",
            paper_only_intent=((bundle.get("analysis") or {}).get("intent") == "PAPER_ONLY"),
        )
    chain = build_fusion_rag_chain(temperature=temperature, system_prompt=sp)
    return chain.stream({"question": bundle["user_question"]})


def format_references_papers_markdown(docs: Sequence[Document]) -> str:
    """Markdown list for the paper reference panel (metadata verbatim)."""
    if not docs:
        return "_None_"
    lines: List[str] = []
    for d in docs:
        m = d.metadata or {}
        title = m.get("paper_title") or m.get("project_id", "")
        page = m.get("page", "?")
        src = m.get("source", "")
        role = m.get("doc_role", "")
        if role == "supplementary_info":
            lines.append(f"- **{title}** · supplementary p.{page} · `{src}`")
        else:
            lines.append(f"- **{title}** · p.{page} · `{src}`")
    return "\n".join(lines)


def format_references_manuals_markdown(docs: Sequence[Document]) -> str:
    """Markdown list for the SOP reference panel (metadata verbatim)."""
    if not docs:
        return "_None_"
    lines: List[str] = []
    for d in docs:
        m = d.metadata or {}
        title = m.get("paper_title") or m.get("project_id", "Manual")
        page = m.get("page", "?")
        src = m.get("source", "")
        lines.append(f"- **{title}** · p.{page} · `{src}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 兼容旧 API（脚本 / 测试）
# ---------------------------------------------------------------------------


def retrieve_with_supplementary_boost(
    query: str,
    k: int = DEFAULT_RETRIEVER_K,
    *,
    vectorstore: Chroma | None = None,
) -> List[Document]:
    """等价于不做 Query 解析时，对全库 paper 路 + SI 增强（不推荐用于生产 UI）。"""
    analysis = normalize_analysis(
        {
            "intent": "PAPER_ONLY",
            "answer_mode": "SCHOLARLY",
            "search_queries": {"paper_query": query, "sop_query": query},
        }
    )
    paper_docs, _, _, _ = retrieve_dual_path_filtered(
        query,
        analysis,
        k=k,
        vectorstore=vectorstore,
        paper_extra_filter=None,
        paper_title_soft_hint=None,
        paper_k=effective_paper_k(k, "SCHOLARLY", False),
    )
    return paper_docs


def format_context_with_citation_hints(docs: Sequence[Document]) -> str:
    """旧版单路 context 格式化（论文片段逻辑）。"""
    return format_paper_context_blocks(docs)


def invoke_rag(question: str) -> str:
    """兼容旧名：走 Fusion 全流程。"""
    return invoke_fusion_rag(question)


def stream_rag(question: str, *, paper_source_scope: Optional[str] = None):
    """兼容旧名：内部先 prepare 再流式输出。"""
    bundle = fusion_prepare(question, paper_source_scope=paper_source_scope)
    return stream_fusion_rag_from_bundle(bundle)


def get_reference_documents(
    question: str,
    *,
    paper_source_scope: Optional[str] = None,
) -> List[Document]:
    """兼容：返回论文路 + 手册路合并列表（论文在前）。"""
    b = fusion_prepare(question, paper_source_scope=paper_source_scope)
    return list(b["paper_docs"]) + list(b["sop_docs"])


def format_references_line(docs: Sequence[Document]) -> str:
    """单行摘要（兼容）。"""
    parts: List[str] = []
    for d in docs:
        m = d.metadata or {}
        dt = m.get("doc_type", "")
        title = m.get("paper_title") or m.get("project_id", "")
        page = m.get("page", "?")
        src = m.get("source", "")
        tag = "SOP" if dt == "sop" else "Paper"
        parts.append(f"[{tag}] {title} p.{page} {src}")
    return " · ".join(parts)
