#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional RAGAS evaluation wrapper."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import ensure_report_dir, load_jsonl, markdown_table, timestamp, write_json  # noqa: E402


def evaluate(questions_path: Path, *, report_dir: Path) -> dict[str, Any]:
    stamp = timestamp()
    json_path = report_dir / f"ragas_eval_{stamp}.json"
    md_path = report_dir / f"ragas_eval_{stamp}.md"
    try:
        import ragas  # type: ignore  # noqa: F401
    except ImportError:
        reason = "ragas is not installed. Install optional dependencies to run this evaluation."
        payload = {"skipped": True, "reason": reason, "metrics": {}, "cases": []}
        write_json(json_path, payload)
        md_path.write_text(f"# RAGAS Evaluation Report\n\n{reason}\n", encoding="utf-8")
        payload["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
        return payload

    cases = load_jsonl(questions_path)
    reason = (
        "RAGAS 已安装，但本项目默认 gold 文件只有 source/section 级证据，"
        "未强制提供 reference answer；faithfulness / answer_relevancy / "
        "context_precision / context_recall 需要先运行 generation eval 并补充 reference。"
    )
    payload: dict[str, Any] = {
        "skipped": False,
        "reason": reason,
        "supported_metrics": ["faithfulness", "answer_relevancy", "context_precision", "context_recall"],
        "cases": [{"id": c.get("id"), "has_reference_answer": bool(c.get("reference_answer"))} for c in cases],
        "metrics": {},
    }
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    payload["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# RAGAS Evaluation Report", "", payload.get("reason", ""), ""]
    lines.append(markdown_table(["metric", "status"], [(m, "requires generated answers/reference where applicable") for m in payload["supported_metrics"]]))
    lines.extend(["", "## Reference Coverage", ""])
    lines.append(markdown_table(["id", "has_reference_answer"], [(c["id"], c["has_reference_answer"]) for c in payload["cases"]]))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run optional RAGAS evaluation.")
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)
    payload = evaluate(args.questions, report_dir=report_dir)
    print(payload.get("reason") or f"ragas eval report: {payload['report_paths']['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
