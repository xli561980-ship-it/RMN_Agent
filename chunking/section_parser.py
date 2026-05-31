# -*- coding: utf-8 -*-
"""Lightweight section heading detection for papers, SOPs and manuals."""

from __future__ import annotations

import re
from dataclasses import dataclass


SECTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("abstract", ("abstract", "摘要")),
    ("introduction", ("introduction", "background", "引言", "背景")),
    ("methods", ("methods", "materials and methods", "experimental", "methodology", "方法", "材料与方法")),
    ("supplementary_methods", ("supplementary methods", "supporting information", "supplementary", "补充方法")),
    ("results", ("results", "result", "结果")),
    ("discussion", ("discussion", "讨论")),
    ("protocol", ("protocol", "procedure", "步骤", "流程", "规程")),
    ("safety", ("safety", "warning", "caution", "hazard", "安全", "警告", "注意")),
    ("operation", ("operation", "operating", "operation manual", "使用", "操作")),
    ("calibration", ("calibration", "calibrate", "校准")),
    ("troubleshooting", ("troubleshooting", "trouble shooting", "故障", "排错")),
)


HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$", flags=re.MULTILINE)


@dataclass(frozen=True)
class Section:
    title: str
    section_type: str
    start: int
    end: int
    text: str


def classify_section_title(title: str) -> str:
    norm = re.sub(r"^\d+(?:\.\d+)*\s*", "", (title or "").strip()).casefold()
    for section_type, needles in SECTION_KEYWORDS:
        if any(n in norm for n in needles):
            return section_type
    return "other"


def parse_markdown_sections(text: str) -> list[Section]:
    """Split text into Markdown-like sections while preserving heading text."""
    body = text or ""
    matches = list(HEADING_RE.finditer(body))
    if not matches:
        title = "Untitled"
        return [Section(title=title, section_type=classify_section_title(title), start=0, end=len(body), text=body)]
    sections: list[Section] = []
    if matches[0].start() > 0 and body[: matches[0].start()].strip():
        prefix = body[: matches[0].start()].strip()
        sections.append(Section("Preamble", "other", 0, matches[0].start(), prefix))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        title = match.group("title").strip()
        section_text = body[start:end].strip()
        sections.append(Section(title, classify_section_title(title), start, end, section_text))
    return sections
