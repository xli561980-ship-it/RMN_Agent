# -*- coding: utf-8 -*-
"""Post-generation citation checks for Fusion RAG answers.

The validator is intentionally lightweight and offline: it does not judge
semantic faithfulness, but it catches a useful class of demo/prod failures:
answers that cite sources not present in the current retrieval bundle, or
answers with parameter-like numeric claims but no traceable citation hints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from langchain_core.documents import Document


_SOURCE_HINT_RE = re.compile(r"\[Source:[^\]]+\]")
_NUMERIC_CLAIM_RE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*(?:"
    r"%|°C|℃|K|h|hr|hrs|hour|hours|min|s|sec|seconds|"
    r"mM|µM|uM|nM|M|mol|mg|g|kg|µg|ug|mL|ml|L|µL|ul|"
    r"rpm|g-force|xg|kPa|MPa|Pa|V|mA|A|W|Hz|nm|µm|um"
    r")\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class CitationValidationResult:
    """Compact validation result suitable for UI/debug display."""

    ok: bool
    cited_hints: list[str] = field(default_factory=list)
    unknown_hints: list[str] = field(default_factory=list)
    missing_citation_numeric_claims: list[str] = field(default_factory=list)
    allowed_hint_count: int = 0

    @property
    def cited_allowed_count(self) -> int:
        return len(self.cited_hints) - len(self.unknown_hints)

    def to_markdown(self) -> str:
        status = "OK" if self.ok else "Needs review"
        lines = [
            f"**Citation validation:** {status}",
            f"- Allowed hints in retrieval bundle: `{self.allowed_hint_count}`",
            f"- Cited hints in answer: `{len(self.cited_hints)}`",
            f"- Unknown cited hints: `{len(self.unknown_hints)}`",
            f"- Numeric claim lines without citation: `{len(self.missing_citation_numeric_claims)}`",
        ]
        if self.unknown_hints:
            lines.append("\n**Unknown hints**")
            lines.extend(f"- `{h}`" for h in self.unknown_hints[:10])
        if self.missing_citation_numeric_claims:
            lines.append("\n**Numeric claim lines without citation**")
            lines.extend(f"- {x}" for x in self.missing_citation_numeric_claims[:10])
        return "\n".join(lines)


def citation_hint_for_doc(doc: Document, *, kind: str) -> str:
    """Recreate the citation_hint string used in rag_core context blocks."""
    meta = doc.metadata or {}
    title = meta.get("paper_title") or meta.get("project_id") or ("Manual" if kind == "sop" else "unknown_document")
    page = meta.get("page", "?")
    src = meta.get("source", "")
    role = meta.get("doc_role", "")
    if kind == "paper":
        if role == "supplementary_info":
            return f"[Source: {title} — supplementary material p.{page}]"
        return f"[Source: `{src}` p.{page}]"
    return f"[Source: SOP `{src}` p.{page}]"


def allowed_citation_hints(
    paper_docs: Sequence[Document],
    sop_docs: Sequence[Document],
) -> set[str]:
    hints: set[str] = set()
    for doc in paper_docs:
        hints.add(citation_hint_for_doc(doc, kind="paper"))
    for doc in sop_docs:
        hints.add(citation_hint_for_doc(doc, kind="sop"))
    return hints


def _extract_cited_hints(answer: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _SOURCE_HINT_RE.finditer(answer or ""):
        hint = match.group(0)
        if hint not in seen:
            seen.add(hint)
            out.append(hint)
    return out


def _numeric_claim_lines_without_citation(answer: str) -> list[str]:
    out: list[str] = []
    for raw_line in (answer or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "[Source:" in line:
            continue
        if _NUMERIC_CLAIM_RE.search(line):
            out.append(line[:300])
    return out


def validate_answer_citations(
    answer: str,
    *,
    paper_docs: Sequence[Document],
    sop_docs: Sequence[Document],
) -> CitationValidationResult:
    allowed = allowed_citation_hints(paper_docs, sop_docs)
    cited = _extract_cited_hints(answer)
    unknown = [h for h in cited if h not in allowed]
    numeric_without = _numeric_claim_lines_without_citation(answer)
    ok = not unknown and not numeric_without and bool(cited or not (answer or "").strip())
    return CitationValidationResult(
        ok=ok,
        cited_hints=cited,
        unknown_hints=unknown,
        missing_citation_numeric_claims=numeric_without,
        allowed_hint_count=len(allowed),
    )


def format_allowed_citation_hints(hints: Iterable[str]) -> str:
    return "\n".join(f"- `{h}`" for h in sorted(set(hints)))
