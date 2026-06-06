"""
Ingest knowledge base + products vào ChromaDB.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .embeddings import get_embedder
from .vector_store import get_collection, reset_collection

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_KB_DIR = _DATA_DIR / "knowledge"
_PRODUCTS_JSON = _DATA_DIR / "products.json"


# ============================================================
# Chunking
# ============================================================
def _chunk_markdown(text: str, max_chars: int = 800) -> list[dict]:
    """Tách markdown theo heading + paragraph, giới hạn max_chars mỗi chunk."""
    chunks: list[dict] = []
    current_section = ""
    buffer = ""

    for line in text.split("\n"):
        if re.match(r"^#{1,3}\s", line):
            # flush
            if buffer.strip():
                chunks.append({"section": current_section, "text": buffer.strip()})
                buffer = ""
            current_section = line.lstrip("#").strip()
            continue
        buffer += line + "\n"
        if len(buffer) >= max_chars:
            chunks.append({"section": current_section, "text": buffer.strip()})
            buffer = ""

    if buffer.strip():
        chunks.append({"section": current_section, "text": buffer.strip()})

    return [c for c in chunks if len(c["text"]) > 30]


def _product_to_doc(p: dict) -> str:
    """Render 1 sản phẩm thành đoạn văn để index."""
    return (
        f"Sản phẩm: {p['name']}\n"
        f"SKU: {p['sku']}\n"
        f"Loại: {p['type']} ({p['category']})\n"
        f"Giá: {p['list_price']:,} VND\n"
        f"Mô tả: {p['description']}"
    )


# ============================================================
# Build index
# ============================================================
def build_index(reset: bool = True) -> dict:
    """
    Đọc all knowledge files + products.json, chunk, embed, store.
    Trả về stats {documents, chunks}.
    """
    if reset:
        reset_collection()

    embed = get_embedder()
    coll = get_collection()

    docs: list[str] = []
    metas: list[dict] = []
    ids: list[str] = []

    # 1) Knowledge markdown files
    for md_file in sorted(_KB_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for i, chunk in enumerate(_chunk_markdown(text)):
            docs.append(chunk["text"])
            metas.append({
                "source": md_file.name,
                "type": "knowledge",
                "section": chunk["section"],
            })
            ids.append(f"{md_file.stem}-{i}")

    # 2) Products JSON
    if _PRODUCTS_JSON.exists():
        products = json.loads(_PRODUCTS_JSON.read_text(encoding="utf-8"))["products"]
        for p in products:
            docs.append(_product_to_doc(p))
            metas.append({
                "source": "products.json",
                "type": "product",
                "sku": p["sku"],
                "category": p["type"],
                "list_price": p["list_price"],
            })
            ids.append(f"product-{p['sku']}")

    print(f"[ingest] embedding {len(docs)} chunks...")
    vectors = embed(docs)

    print(f"[ingest] adding to ChromaDB...")
    coll.upsert(
        ids=ids,
        documents=docs,
        embeddings=vectors,
        metadatas=metas,
    )

    stats = {
        "total_chunks": len(docs),
        "knowledge_chunks": sum(1 for m in metas if m["type"] == "knowledge"),
        "product_chunks": sum(1 for m in metas if m["type"] == "product"),
        "kb_files": sorted(set(m["source"] for m in metas if m["type"] == "knowledge")),
    }
    print(f"[ingest] done: {stats}")
    return stats


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.chdir(Path(__file__).resolve().parents[2])
    build_index(reset=True)
