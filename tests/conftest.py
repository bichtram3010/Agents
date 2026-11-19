"""Shared test setup.

Tests never call Odoo or an LLM: agents, the team and Odoo tools are replaced per test.
sentence-transformers is never loaded (tests/test_rag.py uses a small fake embedder).
When chromadb is not installed, a stand-in module lets the backend import;
the RAG tests then skip.
"""
from __future__ import annotations

import sys
import types


def _install_fake_chromadb() -> None:
    try:
        import chromadb  # noqa: F401
        return
    except ImportError:
        pass
    chromadb = types.ModuleType("chromadb")
    chromadb.__fake__ = True
    config = types.ModuleType("chromadb.config")

    class Settings:  # noqa: D401 - minimal stand-in
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class PersistentClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("chromadb is not available in tests")

    config.Settings = Settings
    chromadb.config = config
    chromadb.PersistentClient = PersistentClient
    chromadb.api = types.SimpleNamespace(ClientAPI=object)
    sys.modules["chromadb"] = chromadb
    sys.modules["chromadb.config"] = config


_install_fake_chromadb()
