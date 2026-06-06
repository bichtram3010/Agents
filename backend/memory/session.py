"""
Session Memory — nhớ trạng thái hội thoại giữa các request.

Lưu trữ:
  - Lịch sử tin nhắn (10 turns gần nhất)
  - User profile tự động trích xuất (loại da, ngân sách, scenario)
  - Sản phẩm đã đề cập (SKU)
  - Agent cuối dùng

TTL mặc định: 30 phút không hoạt động → xóa session.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


# ── User Profile ──────────────────────────────────────────────────────────────

SKIN_PATTERNS: dict[str, list[str]] = {
    "dầu":       ["da dầu", "bóng nhờn", "lỗ chân lông to", "nhờn", "tiết nhiều dầu"],
    "khô":       ["da khô", "căng rát", "bong tróc", "thiếu ẩm", "khô ráp"],
    "hỗn hợp":  ["da hỗn hợp", "vùng t", "chữ t"],
    "nhạy cảm": ["da nhạy cảm", "dị ứng", "kích ứng", "đỏ rát"],
    "mụn":       ["da mụn", "mụn ẩn", "mụn đầu đen", "mụn bọc", "sần sùi"],
}

SCENARIO_PATTERNS: dict[str, list[str]] = {
    "đi quân sự": ["quân sự", "tập quân sự", "học quân sự"],
    "đi học":     ["sinh viên", "đi học", "học sinh", "đại học"],
    "đi làm":     ["công sở", "văn phòng", "đi làm", "công việc"],
    "đi tiệc":    ["đi tiệc", "hẹn hò", "dự tiệc", "party"],
    "đi biển":    ["đi biển", "du lịch hè", "bãi biển", "ngoài trời"],
    "sau sinh":   ["sau sinh", "mới sinh", "đang cho con bú"],
}

SKU_PATTERN = re.compile(r'\b(FSH|COS)-[A-Z]{2}-\d{3}\b')


@dataclass
class UserProfile:
    skin_type: Optional[str] = None     # "dầu" | "khô" | "hỗn hợp" | "nhạy cảm" | "mụn"
    budget: Optional[int] = None        # VND
    scenario: Optional[str] = None      # "đi quân sự" | "đi làm" ...
    mentioned_skus: list[str] = field(default_factory=list)

    def update_from_text(self, text: str) -> None:
        """Trích xuất profile từ tin nhắn user."""
        tl = text.lower()

        # Skin type
        for skin, patterns in SKIN_PATTERNS.items():
            if any(p in tl for p in patterns):
                self.skin_type = skin
                break

        # Scenario
        for scenario, patterns in SCENARIO_PATTERNS.items():
            if any(p in tl for p in patterns):
                self.scenario = scenario
                break

        # Budget: "500k", "1tr", "2 triệu", "300 nghìn"
        for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(k|nghìn|tr|triệu)', tl):
            num = float(m.group(1).replace(',', '.'))
            unit = m.group(2)
            if unit in ('tr', 'triệu'):
                self.budget = int(num * 1_000_000)
            else:
                self.budget = int(num * 1_000)
            break  # lấy số đầu tiên

        # SKUs
        skus = SKU_PATTERN.findall(text.upper())
        for sku in skus:
            if sku not in self.mentioned_skus:
                self.mentioned_skus.append(sku)
        # Giữ max 10 SKU gần nhất
        self.mentioned_skus = self.mentioned_skus[-10:]

    def summary(self) -> str:
        parts = []
        if self.skin_type:
            parts.append(f"loại da: {self.skin_type}")
        if self.budget:
            parts.append(f"ngân sách: {self.budget:,} ₫")
        if self.scenario:
            parts.append(f"scenario: {self.scenario}")
        if self.mentioned_skus:
            parts.append(f"SP quan tâm: {', '.join(self.mentioned_skus[-5:])}")
        return " | ".join(parts) if parts else ""


# ── Session State ─────────────────────────────────────────────────────────────

@dataclass
class SessionState:
    session_id: str
    history: list[dict] = field(default_factory=list)   # [{role, content}]
    profile: UserProfile = field(default_factory=UserProfile)
    last_agent: Optional[str] = None
    turn_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_user(self, content: str) -> None:
        self.profile.update_from_text(content)
        self.history.append({"role": "user", "content": content})
        self._trim()
        self.turn_count += 1
        self.updated_at = datetime.now()

    def add_assistant(self, content: str, agent: Optional[str] = None) -> None:
        self.history.append({"role": "assistant", "content": content})
        if agent:
            self.last_agent = agent
        self._trim()
        self.updated_at = datetime.now()

    def _trim(self) -> None:
        """Giữ tối đa 10 turns (5 user + 5 assistant)."""
        if len(self.history) > 10:
            self.history = self.history[-10:]

    def build_prompt(self, current_query: str) -> str:
        """
        Ghép context đầy đủ để gửi vào agent:
          [User Profile] → [Lịch sử] → [Câu hỏi hiện tại]
        """
        parts: list[str] = []

        # Profile summary
        profile_str = self.profile.summary()
        if profile_str:
            parts.append(f"[Thông tin user: {profile_str}]")

        # Agent gần nhất (giúp supervisor route tốt hơn)
        if self.last_agent:
            parts.append(f"[Agent vừa dùng: {self.last_agent}]")

        # Lịch sử (bỏ câu cuối vì đó là current_query sắp thêm)
        prev = [m for m in self.history if m["content"] != current_query][-8:]
        if prev:
            hist_lines = "\n".join(f"{m['role'].upper()}: {m['content'][:300]}" for m in prev)
            parts.append(f"[Lịch sử hội thoại]\n{hist_lines}")

        parts.append(f"USER: {current_query}")
        return "\n\n".join(parts)


# ── Session Store ─────────────────────────────────────────────────────────────

class SessionStore:
    def __init__(self, ttl_minutes: int = 30, max_sessions: int = 500):
        self._store: dict[str, SessionState] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max = max_sessions
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionState:
        with self._lock:
            self._cleanup()
            if session_id not in self._store:
                if len(self._store) >= self._max:
                    # Evict session cũ nhất
                    oldest = min(self._store.items(), key=lambda x: x[1].updated_at)
                    del self._store[oldest[0]]
                self._store[session_id] = SessionState(session_id=session_id)
            return self._store[session_id]

    def _cleanup(self) -> None:
        now = datetime.now()
        expired = [sid for sid, s in self._store.items() if now - s.updated_at > self._ttl]
        for sid in expired:
            del self._store[sid]

    def stats(self) -> dict:
        with self._lock:
            return {
                "active_sessions": len(self._store),
                "total_turns": sum(s.turn_count for s in self._store.values()),
                "avg_turns": round(
                    sum(s.turn_count for s in self._store.values()) / max(len(self._store), 1), 1
                ),
            }


_store = SessionStore()


def get_session(session_id: str) -> SessionState:
    return _store.get_or_create(session_id)


def session_stats() -> dict:
    return _store.stats()
