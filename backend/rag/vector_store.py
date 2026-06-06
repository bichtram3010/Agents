"""
ChromaDB persistent client + collection management.
DB lưu ở backend/data/chroma/.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings

COLLECTION_NAME = "shop_knowledge"
_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "chroma"


@lru_cache(maxsize=1)
def get_client() -> chromadb.api.ClientAPI:
    _DB_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(_DB_PATH),
        settings=Settings(anonymized_telemetry=False),
    )


@lru_cache(maxsize=1)
def get_collection():
    client = get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection() -> None:
    """Xóa và tạo lại collection (gọi khi re-index)."""
    client = get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    get_collection.cache_clear()
    get_collection()
