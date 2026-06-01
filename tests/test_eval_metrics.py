# -*- coding: utf-8 -*-

import unittest

from eval.metrics import doc_type_accuracy, mrr, ndcg_at_k, precision_at_k, recall_at_k, source_coverage


class TestEvalMetrics(unittest.TestCase):
    def test_recall_precision_mrr(self) -> None:
        results = ["a", "b", "c"]
        gold = ["b", "x"]
        self.assertAlmostEqual(recall_at_k(results, gold, 2), 0.5)
        self.assertAlmostEqual(precision_at_k(results, gold, 2), 0.5)
        self.assertAlmostEqual(mrr(results, gold), 0.5)

    def test_ndcg(self) -> None:
        self.assertAlmostEqual(ndcg_at_k([1, 0, 1], 3), 0.9197, places=3)

    def test_source_and_doc_type(self) -> None:
        self.assertAlmostEqual(source_coverage(["a", "b"], ["b", "c"]), 0.5)
        self.assertAlmostEqual(doc_type_accuracy(["paper", "sop", "paper"], ["paper"]), 2 / 3)


if __name__ == "__main__":
    unittest.main()
