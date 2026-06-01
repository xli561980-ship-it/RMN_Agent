# -*- coding: utf-8 -*-
"""最小测试：论文 scope 过滤合并、paper_k、fusion system 组装。"""

import unittest

from langchain_core.documents import Document

from fusion_prompts import compose_fusion_system_prompt
from fusion_scope import (
    build_paper_scope_chroma_filter,
    effective_paper_k,
    rerank_paper_docs_by_title_hint,
    title_similarity_for_scope,
)
from query_analyzer import normalize_analysis


class TestPaperScopeFilter(unittest.TestCase):
    def test_ui_source_overrides_analysis(self) -> None:
        a = normalize_analysis(
            {
                "intent": "PAPER_ONLY",
                "paper_scope_source": "papers/from_llm.pdf",
                "search_queries": {"paper_query": "q", "sop_query": "q"},
            }
        )
        flt, locked, hint = build_paper_scope_chroma_filter(a, "papers/ui_anchor.pdf")
        self.assertTrue(locked)
        self.assertEqual(flt, {"source": "papers/ui_anchor.pdf"})
        self.assertIsNone(hint)

    def test_unscoped_when_empty(self) -> None:
        a = normalize_analysis({"intent": "HYBRID", "search_queries": {"paper_query": "x", "sop_query": "x"}})
        flt, locked, hint = build_paper_scope_chroma_filter(a, None)
        self.assertIsNone(flt)
        self.assertFalse(locked)
        self.assertIsNone(hint)

    def test_ui_none_placeholder_ignored(self) -> None:
        a = normalize_analysis(
            {
                "paper_scope_source": "papers/from_analysis.pdf",
                "search_queries": {"paper_query": "x", "sop_query": "x"},
            }
        )
        flt, locked, hint = build_paper_scope_chroma_filter(a, "(None — all papers in library)")
        self.assertTrue(locked)
        self.assertEqual(flt, {"source": "papers/from_analysis.pdf"})
        self.assertIsNone(hint)

    def test_ui_none_placeholder_no_analysis_scope(self) -> None:
        a = normalize_analysis({"intent": "HYBRID", "search_queries": {"paper_query": "x", "sop_query": "x"}})
        flt, locked, hint = build_paper_scope_chroma_filter(a, "(None — all papers in library)")
        self.assertIsNone(flt)
        self.assertFalse(locked)
        self.assertIsNone(hint)

    def test_project_id_from_analysis(self) -> None:
        a = normalize_analysis(
            {
                "paper_scope_project_id": "my_proj_slug",
                "search_queries": {"paper_query": "x", "sop_query": "x"},
            }
        )
        flt, locked, hint = build_paper_scope_chroma_filter(a, None)
        self.assertTrue(locked)
        self.assertEqual(flt, {"project_id": "my_proj_slug"})
        self.assertIsNone(hint)

    def test_paper_title_not_in_chroma_filter_returns_soft_hint(self) -> None:
        a = normalize_analysis(
            {
                "paper_scope_paper_title": "My Exact Title",
                "paper_scope_project_id": "proj_a",
                "search_queries": {"paper_query": "x", "sop_query": "x"},
            }
        )
        flt, locked, hint = build_paper_scope_chroma_filter(a, None)
        self.assertEqual(flt, {"project_id": "proj_a"})
        self.assertTrue(locked)
        self.assertEqual(hint, "My Exact Title")
        self.assertNotIn("paper_title", flt)

    def test_title_only_unlocked_with_hint(self) -> None:
        a = normalize_analysis(
            {
                "paper_scope_paper_title": "Some title",
                "search_queries": {"paper_query": "x", "sop_query": "x"},
            }
        )
        flt, locked, hint = build_paper_scope_chroma_filter(a, None)
        self.assertIsNone(flt)
        self.assertFalse(locked)
        self.assertEqual(hint, "Some title")


class TestTitleSoftMatch(unittest.TestCase):
    def test_punctuation_case_insensitive(self) -> None:
        a = "Deep Learning for RMN: A Study."
        b = "deep learning for rmn a study"
        self.assertGreater(title_similarity_for_scope(a, b), 0.85)

    def test_rerank_prefers_matching_paper(self) -> None:
        d_wrong = Document(page_content="x", metadata={"paper_title": "Other Paper"})
        d_right = Document(page_content="y", metadata={"paper_title": "Target Paper Title"})
        pool = [d_wrong, d_wrong, d_right]
        out, note = rerank_paper_docs_by_title_hint(
            pool,
            "target paper title",
            "methods",
            k=2,
        )
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].metadata["paper_title"], "Target Paper Title")
        self.assertEqual(note, "")

    def test_rerank_weak_hint_falls_back_to_embedding_order(self) -> None:
        d1 = Document(page_content="a", metadata={"paper_title": "Alpha"})
        d2 = Document(page_content="b", metadata={"paper_title": "Beta"})
        pool = [d1, d2]
        out, note = rerank_paper_docs_by_title_hint(pool, "completely unrelated xyz", "query", k=2)
        self.assertEqual(out, [d1, d2])
        self.assertIn("embedding", note.lower())


class TestEffectivePaperK(unittest.TestCase):
    def test_scholarly_raises_k(self) -> None:
        self.assertEqual(effective_paper_k(5, "SCHOLARLY", False), 8)

    def test_locked_raises_k(self) -> None:
        self.assertEqual(effective_paper_k(3, "OPERATIONAL", True), 8)


class TestComposePrompt(unittest.TestCase):
    def test_scholarly_contains_mode_rules(self) -> None:
        text = compose_fusion_system_prompt(
            "SCHOLARLY",
            paper_context="ctx p",
            sop_context="ctx s",
        )
        self.assertIn("SCHOLARLY", text)
        self.assertIn("citation_hint", text)
        self.assertIn("Never merge citations", text)
        self.assertIn("Never create bare page citations", text)
        self.assertIn("ctx p", text)
        self.assertNotIn("Complete protocol", text)

    def test_protocol_rigor_block_when_enabled(self) -> None:
        text = compose_fusion_system_prompt(
            "SCHOLARLY",
            paper_context="ctx p",
            sop_context="ctx s",
            protocol_rigor_appendix=True,
            retrieved_paper_sources_summary="Distinct paper `source` values (2): papers/a.pdf, papers/b.pdf.",
            paper_only_intent=True,
        )
        self.assertIn("Complete protocol", text)
        self.assertIn("Cross-paper differences", text)
        self.assertIn("papers/a.pdf", text)
        self.assertIn("Paper-only routing", text)


if __name__ == "__main__":
    unittest.main()
