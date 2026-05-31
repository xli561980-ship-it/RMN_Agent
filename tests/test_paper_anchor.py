# -*- coding: utf-8 -*-

import unittest

from paper_anchor import (
    enrich_analysis_with_paper_anchor,
    extract_paper_entities,
    extract_title_hints,
    has_strong_paper_anchor_signal,
    is_corpus_level_question,
    references_paper_deictically,
    resolve_best_source,
    resolve_source_candidates,
    resolve_sources_by_title_hint,
)

WANG_SOURCE = (
    "papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels "
    "Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf"
)


class TestPaperAnchor(unittest.TestCase):
    def test_wang_entity_variants_resolve_to_wang_source(self) -> None:
        queries = [
            "Wang 2025 的 microfluidic fabrication 参数是什么？",
            "Wang 论文里 laser actuation 条件",
            "Photothermally Powered 3D Microgels 的制备流程",
            "3D Microgels mechanically regulate MSCs 的机制",
        ]
        for q in queries:
            with self.subTest(query=q):
                analysis = enrich_analysis_with_paper_anchor({"intent": "PAPER_ONLY"}, q)
                self.assertEqual(analysis["paper_scope_source"], WANG_SOURCE)

    def test_ui_anchor_forced_on_deictic_microgel(self) -> None:
        ui_anchor = "papers/ui-selected-wang.pdf"
        q = "如果我要参考论文里的 microgel 参数做一次实验"
        self.assertTrue(references_paper_deictically(q))
        analysis = enrich_analysis_with_paper_anchor(
            {"intent": "HYBRID", "paper_scope_source": None},
            q,
            paper_anchor=ui_anchor,
        )
        self.assertEqual(analysis["paper_scope_source"], ui_anchor)
        self.assertEqual(analysis["paper_scope_source_hint"], ui_anchor)

    def test_corpus_level_question_does_not_mis_anchor(self) -> None:
        q = "这些文献是否证明了该 microgel 方法在所有干细胞类型中都有效？"
        self.assertTrue(is_corpus_level_question(q))
        analysis = enrich_analysis_with_paper_anchor(
            {"intent": "PAPER_ONLY", "paper_scope_source": None},
            q,
            paper_anchor=None,
        )
        self.assertIsNone(analysis.get("paper_scope_source"))

    def test_soft_match_returns_multiple_microgel_candidates_with_confidence(self) -> None:
        candidates = resolve_source_candidates("3D Microgels")
        self.assertGreaterEqual(len(candidates), 2)
        scores = [score for score, _ in candidates]
        self.assertTrue(all(0.0 < s <= 1.0 for s in scores))
        self.assertEqual(scores, sorted(scores, reverse=True))
        sources = [src for _, src in candidates]
        self.assertTrue(any("Wang" in src for src in sources))
        self.assertGreaterEqual(scores[0], scores[-1])

    def test_forced_gold_source_anchor_not_in_default_enrich(self) -> None:
        """Production enrich must never inject eval-only forced gold anchors."""
        q = "这些文献是否证明了该 microgel 方法在所有干细胞类型中都有效？"
        case_gold = [WANG_SOURCE]
        analysis = enrich_analysis_with_paper_anchor({}, q, paper_anchor=None)
        self.assertNotIn(
            analysis.get("paper_scope_source"),
            case_gold,
            "Default pipeline must not force gold source from eval labels",
        )
        self.assertFalse(hasattr(enrich_analysis_with_paper_anchor, "forced_gold_source_anchor"))

        from eval.run_query_anchor_ablation import _forced_gold_analysis

        forced = _forced_gold_analysis(
            {"gold_sources": case_gold},
            {"intent": "PAPER_ONLY", "paper_scope_source": None},
        )
        self.assertEqual(forced["paper_scope_source"], WANG_SOURCE)

    def test_extract_entities_and_title_hints(self) -> None:
        ents = extract_paper_entities("Photothermally Powered 3D Microgels with microfluidic fabrication")
        self.assertTrue(any("Photothermally" in e for e in ents))
        hints = extract_title_hints("如果我要参考论文里的 microgel 参数做一次实验")
        self.assertIn("Photothermally Powered 3D Microgels", hints)

    def test_resolve_sources_by_title_hint_wang(self) -> None:
        matches = resolve_sources_by_title_hint("Photothermally Powered 3D Microgels")
        self.assertTrue(matches)
        self.assertEqual(resolve_best_source("Photothermally Powered 3D Microgels"), WANG_SOURCE)

    def test_strong_anchor_signal(self) -> None:
        self.assertTrue(has_strong_paper_anchor_signal("Wang 2025 microgel protocol"))
        self.assertFalse(has_strong_paper_anchor_signal("这些文献里的 microgel 方法"))


if __name__ == "__main__":
    unittest.main()
