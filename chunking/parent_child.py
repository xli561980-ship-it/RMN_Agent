# -*- coding: utf-8 -*-
"""Parent-child helpers for SOP/manual chunking."""

from __future__ import annotations

import hashlib


def stable_parent_id(source: str, page: object, index: int, text: str) -> str:
    raw = f"{source}|{page}|{index}|{text[:80]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def preview(text: str, limit: int = 500) -> str:
    body = " ".join((text or "").split())
    return body[:limit]
