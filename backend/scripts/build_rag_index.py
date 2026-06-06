"""
Script CLI build (re-index) RAG knowledge base vào ChromaDB.
Chạy từ thư mục gốc dự án:
    python -m backend.scripts.build_rag_index
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from backend.rag.ingest import build_index  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("Building RAG index (ChromaDB + sentence-transformers)")
    print("=" * 60)
    stats = build_index(reset=True)
    print()
    print(f"✓ Total chunks      : {stats['total_chunks']}")
    print(f"✓ Knowledge chunks  : {stats['knowledge_chunks']}")
    print(f"✓ Product chunks    : {stats['product_chunks']}")
    print(f"✓ Source files      : {', '.join(stats['kb_files'])}")
    print()
    print("Index lưu tại: backend/data/chroma/")
    print("Bây giờ restart uvicorn để agent Consultant dùng được.")


if __name__ == "__main__":
    main()
