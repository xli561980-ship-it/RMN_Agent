# -*- coding: utf-8 -*-

import unittest

from eval.check_gold_evidence_alignment import check_evidence_row


class TestGoldEvidenceAlignment(unittest.TestCase):
    def test_ok_when_source_section_keywords_match(self) -> None:
        row = {
            "question_id": "demo",
            "source": "manuals/demo.pdf",
            "doc_type": "sop",
            "section": "Safety",
            "must_contain_any": ["PPE", "gloves"],
        }
        manifest = {"manuals/demo.pdf": "sop"}
        chunks = {
            "manuals/demo.pdf": [
                {"text": "Wear PPE and gloves before starting.", "doc_type": "sop", "section": "Safety Instructions"}
            ]
        }
        result = check_evidence_row(row, manifest_sources=manifest, chunks_by_source=chunks)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["issues"], [])

    def test_source_missing(self) -> None:
        row = {
            "question_id": "demo",
            "source": "missing/source.pdf",
            "doc_type": "paper",
            "section": "",
            "must_contain_any": ["microgel"],
        }
        result = check_evidence_row(row, manifest_sources={}, chunks_by_source={})
        self.assertEqual(result["status"], "source_missing")
        self.assertIn("source_missing", result["issues"])

    def test_doc_type_mismatch(self) -> None:
        row = {
            "question_id": "demo",
            "source": "papers/a.pdf",
            "doc_type": "sop",
            "section": "",
            "must_contain_any": ["microgel"],
        }
        manifest = {"papers/a.pdf": "paper"}
        chunks = {"papers/a.pdf": [{"text": "microgel study", "doc_type": "paper", "section": ""}]}
        result = check_evidence_row(row, manifest_sources=manifest, chunks_by_source=chunks)
        self.assertEqual(result["status"], "doc_type_mismatch")
        self.assertIn("doc_type_mismatch", result["issues"])

    def test_keywords_missing(self) -> None:
        row = {
            "question_id": "demo",
            "source": "papers/a.pdf",
            "doc_type": "paper",
            "section": "",
            "must_contain_any": ["nonexistent-token"],
        }
        manifest = {"papers/a.pdf": "paper"}
        chunks = {"papers/a.pdf": [{"text": "microgel study", "doc_type": "paper", "section": ""}]}
        result = check_evidence_row(row, manifest_sources=manifest, chunks_by_source=chunks)
        self.assertEqual(result["status"], "keywords_missing")
        self.assertIn("keywords_missing", result["issues"])

    def test_section_missing(self) -> None:
        row = {
            "question_id": "demo",
            "source": "papers/a.pdf",
            "doc_type": "paper",
            "section": "Methods",
            "must_contain_any": ["microgel"],
        }
        manifest = {"papers/a.pdf": "paper"}
        chunks = {"papers/a.pdf": [{"text": "microgel study", "doc_type": "paper", "section": "Introduction"}]}
        result = check_evidence_row(row, manifest_sources=manifest, chunks_by_source=chunks)
        self.assertIn("section_missing", result["issues"])


if __name__ == "__main__":
    unittest.main()
