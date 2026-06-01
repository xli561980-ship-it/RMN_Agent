#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare two or more experiment JSONL runs and optionally write a Markdown report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.experiment_utils import (  # noqa: E402
    REPORTS_DIR,
    load_jsonl,
    row_ok,
    run_score,
    summarize_run,
)


def _run_label(path: Path, rows: Sequence[dict[str, Any]]) -> str:
    if rows:
        rid = rows[0].get("run_id")
        if rid:
            return str(rid)
    return path.stem


def _case_map(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("case_id") or ""): row for row in rows}


def _fmt_pct(value: Any) -> str:
    return "n/a" if value is None else f"{value}%"


def _fmt_float(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _case_status(row: dict[str, Any] | None) -> str:
    if row is None:
        return "missing"
    if row.get("error"):
        return "error"
    return "pass" if row_ok(row) else "fail"


def _metric(row: dict[str, Any] | None, key: str) -> Any:
    if row is None:
        return None
    return (row.get("metrics") or {}).get(key)


def _missing_count(row: dict[str, Any] | None) -> int:
    missing = _metric(row, "missing_required_sources") or []
    return len(missing)


def _describe_case_delta(base: dict[str, Any] | None, cand: dict[str, Any] | None) -> str | None:
    if base is None and cand is not None:
        return "new case in candidate run"
    if base is not None and cand is None:
        return "case missing from candidate run"
    if base is None or cand is None:
        return None

    parts: list[str] = []
    if _case_status(base) != _case_status(cand):
        parts.append(f"status {_case_status(base)} -> {_case_status(cand)}")
    if _metric(base, "got_route") != _metric(cand, "got_route"):
        parts.append(f"route {_metric(base, 'got_route')!r} -> {_metric(cand, 'got_route')!r}")
    if _missing_count(base) != _missing_count(cand):
        parts.append(f"missing required sources {_missing_count(base)} -> {_missing_count(cand)}")
    if _metric(base, "paper_doc_count") != _metric(cand, "paper_doc_count"):
        parts.append(f"paper docs {_metric(base, 'paper_doc_count')} -> {_metric(cand, 'paper_doc_count')}")
    if _metric(base, "sop_doc_count") != _metric(cand, "sop_doc_count"):
        parts.append(f"sop docs {_metric(base, 'sop_doc_count')} -> {_metric(cand, 'sop_doc_count')}")

    base_cv = base.get("citation_validation") or {}
    cand_cv = cand.get("citation_validation") or {}
    if base_cv.get("ok") != cand_cv.get("ok"):
        parts.append(f"citation {base_cv.get('ok')} -> {cand_cv.get('ok')}")
    return "; ".join(parts) if parts else None


def _is_regression(base: dict[str, Any] | None, cand: dict[str, Any] | None) -> bool:
    if base is None:
        return False
    if cand is None:
        return True
    if row_ok(base) and not row_ok(cand):
        return True
    if _missing_count(cand) > _missing_count(base):
        return True
    if _metric(base, "route_ok") is True and _metric(cand, "route_ok") is False:
        return True
    base_cv = base.get("citation_validation") or {}
    cand_cv = cand.get("citation_validation") or {}
    return base_cv.get("ok") is True and cand_cv.get("ok") is False


def _is_improvement(base: dict[str, Any] | None, cand: dict[str, Any] | None) -> bool:
    if cand is None:
        return False
    if base is None:
        return True
    if not row_ok(base) and row_ok(cand):
        return True
    if _missing_count(cand) < _missing_count(base):
        return True
    if _metric(base, "route_ok") is False and _metric(cand, "route_ok") is True:
        return True
    base_cv = base.get("citation_validation") or {}
    cand_cv = cand.get("citation_validation") or {}
    return base_cv.get("ok") is False and cand_cv.get("ok") is True


def build_report(run_paths: Sequence[Path]) -> str:
    loaded = [(path, load_jsonl(path)) for path in run_paths]
    if not loaded:
        raise SystemExit("Provide at least one run JSONL")

    labels = [_run_label(path, rows) for path, rows in loaded]
    summaries = [summarize_run(rows) for _, rows in loaded]
    scores = [run_score(summary) for summary in summaries]

    lines: list[str] = []
    lines.append("# RMN Agent Run Comparison")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Run | Cases | OK | Errors | Route | Required source | Citation | Avg latency | Score |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, summary, score in zip(labels, summaries, scores):
        lines.append(
            f"| `{label}` | {summary['cases']} | {summary['ok']} | {summary['errors']} | "
            f"{_fmt_pct(summary['route_accuracy_pct'])} | "
            f"{_fmt_pct(summary['required_source_hit_pct'])} | "
            f"{_fmt_pct(summary['citation_ok_pct'])} | "
            f"{_fmt_float(summary['avg_latency_sec'])} | {score} |"
        )

    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    if summaries[best_idx].get("errors"):
        lines.append(
            f"- Highest score is `{labels[best_idx]}`, but it has errors; do not promote without inspecting failures."
        )
    else:
        lines.append(f"- Best candidate by automatic score: `{labels[best_idx]}`.")
    lines.append("- Treat this as a regression screen, not a full answer-quality judgment.")

    if len(loaded) >= 2:
        base_label = labels[0]
        base_map = _case_map(loaded[0][1])
        for idx, (label, rows) in enumerate(zip(labels[1:], [x[1] for x in loaded[1:]]), start=1):
            cand_map = _case_map(rows)
            case_ids = sorted(set(base_map) | set(cand_map))
            regressions: list[str] = []
            improvements: list[str] = []
            neutral_changes: list[str] = []
            for cid in case_ids:
                base = base_map.get(cid)
                cand = cand_map.get(cid)
                delta = _describe_case_delta(base, cand)
                if not delta:
                    continue
                line = f"- `{cid}`: {delta}"
                if _is_regression(base, cand):
                    regressions.append(line)
                elif _is_improvement(base, cand):
                    improvements.append(line)
                else:
                    neutral_changes.append(line)

            lines.append("")
            lines.append(f"## `{label}` vs `{base_label}`")
            lines.append("")
            lines.append("### Regressions")
            lines.extend(regressions or ["- None detected by automatic checks."])
            lines.append("")
            lines.append("### Improvements")
            lines.extend(improvements or ["- None detected by automatic checks."])
            lines.append("")
            lines.append("### Other Changes")
            lines.extend(neutral_changes[:30] or ["- None."])
            if len(neutral_changes) > 30:
                lines.append(f"- ... {len(neutral_changes) - 30} more")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+", help="Run JSONL files from eval/runs/")
    parser.add_argument("--out", type=Path, default=None, help="Optional Markdown report path.")
    args = parser.parse_args()
    report = build_report(args.runs)
    print(report)
    if args.out:
        out = args.out
        if not out.is_absolute():
            out = REPORTS_DIR / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Saved report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
