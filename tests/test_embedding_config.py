# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

import ingest


class FakeHFEmbeddings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class TestEmbeddingConfig(unittest.TestCase):
    def test_local_hash_provider_has_embedding_methods(self) -> None:
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "local_hash", "LOCAL_HASH_EMBEDDING_DIM": "32"}, clear=False):
            emb = ingest.build_embeddings()
        self.assertEqual(len(emb.embed_query("microgel safety")), 32)
        self.assertEqual(len(emb.embed_documents(["a", "b"])), 2)

    def test_bge_m3_uses_huggingface_model_alias(self) -> None:
        with patch.object(ingest, "HuggingFaceEmbeddings", FakeHFEmbeddings), patch.dict(
            os.environ,
            {"EMBEDDING_PROVIDER": "bge_m3", "HF_EMBEDDING_MODEL": "BAAI/bge-m3", "EMBEDDING_NORMALIZE": "true"},
            clear=False,
        ):
            emb = ingest.build_embeddings()
        self.assertEqual(emb.kwargs["model_name"], "BAAI/bge-m3")
        self.assertTrue(emb.kwargs["encode_kwargs"]["normalize_embeddings"])

    def test_e5_uses_e5_model(self) -> None:
        with patch.object(ingest, "HuggingFaceEmbeddings", FakeHFEmbeddings), patch.dict(
            os.environ,
            {"EMBEDDING_PROVIDER": "e5", "E5_EMBEDDING_MODEL": "intfloat/multilingual-e5-base"},
            clear=False,
        ):
            emb = ingest.build_embeddings()
        self.assertEqual(emb.kwargs["model_name"], "intfloat/multilingual-e5-base")


if __name__ == "__main__":
    unittest.main()
