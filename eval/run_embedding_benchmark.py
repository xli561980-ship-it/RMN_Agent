#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare embedding providers/models with retrieval metrics."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_utils import corpus_preflight, ensure_report_dir, markdown_table, timestamp, write_json  # noqa: E402
from eval.run_retrieval_eval import evaluate as run_retrieval  # noqa: E402


def _provider_model(provider: str) -> str:
    if provider in {"local_hash", "hash", "offline"}:
        return f"local_hash_dim_{os.getenv('LOCAL_HASH_EMBEDDING_DIM', '384')}"
    if provider in {"google", "gemini"}:
        return os.getenv("GOOGLE_EMBEDDING_MODEL", "gemini-embedding-001")
    if provider == "openai":
        return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    if provider == "zhipu":
        return os.getenv("ZHIPU_EMBEDDING_MODEL", "embedding-2")
    if provider == "bge_m3":
        return os.getenv("HF_EMBEDDING_MODEL", "BAAI/bge-m3")
    if provider == "e5":
        return os.getenv("E5_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
    return os.getenv("HF_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")


def _check_provider(provider: str) -> str:
    if provider in {"google", "gemini"} and not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        return "missing GOOGLE_API_KEY/GEMINI_API_KEY"
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return "missing OPENAI_API_KEY"
    if provider == "zhipu" and not os.getenv("ZHIPU_API_KEY"):
        return "missing ZHIPU_API_KEY"
    if provider in {"huggingface", "bge_m3", "e5"}:
        try:
            import sentence_transformers  # type: ignore  # noqa: F401
        except Exception as exc:
            return f"missing sentence-transformers: {exc}"
    return ""


def _rebuild(provider: str, rebuild: bool) -> tuple[bool, str, float]:
    if not rebuild:
        return False, "未传入 --rebuild，未重建索引；指标反映当前 Chroma。", 0.0
    env = dict(os.environ)
    env.update({"EMBEDDING_PROVIDER": provider, "REBUILD_CHROMA": "1"})
    start = time.perf_counter()
    proc = subprocess.run([sys.executable, str(ROOT / "ingest.py")], cwd=str(ROOT), env=env, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        return True, f"index build failed: {proc.stderr.strip() or proc.stdout.strip()}", elapsed
    return True, "index build ok", elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run embedding benchmark.")
    parser.add_argument("--providers", default="google,bge_m3,e5")
    parser.add_argument("--rebuild", action="store_true", help="明确允许每个 provider 重建 Chroma。")
    parser.add_argument("-k", "--k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "golden_questions.jsonl")
    parser.add_argument("--evidence", type=Path, default=ROOT / "eval" / "gold_evidence.jsonl")
    parser.add_argument("--report-dir", type=Path, default=Path(os.getenv("EVAL_REPORT_DIR", "eval/reports")))
    args = parser.parse_args()
    report_dir = ensure_report_dir(args.report_dir if args.report_dir.is_absolute() else ROOT / args.report_dir)
    rows: list[dict[str, Any]] = []
    for provider in [p.strip() for p in args.providers.split(",") if p.strip()]:
        skip = _check_provider(provider)
        if skip:
            rows.append({"embedding_provider": provider, "embedding_model": _provider_model(provider), "skipped": True, "notes": f"provider skipped: {skip}"})
            continue
        rebuilt, note, build_time = _rebuild(provider, args.rebuild)
        os.environ["EMBEDDING_PROVIDER"] = provider
        start = time.perf_counter()
        try:
            result = run_retrieval(args.questions, args.evidence, k=args.k, report_dir=report_dir)
            metrics = result.get("metrics") or {}
        except Exception as exc:
            metrics = {"error": str(exc)}
        latency = (time.perf_counter() - start) * 1000
        rows.append(
            {
                "embedding_provider": provider,
                "embedding_model": _provider_model(provider),
                "skipped": False,
                f"recall@{args.k}": metrics.get(f"recall@{args.k}", 0),
                f"precision@{args.k}": metrics.get(f"precision@{args.k}", 0),
                "mrr": metrics.get("mrr", 0),
                f"ndcg@{args.k}": metrics.get(f"ndcg@{args.k}", 0),
                "doc_type_accuracy": metrics.get("doc_type_accuracy", 0),
                "sop_boundary_accuracy": metrics.get("sop_boundary_accuracy", 0),
                "paper_to_sop_confusion_rate": metrics.get("paper_to_sop_confusion_rate", 0),
                "avg_retrieval_latency_ms": metrics.get("avg_retrieval_latency_ms", round(latency, 2)),
                "index_build_time_sec": round(build_time, 2),
                "total_chunks": 0,
                "notes": note,
                "rebuilt": rebuilt,
            }
        )
    payload = {"rows": rows, "k": args.k, "preflight_warnings": corpus_preflight()}
    stamp = timestamp()
    json_path = report_dir / f"embedding_benchmark_{stamp}.json"
    md_path = report_dir / f"embedding_benchmark_{stamp}.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload, args.k), encoding="utf-8")
    print(f"embedding benchmark report: {md_path}")
    return 0


def render_markdown(payload: dict[str, Any], k: int) -> str:
    rows = payload["rows"]
    warnings = payload.get("preflight_warnings") or []
    warning_text = ""
    if warnings:
        warning_text = "## Preflight Warnings\n\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n"
    return "# Embedding Benchmark\n\n" + warning_text + markdown_table(
        ["provider", "model", f"recall@{k}", f"precision@{k}", "mrr", f"ndcg@{k}", "doc_type_accuracy", "latency_ms", "notes"],
        [
            (
                r.get("embedding_provider"),
                r.get("embedding_model"),
                round(float(r.get(f"recall@{k}") or 0), 3),
                round(float(r.get(f"precision@{k}") or 0), 3),
                round(float(r.get("mrr") or 0), 3),
                round(float(r.get(f"ndcg@{k}") or 0), 3),
                round(float(r.get("doc_type_accuracy") or 0), 3),
                r.get("avg_retrieval_latency_ms", ""),
                r.get("notes", ""),
            )
            for r in rows
        ],
    ) + "\n\n中文问题检索英文论文时，请重点观察 recall/MRR 与失败问题列表；本报告不会自动解释语义失败原因。\n"


if __name__ == "__main__":
    raise SystemExit(main())
