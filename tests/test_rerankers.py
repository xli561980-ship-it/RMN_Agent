# -*- coding: utf-8 -*-

import unittest

from langchain_core.documents import Document

from rerankers import rerank_dual_path, rerank_documents, rule_rerank


class TestRerankers(unittest.TestCase):
    def test_rule_prefers_paper_for_paper_question(self) -> None:
        sop = Document(page_content="Safety warning and calibration.", metadata={"doc_type": "sop", "section_type": "safety"})
        paper = Document(page_content="Methods used 10 mM reagent for 30 min.", metadata={"doc_type": "paper", "section_type": "methods"})
        out = rule_rerank([sop, paper], "论文方法参数", {"intent": "PAPER_ONLY"}).docs
        self.assertEqual(out[0].metadata["doc_type"], "paper")
        self.assertIn("rerank_score", out[0].metadata)

    def test_rule_prefers_sop_for_operational_question(self) -> None:
        paper = Document(page_content="Results show signal.", metadata={"doc_type": "paper", "section_type": "results"})
        sop = Document(page_content="Warning: must calibrate before operation.", metadata={"doc_type": "sop", "section_type": "operation", "doc_role": "manual"})
        out = rule_rerank([paper, sop], "操作安全要求", {"intent": "SOP_ONLY"}).docs
        self.assertEqual(out[0].metadata["doc_type"], "sop")

    def test_hybrid_query_keeps_sop_when_safety_requested(self) -> None:
        paper = Document(page_content="Methods used 10 mM reagent.", metadata={"doc_type": "paper", "section_type": "methods"})
        sop = Document(page_content="Safety warning: must wear protection.", metadata={"doc_type": "sop", "section_type": "safety"})
        out = rule_rerank([paper, sop], "参考论文参数时有哪些 SOP 安全限制", {"intent": "HYBRID", "answer_mode": "HYBRID"}, final_k=2).docs
        self.assertEqual({d.metadata["doc_type"] for d in out}, {"paper", "sop"})
        self.assertEqual(out[0].metadata["doc_type"], "sop")

    def test_dual_path_rerank_preserves_path_lists(self) -> None:
        paper = Document(
            page_content="Microfluidic fabrication with gold nanorods.",
            metadata={"doc_type": "paper", "section_type": "methods", "paper_title": "Target Paper"},
        )
        generic = Document(
            page_content="Alginate microgel guidelines.",
            metadata={"doc_type": "paper", "section_type": "results", "paper_title": "Generic microgel review"},
        )
        sop = Document(page_content="Safety Instructions and MSDS warning.", metadata={"doc_type": "sop", "section_type": "safety", "doc_role": "manual"})
        papers, sops, result = rerank_dual_path(
            [generic, paper],
            [sop],
            "参考论文 microfluidic 参数有哪些 SOP 安全限制",
            {"intent": "HYBRID", "answer_mode": "HYBRID", "paper_scope_paper_title": "Target Paper"},
            paper_limit=2,
            sop_limit=1,
        )
        self.assertEqual(len(papers), 2)
        self.assertEqual(len(sops), 1)
        self.assertEqual(papers[0].metadata["paper_title"], "Target Paper")
        self.assertIn("original_rank", papers[0].metadata)
        self.assertEqual(result.provider, "rule")

    def test_generalization_boosts_intro_section(self) -> None:
        intro = Document(page_content="mesenchymal stem cells in 3D microgels under specific forces.", metadata={"doc_type": "paper", "section_type": "introduction"})
        methods = Document(page_content="results signal only.", metadata={"doc_type": "paper", "section_type": "methods"})
        out = rule_rerank([methods, intro], "是否证明所有干细胞类型都有效", {"intent": "PAPER_ONLY"}, final_k=1).docs
        self.assertEqual(out[0].metadata["section_type"], "introduction")


if __name__ == "__main__":
    unittest.main()
