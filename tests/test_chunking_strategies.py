# -*- coding: utf-8 -*-

import unittest

from langchain_core.documents import Document

from chunking import ChunkingConfig, split_document


class TestChunkingStrategies(unittest.TestCase):
    def test_header_aware_metadata(self) -> None:
        doc = Document(page_content="# Methods\n\nMix 10 mM buffer.\n\n# Results\n\nSignal increased.", metadata={"source": "papers/a.pdf", "doc_type": "paper"})
        chunks = split_document(doc, ChunkingConfig(strategy="header_aware", chunk_size=80, chunk_overlap=0))
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].metadata["chunk_strategy"], "header_aware")
        self.assertEqual(chunks[0].metadata["section_type"], "methods")
        self.assertIn("chunk_index", chunks[0].metadata)

    def test_parent_child_metadata(self) -> None:
        text = "## Operation\n\n" + ("Step one. Warning: calibrate before use. " * 30)
        chunks = split_document(
            Document(page_content=text, metadata={"source": "manuals/sop.docx", "doc_type": "sop"}),
            ChunkingConfig(strategy="parent_child", child_chunk_size=120, child_chunk_overlap=10, parent_chunk_size=300, parent_chunk_overlap=20),
        )
        self.assertTrue(chunks)
        self.assertEqual(chunks[0].metadata["chunk_strategy"], "parent_child")
        self.assertEqual(chunks[0].metadata["chunk_role"], "child")
        self.assertIn("parent_id", chunks[0].metadata)
        self.assertIn("parent_text_preview", chunks[0].metadata)

    def test_semantic_placeholder_no_dependency(self) -> None:
        doc = Document(page_content="Abstract\n\nA short paragraph.\n\nMethods\n\nAnother paragraph.", metadata={"source": "papers/a.pdf"})
        chunks = split_document(doc, ChunkingConfig(strategy="semantic_placeholder", chunk_size=40))
        self.assertTrue(chunks)
        self.assertEqual(chunks[0].metadata["chunk_strategy"], "semantic_placeholder")


if __name__ == "__main__":
    unittest.main()
