"""
RAG module - ChromaDB + sentence-transformers cho tư vấn sản phẩm.
"""
from .embeddings import get_embedder
from .vector_store import get_collection, COLLECTION_NAME
from .retriever import semantic_search, format_results
