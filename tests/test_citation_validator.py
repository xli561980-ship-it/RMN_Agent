# -*- coding: utf-8 -*-

import unittest

from langchain_core.documents import Document

from citation_validator import allowed_citation_hints, validate_answer_citations


class TestCitationValidator(unittest.TestCase):
    def test_allowed_hints_match_context_format(self) -> None:
        docs = [Document(page_content="x", metadata={"source": "papers/a.pdf", "page": 3, "doc_role": "main_text"})]
        hints = allowed_citation_hints(docs, [])
        self.assertIn("[Source: `papers/a.pdf` p.3]", hints)

    def test_unknown_hint_fails(self) -> None:
        docs = [Document(page_content="x", metadata={"source": "papers/a.pdf", "page": 3, "doc_role": "main_text"})]
        result = validate_answer_citations(
            "Claim. [Source: `papers/b.pdf` p.9]",
            paper_docs=docs,
            sop_docs=[],
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.unknown_hints, ["[Source: `papers/b.pdf` p.9]"])

    def test_numeric_claim_without_citation_fails(self) -> None:
        docs = [Document(page_content="x", metadata={"source": "papers/a.pdf", "page": 3, "doc_role": "main_text"})]
        result = validate_answer_citations("Heat at 37 °C for 10 min.", paper_docs=docs, sop_docs=[])
        self.assertFalse(result.ok)
        self.assertTrue(result.missing_citation_numeric_claims)


if __name__ == "__main__":
    unittest.main()
