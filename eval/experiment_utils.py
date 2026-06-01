#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for RMN Agent experiment runs and comparisons."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Iterator, Sequence

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "eval" / "runs"
REPORTS_DIR = ROOT / "eval" / "reports"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{i}: invalid JSONL: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"name": "current", "description": "Current environment defaults.", "k": 5, "env": {}}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(cfg, dict):
        raise SystemExit(f"{path}: config must be a JSON object")
    cfg.setdefault("name", path.stem)
    cfg.setdefault("description", "")
    cfg.setdefault("k", 5)
    cfg.setdefault("env", {})
    if not isinstance(cfg.get("env"), dict):
        raise SystemExit(f"{path}: env must be an object")
    return cfg


def slugify(value: str, *, default: str = "run") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug or default


def make_run_id(config_name: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{ts}_{slugify(config_name)}"


@contextlib.contextmanager
def temporary_env(overrides: dict[str, Any]) -> Iterator[None]:
    old: dict[str, str | None] = {}
    for key, value in overrides.items():
        skey = str(key)
        old[skey] = os.environ.get(skey)
        if value is None:
            os.environ.pop(skey, None)
        else:
            os.environ[skey] = str(value)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def content_hash(text: str, *, chars: int = 12) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="replace")).hexdigest()[:chars]


def summarize_doc(doc: Any, *, rank: int, path_name: str) -> dict[str, Any]:
    meta = dict(getattr(doc, "metadata", None) or {})
    text = getattr(doc, "page_content", "") or ""
    return {
        "rank": rank,
        "path": path_name,
        "source": str(meta.get("source") or ""),
        "page": meta.get("page"),
        "doc_type": meta.get("doc_type"),
        "doc_role": meta.get("doc_role"),
        "paper_title": meta.get("paper_title"),
        "project_id": meta.get("project_id"),
        "content_hash": content_hash(text),
        "char_count": len(text),
        "text_quality_score": meta.get("text_quality_score"),
        "text_quality_warning": meta.get("text_quality_warning"),
        "preview": " ".join(text.split())[:280],
    }


def sources_from_docs(docs: Sequence[dict[str, Any]]) -> set[str]:
    return {str(d.get("source") or "").strip() for d in docs if str(d.get("source") or "").strip()}


def mean_or_none(values: Sequence[float | int | None]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    return round(mean(clean), 3) if clean else None


def percent(numer: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return round(100.0 * numer / denom, 1)


def row_ok(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics") or {}
    return bool(metrics.get("ok"))


def summarize_run(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    no_error = [r for r in rows if not r.get("error")]
    route_cases = [r for r in no_error if (r.get("metrics") or {}).get("route_ok") is not None]
    source_cases = [r for r in no_error if (r.get("metrics") or {}).get("required_sources_hit") is not None]
    citation_cases = [
        r
        for r in no_error
        if (r.get("citation_validation") or {}).get("ok") is not None
    ]
    return {
        "cases": total,
        "errors": total - len(no_error),
        "ok": sum(1 for r in rows if row_ok(r)),
        "route_accuracy_pct": percent(
            sum(1 for r in route_cases if (r.get("metrics") or {}).get("route_ok")),
            len(route_cases),
        ),
        "required_source_hit_pct": percent(
            sum(1 for r in source_cases if (r.get("metrics") or {}).get("required_sources_hit")),
            len(source_cases),
        ),
        "citation_ok_pct": percent(
            sum(1 for r in citation_cases if (r.get("citation_validation") or {}).get("ok")),
            len(citation_cases),
        ),
        "avg_latency_sec": mean_or_none([(r.get("metrics") or {}).get("latency_sec") for r in no_error]),
        "avg_paper_docs": mean_or_none([(r.get("metrics") or {}).get("paper_doc_count") for r in no_error]),
        "avg_sop_docs": mean_or_none([(r.get("metrics") or {}).get("sop_doc_count") for r in no_error]),
        "avg_distinct_sources": mean_or_none(
            [(r.get("metrics") or {}).get("distinct_source_count") for r in no_error]
        ),
    }


def run_score(summary: dict[str, Any]) -> float:
    """Simple ranking score. Hard safety gates should still be reviewed manually."""
    route = float(summary.get("route_accuracy_pct") or 0.0) / 100.0
    source = float(summary.get("required_source_hit_pct") or 0.0) / 100.0
    citation_raw = summary.get("citation_ok_pct")
    citation = 1.0 if citation_raw is None else float(citation_raw) / 100.0
    error_penalty = min(0.5, float(summary.get("errors") or 0) * 0.1)
    latency = float(summary.get("avg_latency_sec") or 0.0)
    latency_penalty = min(0.15, latency / 200.0)
    return round(0.35 * source + 0.30 * route + 0.25 * citation + 0.10 - error_penalty - latency_penalty, 4)
