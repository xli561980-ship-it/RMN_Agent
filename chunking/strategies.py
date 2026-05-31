# -*- coding: utf-8 -*-
"""Chunking strategies used by ingest and experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

from .parent_child import preview, stable_parent_id
from .section_parser import classify_section_title, parse_markdown_sections


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: str = "header_aware"
    chunk_size: int = 900
    chunk_overlap: int = 150
    child_chunk_size: int = 500
    child_chunk_overlap: int = 80
    parent_chunk_size: int = 1800
    parent_chunk_overlap: int = 200


def _windows(text: str, size: int, overlap: int) -> list[str]:
    body = text or ""
    if not body:
        return []
    size = max(1, int(size))
    overlap = max(0, min(int(overlap), size - 1))
    out: list[str] = []
    start = 0
    while start < len(body):
        end = min(len(body), start + size)
        piece = body[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(body):
            break
        start = end - overlap
    return out


def _with_common_meta(meta: dict[str, Any], *, strategy: str, section_title: str, section_type: str, index: int) -> dict[str, Any]:
    out = dict(meta)
    out["chunk_strategy"] = strategy
    out["section_title"] = section_title
    out["section_type"] = section_type
    out["chunk_index"] = index
    return out


def fixed_chunks(doc: Document, config: ChunkingConfig) -> list[Document]:
    chunks = []
    for idx, piece in enumerate(_windows(doc.page_content or "", config.chunk_size, config.chunk_overlap)):
        chunks.append(
            Document(
                page_content=piece,
                metadata=_with_common_meta(doc.metadata or {}, strategy="fixed", section_title="Fixed", section_type="other", index=idx),
            )
        )
    return chunks


def header_aware_chunks(doc: Document, config: ChunkingConfig) -> list[Document]:
    chunks: list[Document] = []
    idx = 0
    for section in parse_markdown_sections(doc.page_content or ""):
        for piece in _windows(section.text, config.chunk_size, config.chunk_overlap):
            chunks.append(
                Document(
                    page_content=piece,
                    metadata=_with_common_meta(
                        doc.metadata or {},
                        strategy="header_aware",
                        section_title=section.title,
                        section_type=section.section_type,
                        index=idx,
                    ),
                )
            )
            idx += 1
    return chunks


def semantic_placeholder_chunks(doc: Document, config: ChunkingConfig) -> list[Document]:
    """Lightweight paragraph grouping placeholder, not embedding-based semantic chunking."""
    paragraphs = [p.strip() for p in (doc.page_content or "").split("\n\n") if p.strip()]
    if not paragraphs:
        return []
    groups: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for para in paragraphs:
        if cur and cur_len + len(para) > config.chunk_size:
            groups.append("\n\n".join(cur))
            cur = []
            cur_len = 0
        cur.append(para)
        cur_len += len(para)
    if cur:
        groups.append("\n\n".join(cur))
    chunks: list[Document] = []
    current_section = "Paragraph Group"
    for idx, text in enumerate(groups):
        first = text.splitlines()[0].lstrip("# ").strip() if text.splitlines() else current_section
        if first:
            current_section = first[:120]
        chunks.append(
            Document(
                page_content=text,
                metadata=_with_common_meta(
                    doc.metadata or {},
                    strategy="semantic_placeholder",
                    section_title=current_section,
                    section_type=classify_section_title(current_section),
                    index=idx,
                ),
            )
        )
    return chunks


def parent_child_chunks(doc: Document, config: ChunkingConfig) -> list[Document]:
    """Create retrievable child chunks with parent context stored in metadata."""
    parent_texts = _windows(doc.page_content or "", config.parent_chunk_size, config.parent_chunk_overlap)
    out: list[Document] = []
    child_global_idx = 0
    for pidx, parent_text in enumerate(parent_texts):
        pid = stable_parent_id(str((doc.metadata or {}).get("source") or ""), (doc.metadata or {}).get("page"), pidx, parent_text)
        for cidx, child_text in enumerate(_windows(parent_text, config.child_chunk_size, config.child_chunk_overlap)):
            section_title = child_text.splitlines()[0].lstrip("# ").strip()[:120] or f"Parent {pidx + 1}"
            meta = _with_common_meta(
                doc.metadata or {},
                strategy="parent_child",
                section_title=section_title,
                section_type=classify_section_title(section_title),
                index=child_global_idx,
            )
            meta.update(
                {
                    "parent_id": pid,
                    "child_id": f"{pid}-{cidx}",
                    "parent_text_preview": preview(parent_text),
                    "chunk_role": "child",
                }
            )
            out.append(Document(page_content=child_text, metadata=meta))
            child_global_idx += 1
    return out


def split_document(doc: Document, config: ChunkingConfig) -> list[Document]:
    strategy = (config.strategy or "header_aware").strip().lower()
    if strategy == "fixed":
        return fixed_chunks(doc, config)
    if strategy == "header_aware":
        return header_aware_chunks(doc, config)
    if strategy == "semantic_placeholder":
        return semantic_placeholder_chunks(doc, config)
    if strategy == "parent_child":
        return parent_child_chunks(doc, config)
    raise ValueError(f"Unsupported chunk strategy: {config.strategy}")
