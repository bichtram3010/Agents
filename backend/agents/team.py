"""
Team coordinator.

Có 2 chế độ:
  1. Direct call  — pre_route() khớp → gọi agent thẳng, 0 supervisor LLM
  2. Supervisor   — pre_route() = None → LLM supervisor route (fallback)

Mục tiêu: 90%+ queries đi qua direct call.
"""
from __future__ import annotations

import os
from functools import lru_cache

from agno.agent import Agent
from agno.team import Team
from agno.models.openai import OpenAILike

from .product_stock import make_product_stock_agent   # merge ProductManager+Inventory
from .sales_order import make_sales_order_agent
from .analytics import make_analytics_agent
from .consultant import make_consultant_agent
from .shipping import make_shipping_agent
from .comparison import make_comparison_agent

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


# ── Lazy-initialized agent registry ──────────────────────────────────────────

_agents: dict[str, Agent] = {}
_team: Team | None = None


def _ensure_agents() -> None:
    """Khởi tạo agents một lần, tái dùng cho mọi request."""
    global _agents
    if _agents:
        return
    _agents = {
        "product_stock": make_product_stock_agent(),
        "sales":         make_sales_order_agent(),
        "analytics":     make_analytics_agent(),
        "consultant":    make_consultant_agent(),
        "shipping":      make_shipping_agent(),
        "comparison":    make_comparison_agent(),
    }


def get_agent(name: str) -> Agent | None:
    """Lấy agent theo tên (dùng cho direct routing)."""
    _ensure_agents()
    return _agents.get(name)


def get_all_agents() -> list[Agent]:
    _ensure_agents()
    return list(_agents.values())


# ── Supervisor Team (fallback) ────────────────────────────────────────────────

def build_team() -> Team:
    _ensure_agents()
    return Team(
        name="OdooAssistant",
        # Supervisor dùng model nhẹ — chỉ cần route, không cần thông minh
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=512,  # supervisor chỉ cần quyết định, không cần dài
        ),
        members=get_all_agents(),
        instructions=[
            "Route ngắn gọn đến đúng agent:",
            "  sản phẩm/kho → ProductStock",
            "  đơn hàng/khách → Sales",
            "  doanh thu/báo cáo → Analytics",
            "  tư vấn/skincare/phối đồ → Consultant",
            "  ship/giao hàng → Shipping",
            "  so sánh shop/phá giá → Comparison",
            "Trả lời tiếng Việt.",
        ],
        markdown=True,
    )


def get_team() -> Team:
    global _team
    if _team is None:
        _team = build_team()
    return _team
