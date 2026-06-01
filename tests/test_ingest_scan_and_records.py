# -*- coding: utf-8 -*-
"""Tests for ingest coverage and success-record semantics."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

import ingest


class TestIngestRecursiveScan(unittest.TestCase):
    def test_iter_supported_ingest_files_recurses_and_skips_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            visible = root / "Safety Data Sheets"
            hidden = root / ".hidden"
            visible.mkdir()
            hidden.mkdir()
            direct = root / "manual.pdf"
            nested = visible / "nested.docx"
            hidden_file = hidden / "secret.pdf"
            direct.write_bytes(b"%PDF")
            nested.write_bytes(b"docx-ish")
            hidden_file.write_bytes(b"%PDF")

            out = [p.relative_to(root).as_posix() for p in ingest.iter_supported_ingest_files(root)]

        self.assertEqual(out, ["Safety Data Sheets/nested.docx", "manual.pdf"])


class TestIngestSuccessRecords(unittest.TestCase):
    def test_empty_chunks_are_not_recorded_as_processed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_data_dir = ingest.DATA_DIR
            ingest.DATA_DIR = root
            try:
                path = root / "manuals" / "empty.pdf"
                path.parent.mkdir()
                path.write_bytes(b"%PDF")
                registry = {"version": 1, "files": {}}
                manifest = {"version": 1, "files": {}}
                ok = ingest.record_ingest_success_if_nonempty(
                    registry,
                    manifest,
                    path,
                    doc_type="sop",
                    doc_role="manual",
                    chunks=[],
                    global_metadata={"doc_type": "sop", "doc_role": "manual"},
                )
            finally:
                ingest.DATA_DIR = old_data_dir

        self.assertFalse(ok)
        self.assertEqual(registry["files"], {})
        self.assertEqual(manifest["files"], {})

    def test_nonempty_chunks_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_data_dir = ingest.DATA_DIR
            ingest.DATA_DIR = root
            try:
                path = root / "manuals" / "manual.pdf"
                path.parent.mkdir()
                path.write_bytes(b"%PDF")
                registry = {"version": 1, "files": {}}
                manifest = {"version": 1, "files": {}}
                ok = ingest.record_ingest_success_if_nonempty(
                    registry,
                    manifest,
                    path,
                    doc_type="sop",
                    doc_role="manual",
                    chunks=[Document(page_content="hello", metadata={"source": "manuals/manual.pdf"})],
                    global_metadata={"doc_type": "sop", "doc_role": "manual"},
                )
            finally:
                ingest.DATA_DIR = old_data_dir

        self.assertTrue(ok)
        self.assertIn("manuals/manual.pdf", registry["files"])
        self.assertIn("manuals/manual.pdf", manifest["files"])


if __name__ == "__main__":
    unittest.main()
