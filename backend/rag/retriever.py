"""
Semantic search interface dùng cho agent + API endpoint.
"""
from __future__ import annotations

import threading
from typing import Literal

from . import ingest
from .embeddings import get_embedder
from .vector_store import get_collection

_index_lock = threading.Lock()


def ensure_index():
    """Trả về collection, tự build index nếu đang trống.

    Repo không commit index (ChromaDB cần cả chroma.sqlite3), nên clone mới luôn
    trống. Thay vì để Consultant nhận "không tìm thấy" mãi, lần search đầu tiên
    build từ backend/data/knowledge/*.md + products.json (lần đầu tải model
    embedding ~120MB). Lock để nhiều request cùng lúc chỉ build một lần.
    """
    coll = get_collection()
    if coll.count() > 0:
        return coll
    with _index_lock:
        coll = get_collection()
        if coll.count() == 0:
            print("[rag] index trống → build lần đầu từ backend/data ...")
            ingest.build_index(reset=False)
            coll = get_collection()
    return coll


def semantic_search(
    query: str,
    top_k: int = 5,
    filter_type: Literal["all", "knowledge", "product"] = "all",
) -> list[dict]:
    """
    Tìm top-k chunk gần nghĩa nhất.

    Returns: list of {text, source, section, distance, sku?, list_price?}
    """
    if not query.strip():
        return []

    coll = ensure_index()
    embed = get_embedder()

    where = None if filter_type == "all" else {"type": filter_type}
    qvec = embed([query])[0]

    res = coll.query(
        query_embeddings=[qvec],
        n_results=top_k,
        where=where,
    )

    results: list[dict] = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    distances = res.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, distances):
        item = {
            "text": doc,
            "distance": round(float(dist), 4),
            **(meta or {}),
        }
        results.append(item)
    return results


def format_results(results: list[dict]) -> str:
    """Format kết quả cho LLM consume - markdown."""
    if not results:
        return "Không tìm thấy thông tin liên quan trong knowledge base."
    out = []
    for i, r in enumerate(results, 1):
        src = r.get("source", "?")
        sec = r.get("section", "")
        suffix = f" — {sec}" if sec else ""
        out.append(f"### [{i}] {src}{suffix} (sim={1 - r['distance']:.2f})\n{r['text']}\n")
    return "\n".join(out)
