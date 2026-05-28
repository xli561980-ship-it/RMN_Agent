#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline-ish retrieval/citation smoke evaluation for RMN Agent.

This script avoids LLM generation by default. It checks that query analysis,
retrieval, and source coverage are sane for a small golden set. Use it before
demoing, and extend `golden_questions.jsonl` as the corpus grows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_core import fusion_prepare  # noqa: E402


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _sources_from_bundle(bundle: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("paper_docs", "sop_docs"):
        for doc in bundle.get(key) or []:
            src = str((doc.metadata or {}).get("source") or "").strip()
            if src:
                out.add(src)
    return out


def run_eval(path: Path, *, k: int) -> int:
    cases = _load_jsonl(path)
    if not cases:
        print(f"No cases in {path}")
        return 1

    failures = 0
    for case in cases:
        cid = case.get("id") or "(no id)"
        q = str(case.get("question") or "")
        expected_route = str(case.get("expected_route") or "")
        required_sources = [str(x) for x in (case.get("required_sources") or [])]
        try:
            bundle = fusion_prepare(q, k=k)
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {cid}: fusion_prepare failed: {exc}")
            continue
        analysis = bundle.get("analysis") or {}
        got_route = analysis.get("intent")
        sources = _sources_from_bundle(bundle)
        route_ok = not expected_route or got_route == expected_route
        missing = [s for s in required_sources if s not in sources]
        ok = route_ok and not missing
        if not ok:
            failures += 1
        status = "PASS" if ok else "FAIL"
        print(
            f"[{status}] {cid} route={got_route!r} expected={expected_route!r} "
            f"paper={len(bundle.get('paper_docs') or [])} sop={len(bundle.get('sop_docs') or [])}"
        )
        if missing:
            print(f"       missing required sources: {missing}")
        if sources:
            preview = ", ".join(sorted(sources)[:8])
            extra = f" (+{len(sources) - 8} more)" if len(sources) > 8 else ""
            print(f"       sources: {preview}{extra}")
    print(f"\nCases: {len(cases)}; failures: {failures}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval smoke eval against golden questions.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()
    return run_eval(args.questions, k=args.k)


if __name__ == "__main__":
    raise SystemExit(main())
