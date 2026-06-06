"""
Wrapper sentence-transformers với multilingual model hỗ trợ tiếng Việt.
Model paraphrase-multilingual-MiniLM-L12-v2 - 384 dim, ~120MB, đa ngôn ngữ.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

# Lazy import để startup nhanh khi không dùng RAG
_model = None
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIM = 384


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


@lru_cache(maxsize=1)
def get_embedder():
    """Return a callable taking list[str] -> list[list[float]]."""
    model = _load_model()

    def embed(texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()

    return embed
