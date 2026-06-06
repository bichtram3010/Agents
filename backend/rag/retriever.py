"""
Semantic search interface dùng cho agent + API endpoint.
"""
from __future__ import annotations

from typing import Literal

from .embeddings import get_embedder
from .vector_store import get_collection


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

    embed = get_embedder()
    coll = get_collection()

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
