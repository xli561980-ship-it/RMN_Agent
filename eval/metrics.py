# -*- coding: utf-8 -*-
"""Pure-Python metrics used by RMN Agent retrieval benchmarks."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any


def _top(items: Sequence[Any], k: int) -> list[Any]:
    return list(items[: max(0, int(k))])


def recall_at_k(results: Sequence[Any], gold: Sequence[Any], k: int) -> float:
    """Fraction of gold items found in the first k results."""
    gold_set = {x for x in gold if x is not None and str(x) != ""}
    if not gold_set:
        return 0.0
    hit = {x for x in _top(results, k) if x in gold_set}
    return len(hit) / len(gold_set)


def precision_at_k(results: Sequence[Any], gold: Sequence[Any], k: int) -> float:
    """Fraction of first k results that match a gold item."""
    top = _top(results, k)
    if not top:
        return 0.0
    gold_set = {x for x in gold if x is not None and str(x) != ""}
    if not gold_set:
        return 0.0
    return sum(1 for x in top if x in gold_set) / len(top)


def mrr(results: Sequence[Any], gold: Sequence[Any]) -> float:
    """Mean reciprocal rank for a single query."""
    gold_set = {x for x in gold if x is not None and str(x) != ""}
    if not gold_set:
        return 0.0
    for idx, item in enumerate(results, start=1):
        if item in gold_set:
            return 1.0 / idx
    return 0.0


def ndcg_at_k(relevances: Sequence[float | int | bool], k: int) -> float:
    """Simplified nDCG@k from per-rank relevance values."""
    vals = [float(x) for x in _top(relevances, k)]
    if not vals:
        return 0.0
    dcg = sum(rel / math.log2(rank + 1) for rank, rel in enumerate(vals, start=1))
    ideal = sorted((float(x) for x in relevances), reverse=True)[: max(0, int(k))]
    idcg = sum(rel / math.log2(rank + 1) for rank, rel in enumerate(ideal, start=1))
    return 0.0 if idcg <= 0 else dcg / idcg


def source_coverage(retrieved_sources: Sequence[str], gold_sources: Sequence[str]) -> float:
    """How many expected sources appeared at least once."""
    gold = {s for s in gold_sources if s}
    if not gold:
        return 0.0
    got = {s for s in retrieved_sources if s}
    return len(got & gold) / len(gold)


def doc_type_accuracy(retrieved_doc_types: Sequence[str], expected_doc_types: Sequence[str]) -> float:
    """Fraction of retrieved chunks whose doc_type belongs to expected_doc_types."""
    got = [x for x in retrieved_doc_types if x]
    if not got:
        return 0.0
    expected = {x for x in expected_doc_types if x}
    if not expected:
        return 0.0
    return sum(1 for x in got if x in expected) / len(got)


def confusion_rate(results: Sequence[Any], is_confused: Callable[[Any], bool]) -> float:
    """Generic confusion fraction over returned results."""
    if not results:
        return 0.0
    return sum(1 for item in results if is_confused(item)) / len(results)
