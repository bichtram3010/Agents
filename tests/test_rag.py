"""RAG: a fresh clone has no index, so the first search must build it from
backend/data/knowledge/*.md + products.json instead of silently returning nothing."""
from __future__ import annotations

import hashlib
import math

import chromadb
import pytest

if getattr(chromadb, "__fake__", False):
    pytest.skip("chromadb is not installed", allow_module_level=True)

from backend.rag import ingest, retriever, vector_store  # noqa: E402

DIM = 64


def fake_embedder():
    """Bag of hashed words: texts sharing words get close vectors (no model download)."""
    def embed(texts):
        out = []
        for text in texts:
            vec = [0.0] * DIM
            for word in text.lower().split():
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out
    return embed


@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store, "_DB_PATH", tmp_path / "chroma")
    monkeypatch.setattr(ingest, "get_embedder", fake_embedder)
    monkeypatch.setattr(retriever, "get_embedder", fake_embedder)
    vector_store.get_client.cache_clear()
    vector_store.get_collection.cache_clear()
    builds = []
    real_build = ingest.build_index

    def counting_build(*args, **kwargs):
        builds.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(ingest, "build_index", counting_build)
    yield builds
    vector_store.get_client.cache_clear()
    vector_store.get_collection.cache_clear()


def test_first_search_builds_missing_index(empty_store):
    assert vector_store.get_collection().count() == 0

    results = retriever.semantic_search("da dầu mụn ẩn", top_k=3)

    assert len(empty_store) == 1
    assert vector_store.get_collection().count() > 0
    assert len(results) == 3


def test_index_is_built_only_once(empty_store):
    retriever.semantic_search("da dầu", top_k=2)
    retriever.semantic_search("phối đồ công sở", top_k=2)
    assert len(empty_store) == 1


def test_product_filter_returns_products(empty_store):
    results = retriever.semantic_search("kem chống nắng", top_k=3, filter_type="product")
    assert results and all(r["type"] == "product" for r in results)
