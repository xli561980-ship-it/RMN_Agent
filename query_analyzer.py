# -*- coding: utf-8 -*-
"""
query_analyzer.py — 用户 Query 意图解析（Fusion RAG 前置步骤）

结构化输出包含：
- intent：检索路由（SOP_ONLY / PAPER_ONLY / HYBRID）
- answer_mode：生成形态（SCHOLARLY / OPERATIONAL / HYBRID），与 intent 的 HYBRID 含义不同
- paper_scope_*：若用户问题可锁定单篇，则给出 source / project_id / paper_title 之一或组合（供 Chroma metadata 过滤）
- requires_full_protocol：用户明确要求逐步完整实验/制备/复现流程时置 true
- search_queries：双路检索改写
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover
    ChatGoogleGenerativeAI = None  # type: ignore

load_dotenv()


_PROCEDURE_TERMS = (
    "protocol",
    "procedure",
    "step",
    "steps",
    "replicate",
    "fabrication",
    "synthesis",
    "prepare",
    "制备",
    "步骤",
    "流程",
    "复现",
    "合成",
    "实验方案",
)

_SOP_TERMS = (
    "sop",
    "manual",
    "safety",
    "compliance",
    "操作手册",
    "安全",
    "规范",
    "注意事项",
    "仪器",
    "手册",
)

_PAPER_TERMS = (
    "paper",
    "study",
    "article",
    "literature",
    "result",
    "compare",
    "comparison",
    "论文",
    "文献",
    "研究",
    "对比",
    "差异",
    "参数",
)

_SOP_OPERATION_TERMS = (
    "requirement",
    "requirements",
    "use",
    "operate",
    "operation",
    "measurement",
    "calibration",
    "equilibration",
    "manual",
    "要求",
    "使用",
    "操作",
    "测量",
    "校准",
    "平衡",
    "注意事项",
)

_INSTRUMENT_HINT_RE = re.compile(
    r"\b(?:Leica|Litesizer|Varioskan|SevenExcellence|arium|FreeZone|Chiaro|OB1|MFS|LAS\s*X|pH\s*meter)\b",
    flags=re.IGNORECASE,
)


class SearchQueriesModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sop_query: str = Field(
        description="Retrieval query for SOPs: emphasize steps, safety, instruments, reagents, normative wording.",
    )
    paper_query: str = Field(
        description="Retrieval query for papers: emphasize conditions, parameters, comparisons, materials, results.",
    )


class QueryAnalysisModel(BaseModel):
    """与下游 rag_core 对齐；新增字段对旧 JSON 缺失时由 normalize_analysis 补默认。"""

    model_config = ConfigDict(extra="ignore")

    entities: List[str] = Field(default_factory=list, description="Key entities (instruments, reagents, project names, etc.).")
    intent: Literal["SOP_ONLY", "PAPER_ONLY", "HYBRID"] = Field(
        description="Retrieval route: SOP_ONLY | PAPER_ONLY | HYBRID"
    )
    answer_mode: Literal["SCHOLARLY", "OPERATIONAL", "HYBRID"] = Field(
        description=(
            "Generation shape: SCHOLARLY = interpret / summarize methods / compare papers (no default three-block lab template); "
            "OPERATIONAL = protocols, replication, steps, grounding parameters in the lab; "
            "HYBRID = both. For exhaustive step-by-step synthesis/fabrication/replication, prefer OPERATIONAL or HYBRID "
            "and set requires_full_protocol when the user demands full procedural depth."
        )
    )
    paper_scope_source: Optional[str] = Field(
        default=None,
        description=(
            "Relative path under data/, e.g. papers/Zhang2024.pdf. "
            "If the user names a file (including .pdf), a basename, or a path-like string, set this to papers/<filename>; "
            "prefer this over paper_scope_paper_title when both are possible."
        ),
    )
    paper_scope_project_id: Optional[str] = Field(
        default=None,
        description="If the user states or you can infer project_id, set it; else null.",
    )
    paper_scope_paper_title: Optional[str] = Field(
        default=None,
        description=(
            "ONLY if the user's title is certainly identical to the corpus metadata field `paper_title` "
            "(or they pasted a DOI / stable id you trust maps 1:1). Otherwise null — rely on semantic retrieval, "
            "`paper_scope_source`, or `paper_scope_project_id`. Do NOT guess near-miss titles (punctuation/case differences)."
        ),
    )
    requires_full_protocol: bool = Field(
        default=False,
        description=(
            "True when the user wants an exhaustive, step-by-step experimental / synthesis / fabrication / "
            "replication procedure (not a summary). Triggers stricter end-of-answer protocol formatting downstream."
        ),
    )
    search_queries: SearchQueriesModel = Field(description="Dual-path retrieval rewrites.")


def normalize_analysis(raw: Dict[str, Any]) -> Dict[str, Any]:
    """兼容旧版/缺字段的 analysis dict。"""
    out = dict(raw)
    out.setdefault("intent", "HYBRID")
    out.setdefault("answer_mode", "HYBRID")
    out.setdefault("entities", [])
    out.setdefault("paper_scope_source", None)
    out.setdefault("paper_scope_project_id", None)
    out.setdefault("paper_scope_paper_title", None)
    out.setdefault("requires_full_protocol", False)
    sq = out.get("search_queries")
    if not isinstance(sq, dict):
        out["search_queries"] = {"sop_query": "", "paper_query": ""}
    else:
        sq = dict(sq)
        sq.setdefault("sop_query", "")
        sq.setdefault("paper_query", "")
        out["search_queries"] = sq
    return out


def _empty_analysis() -> Dict[str, Any]:
    return normalize_analysis(
        {
            "entities": [],
            "intent": "HYBRID",
            "answer_mode": "SCHOLARLY",
            "paper_scope_source": None,
            "paper_scope_project_id": None,
            "paper_scope_paper_title": None,
            "requires_full_protocol": False,
            "search_queries": {"sop_query": "", "paper_query": ""},
        }
    )


def _extract_possible_paper_source(text: str) -> Optional[str]:
    """Best-effort filename/path extraction for LLM-unavailable fallback."""
    match = re.search(r"([\w\u4e00-\u9fff .,\-()（）\[\]‐–—]+?\.(?:pdf|docx))", text or "", flags=re.IGNORECASE)
    if not match:
        return None
    name = match.group(1).strip(" ，,。；;：:")
    # If surrounding natural language was captured, prefer the nearest path-like token.
    for part in reversed(re.split(r"\s+", name)):
        if re.search(r"\.(?:pdf|docx)$", part, flags=re.IGNORECASE):
            name = part.strip(" ，,。；;：:")
            break
    if "/" in name:
        return name if name.startswith("papers/") else name
    return f"papers/{name}"


def heuristic_analyze_query(user_query: str, *, paper_anchor: Optional[str] = None) -> Dict[str, Any]:
    """
    Rule-based fallback used when the analyzer LLM is unavailable.

    It is intentionally conservative: preserve the user's wording for both
    retrieval paths, infer only coarse routing, and use explicit filenames/UI
    anchors for paper scope.
    """
    text = (user_query or "").strip()
    if not text:
        return _empty_analysis()
    low = text.lower()
    has_sop = any(term in low or term in text for term in _SOP_TERMS)
    has_paper = any(term in low or term in text for term in _PAPER_TERMS)
    wants_procedure = any(term in low or term in text for term in _PROCEDURE_TERMS)
    has_operation = any(term in low or term in text for term in _SOP_OPERATION_TERMS)
    if _INSTRUMENT_HINT_RE.search(text) and has_operation and not has_paper:
        has_sop = True

    if has_sop and not has_paper:
        intent: Literal["SOP_ONLY", "PAPER_ONLY", "HYBRID"] = "SOP_ONLY"
    elif has_paper and not has_sop:
        intent = "PAPER_ONLY"
    elif wants_procedure:
        intent = "HYBRID"
    else:
        intent = "HYBRID"

    if wants_procedure and has_paper:
        answer_mode: Literal["SCHOLARLY", "OPERATIONAL", "HYBRID"] = "HYBRID"
    elif wants_procedure or has_sop:
        answer_mode = "OPERATIONAL"
    elif has_paper:
        answer_mode = "SCHOLARLY"
    else:
        answer_mode = "HYBRID"

    source = _extract_possible_paper_source(text)
    if not source and (paper_anchor or "").strip():
        source = paper_anchor.strip()

    entities = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-_/]{2,}|[\u4e00-\u9fff]{2,}", text):
        if token.lower() not in {"what", "how", "the", "and", "for", "with"}:
            entities.append(token)
        if len(entities) >= 8:
            break

    return normalize_analysis(
        {
            "entities": entities,
            "intent": intent,
            "answer_mode": answer_mode,
            "paper_scope_source": source,
            "paper_scope_project_id": None,
            "paper_scope_paper_title": None,
            "requires_full_protocol": wants_procedure,
            "search_queries": {
                "sop_query": f"{text} SOP safety standard procedure manual",
                "paper_query": f"{text} paper methods parameters results",
            },
        }
    )


def _apply_route_guards(analysis: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    """Small deterministic corrections for common lab-corpus routing cases."""
    out = normalize_analysis(analysis)
    text = user_query or ""
    low = text.lower()
    has_paper = any(term in low or term in text for term in _PAPER_TERMS)
    has_sop = any(term in low or term in text for term in _SOP_TERMS)
    has_operation = any(term in low or term in text for term in _SOP_OPERATION_TERMS)
    instrument_like = bool(_INSTRUMENT_HINT_RE.search(text))
    if (has_sop or (instrument_like and has_operation)) and not has_paper:
        out["intent"] = "SOP_ONLY"
        out["answer_mode"] = "OPERATIONAL"
    return out


def _build_analyzer_llm():
    if ChatGoogleGenerativeAI is None:
        raise RuntimeError("langchain-google-genai is required for the query analyzer.")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY or GEMINI_API_KEY.")
    model = os.getenv("GOOGLE_QUERY_ANALYZER_MODEL") or os.getenv("GOOGLE_LLM_MODEL", "gemini-3-flash-preview")
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.0)


def analyze_query(user_query: str, *, paper_anchor: Optional[str] = None) -> Dict[str, Any]:
    """
    结构化分析用户 Query。

    paper_anchor: UI 侧「锚定论文」的 metadata source 值（如 papers/foo.pdf），会并入提示供模型参考；
    解析结果中的 paper_scope_* 若为空，下游 rag_core 将优先使用该锚定做 Chroma 过滤。
    """
    text = (user_query or "").strip()
    if not text:
        return _empty_analysis()

    try:
        llm = _build_analyzer_llm()
    except Exception:
        return _apply_route_guards(heuristic_analyze_query(text, paper_anchor=paper_anchor), text)
    structured = llm.with_structured_output(QueryAnalysisModel)
    anchor_line = (
        f"\n[UI-anchored paper path (if selected): {paper_anchor}]\n"
        "If this anchor is relevant to the question, set paper_scope_source to exactly this path string; otherwise ignore it."
        if (paper_anchor or "").strip()
        else ""
    )
    sys_msg = (
        "You are the query-analysis module for a lab RAG system. The corpus has two kinds of documents:\n"
        "- SOPs (manuals): normative, executable workflow and safety.\n"
        "- Papers: descriptive parameters, methods, results, comparisons.\n\n"
        "Produce:\n"
        "1) intent: SOP_ONLY | PAPER_ONLY | HYBRID (retrieval routing).\n"
        "2) answer_mode (generation shape, not the same meaning as intent HYBRID):\n"
        "   - SCHOLARLY: interpretation, gist, methods summary, results comparison across papers; do NOT assume the three-block lab answer template.\n"
        "   - OPERATIONAL: user wants hands-on steps, replication, or grounding paper parameters in lab work.\n"
        "   - HYBRID: both scholarly and potentially executable aspects.\n"
        "3) paper_scope_*: Use ONLY when you can lock a single paper without brittle string guessing.\n"
        "   - If the user mentions a filename (with .pdf), basename, or path, set paper_scope_source to papers/<filename>.\n"
        "   - Set paper_scope_paper_title ONLY when the title is certainly the same string as stored metadata.paper_title "
        "(or the user pasted a DOI / file path); otherwise leave it null and let retrieval use embeddings + source/project hints.\n"
        "   - project_id when explicitly stated or unambiguous.\n"
        "4) requires_full_protocol: true only when the user explicitly wants exhaustive step-by-step lab / synthesis / "
        "fabrication / replication detail (not a short summary); false otherwise.\n"
        "5) search_queries: sop_query and paper_query tuned for retrieval (reuse the user’s language and technical terms where helpful).\n"
        f"{anchor_line}"
    )
    human = f"User question:\n{text}"
    try:
        result = structured.invoke([("system", sys_msg), ("human", human)])
    except Exception:
        return _apply_route_guards(heuristic_analyze_query(text, paper_anchor=paper_anchor), text)
    if isinstance(result, QueryAnalysisModel):
        parsed = result
    elif isinstance(result, dict):
        parsed = QueryAnalysisModel.model_validate(result)
    else:
        parsed = QueryAnalysisModel.model_validate(result)
    return _apply_route_guards(parsed.model_dump(), text)


def analyze_query_json(user_query: str, *, paper_anchor: Optional[str] = None) -> str:
    import json

    return json.dumps(analyze_query(user_query, paper_anchor=paper_anchor), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    assert normalize_analysis({"intent": "PAPER_ONLY"})["answer_mode"] == "HYBRID"
    assert normalize_analysis({"intent": "PAPER_ONLY"}).get("requires_full_protocol") is False
    assert _empty_analysis()["answer_mode"] == "SCHOLARLY"
    print("query_analyzer self-check: ok")
