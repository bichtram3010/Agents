"""
Odoo Query Cache — giảm XML-RPC calls tốn kém.

TTL theo loại data:
  - products list    → 5 phút  (thay đổi ít)
  - categories       → 30 phút (rất ít thay đổi)
  - stock overview   → 2 phút  (thay đổi thường xuyên hơn)
  - sale orders      → 1 phút

Write operations (create/update) → tự động invalidate cache liên quan.
"""
from __future__ import annotations

import functools
import hashlib
import json
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Optional


class OdooCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, datetime, int]] = {}  # key → (value, created_at, ttl_sec)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None
            value, created_at, ttl_sec = self._store[key]
            if (datetime.now() - created_at).total_seconds() > ttl_sec:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl_sec: int = 300) -> None:
        with self._lock:
            self._store[key] = (value, datetime.now(), ttl_sec)

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def clear(self) -> int:
        with self._lock:
            n = len(self._store)
            self._store.clear()
            return n

    def stats(self) -> dict:
        total = self._hits + self._misses
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{self._hits / total:.1%}" if total else "0%",
                "cached_keys": len(self._store),
            }


_odoo_cache = OdooCache()


def get_odoo_cache() -> OdooCache:
    return _odoo_cache


def _make_key(fn_name: str, args, kwargs) -> str:
    raw = json.dumps({"fn": fn_name, "args": args, "kwargs": kwargs},
                     sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


# TTL map theo tên function
_TTL_MAP: dict[str, int] = {
    "list_products": 300,        # 5 phút
    "list_categories": 1800,     # 30 phút
    "get_product": 300,          # 5 phút
    "stock_overview": 120,       # 2 phút
    "low_stock_products": 120,   # 2 phút
    "top_products_by_price": 300,
    "sales_summary_by_category": 120,
    "revenue_summary": 60,       # 1 phút
    "list_sale_orders": 60,
    "search_customers": 300,
}

# Khi gọi các function này → invalidate cache liên quan
_INVALIDATE_ON: dict[str, list[str]] = {
    "create_product":         ["list_products", "list_categories"],
    "update_product_price":   ["list_products", "get_product", "top_products_by_price"],
    "adjust_stock":           ["stock_overview", "low_stock_products"],
    "create_quotation":       ["list_sale_orders", "revenue_summary"],
    "confirm_sale_order":     ["list_sale_orders", "revenue_summary", "sales_summary_by_category"],
    "create_or_get_customer": ["search_customers"],
}


def odoo_cached(fn: Callable) -> Callable:
    """
    Decorator cache kết quả Odoo function.

    Dùng:
        @odoo_cached
        def list_products(category=None, search=None, limit=30) -> list[dict]: ...
    """
    fn_name = fn.__name__
    ttl = _TTL_MAP.get(fn_name, 300)
    invalidates = _INVALIDATE_ON.get(fn_name, [])

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cache = get_odoo_cache()

        # Write operations: gọi thật rồi invalidate
        if invalidates:
            result = fn(*args, **kwargs)
            for prefix in invalidates:
                n = cache.invalidate_prefix(prefix)
                if n:
                    print(f"[odoo_cache] invalidated {n} entries for '{prefix}'")
            return result

        # Read operations: kiểm tra cache
        key = f"{fn_name}:{_make_key(fn_name, args, kwargs)}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        result = fn(*args, **kwargs)
        cache.set(key, result, ttl_sec=ttl)
        return result

    return wrapper
