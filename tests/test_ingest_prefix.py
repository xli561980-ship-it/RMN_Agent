# -*- coding: utf-8 -*-
"""Paper chunk `[DOC]` embedding prefix (ingest)."""

import unittest

from ingest import _paper_embedding_prefix_line


class TestPaperEmbeddingPrefix(unittest.TestCase):
    def test_sop_gets_no_prefix(self) -> None:
        self.assertEqual(
            _paper_embedding_prefix_line({"doc_type": "sop", "source": "manuals/SOP.docx"}),
            "",
        )

    def test_paper_prefix_shape(self) -> None:
        line = _paper_embedding_prefix_line(
            {
                "doc_type": "paper",
                "paper_title": "My Paper Title",
                "source": "papers/foo.pdf",
                "project_id": "slug_abcd1234",
                "doc_role": "main_text",
            }
        )
        self.assertTrue(line.startswith("[DOC] title: My Paper Title | source: papers/foo.pdf"))
        self.assertIn("project_id: slug_abcd1234", line)
        self.assertIn("doc_role: main_text", line)
        self.assertTrue(line.endswith("\n"))

    def test_unknown_title_uses_filename_stem(self) -> None:
        line = _paper_embedding_prefix_line(
            {
                "doc_type": "paper",
                "paper_title": "unknown_title",
                "source": "papers/Deep_Learning_RMN.pdf",
                "project_id": "p1",
                "doc_role": "supplementary_info",
            }
        )
        self.assertIn("title: Deep Learning RMN", line)


if __name__ == "__main__":
    unittest.main()
