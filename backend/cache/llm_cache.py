"""
LLM Response Cache — tránh gọi LLM lặp lại cho câu hỏi giống nhau.

Dùng MD5 hash của query (normalized) làm key.
TTL mặc định: 60 phút.
Max entries: 500.

Không cache các query liên quan đến:
  - Tạo/sửa đơn hàng (realtime)
  - Tồn kho hiện tại (thay đổi thường xuyên)
  - Thời gian hiện tại
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


# Keyword → skip cache (cần data realtime)
SKIP_KEYWORDS = [
    "tạo đơn", "đặt hàng", "chốt đơn", "tạo báo giá",
    "tồn kho hiện", "còn bao nhiêu", "hết hàng chưa",
    "hôm nay", "bây giờ", "lúc này", "hiện tại",
    "doanh thu tháng", "đơn hàng mới",
]


@dataclass
class CacheEntry:
    response: str
    agent_used: Optional[str]
    query_hash: str
    created_at: datetime = field(default_factory=datetime.now)
    hits: int = 0
    latency_ms: float = 0.0   # latency lần đầu (để tính tiết kiệm)


class LLMCache:
    def __init__(self, ttl_minutes: int = 60, max_entries: int = 500):
        self._cache: dict[str, CacheEntry] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max = max_entries
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._total_saved_ms = 0.0

    @staticmethod
    def _normalize(query: str) -> str:
        """Normalize query để tăng hit rate."""
        return " ".join(query.lower().strip().split())

    def _hash(self, query: str) -> str:
        return hashlib.md5(self._normalize(query).encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[CacheEntry]:
        k = self._hash(query)
        with self._lock:
            entry = self._cache.get(k)
            if entry:
                if datetime.now() - entry.created_at < self._ttl:
                    entry.hits += 1
                    self._hits += 1
                    self._total_saved_ms += entry.latency_ms
                    return entry
                else:
                    del self._cache[k]
        self._misses += 1
        return None

    def set(self, query: str, response: str,
            agent_used: Optional[str] = None,
            latency_ms: float = 0.0) -> None:
        k = self._hash(query)
        with self._lock:
            if len(self._cache) >= self._max:
                # Evict LRU (least recently created)
                oldest_key = min(self._cache, key=lambda x: self._cache[x].created_at)
                del self._cache[oldest_key]
            self._cache[k] = CacheEntry(
                response=response,
                agent_used=agent_used,
                query_hash=k,
                latency_ms=latency_ms,
            )

    def stats(self) -> dict:
        total = self._hits + self._misses
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{self._hits / total:.1%}" if total else "0%",
                "cached_entries": len(self._cache),
                "total_saved_ms": round(self._total_saved_ms),
                "ttl_minutes": int(self._ttl.total_seconds() / 60),
            }

    def clear(self) -> int:
        with self._lock:
            n = len(self._cache)
            self._cache.clear()
            return n


_llm_cache = LLMCache()


def get_llm_cache() -> LLMCache:
    return _llm_cache


def should_cache(query: str) -> bool:
    """Kiểm tra query có nên cache không."""
    ql = query.lower()
    return not any(kw in ql for kw in SKIP_KEYWORDS)
