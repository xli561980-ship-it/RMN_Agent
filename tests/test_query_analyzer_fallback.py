# -*- coding: utf-8 -*-

import unittest

from query_analyzer import heuristic_analyze_query


class TestQueryAnalyzerFallback(unittest.TestCase):
    def test_sop_only(self) -> None:
        out = heuristic_analyze_query("Leica DMi8 manual safety 注意事项")
        self.assertEqual(out["intent"], "SOP_ONLY")
        self.assertEqual(out["answer_mode"], "OPERATIONAL")

    def test_filename_scope(self) -> None:
        out = heuristic_analyze_query("请总结 Wang2025.pdf 的制备步骤")
        self.assertEqual(out["paper_scope_source"], "papers/Wang2025.pdf")
        self.assertTrue(out["requires_full_protocol"])

    def test_anchor_scope(self) -> None:
        out = heuristic_analyze_query("这篇论文的参数是什么", paper_anchor="papers/a.pdf")
        self.assertEqual(out["paper_scope_source"], "papers/a.pdf")

    def test_instrument_requirement_routes_to_sop(self) -> None:
        out = heuristic_analyze_query("Litesizer 500 做温度序列测量时，平衡时间有什么要求？")
        self.assertEqual(out["intent"], "SOP_ONLY")


if __name__ == "__main__":
    unittest.main()
