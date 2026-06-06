"""
Keyword Pre-Router — route trực tiếp, KHÔNG qua LLM supervisor.

Mục tiêu: xử lý 90%+ queries bằng keyword matching.
Chỉ fallback về LLM khi thật sự không rõ intent.

Kết quả trả về:
  - Tên agent (str)  → gọi agent đó trực tiếp
  - None             → fallback về LLM supervisor
"""
from __future__ import annotations

import re
from typing import Optional


# ── Route definitions ─────────────────────────────────────────────────────────
# Thứ tự QUAN TRỌNG: specific trước, generic sau

ROUTES: list[tuple[str, list[str]]] = [

    # ── Comparison (đặt trên cùng — rất specific) ─────────────────────────────
    ("comparison", [
        "so sánh", "shop nào", "mua ở đâu", "chỗ nào rẻ", "bên nào rẻ",
        "phá giá", "bán phá giá", "giá các shop", "giữa các shop",
        "beauty corner", "cosmo hub", "3 shop", "nhiều shop",
        "ship rẻ nhất", "so sánh phí ship", "shop nào oke", "shop nào tốt hơn",
    ]),

    # ── Shipping ──────────────────────────────────────────────────────────────
    ("shipping", [
        "phí ship", "phí vận chuyển", "ship về", "giao hàng đến",
        "hỏa tốc", "miễn ship", "free ship", "thời gian giao",
        "bao lâu tới", "mấy ngày tới", "eta", "vận chuyển",
        "ship ra hà nội", "ship ra bắc", "ship vào nam",
    ]),

    # ── Consultant (RAG) ──────────────────────────────────────────────────────
    ("consultant", [
        # Loại da
        "da dầu", "da khô", "da mụn", "da nhạy cảm", "da hỗn hợp",
        "bóng nhờn", "căng rát", "bong tróc", "mụn ẩn", "lỗ chân lông",
        # Tư vấn skincare
        "tư vấn", "nên dùng gì", "phù hợp với", "routine", "quy trình",
        "skincare", "dưỡng da", "chăm da", "serum", "toner", "kem dưỡng",
        "chống nắng", "spf", "retinol", "vitamin c", "niacinamide",
        # Fashion
        "phối đồ", "outfit", "mặc gì", "mix đồ", "ootd", "diện gì",
        "đi làm mặc", "đi tiệc mặc", "đi biển mặc", "tone màu",
        # Context/scenario
        "đi quân sự", "sinh viên", "công sở", "đi tiệc", "hẹn hò",
        "ngân sách", "budget", "tầm giá", "dưới", "khoảng",
        "recommend", "gợi ý", "đề xuất", "chọn giúp",
    ]),

    # ── Sales / Orders ────────────────────────────────────────────────────────
    ("sales", [
        "tạo đơn", "đặt hàng", "báo giá", "chốt đơn", "đặt mua",
        "đơn hàng", "xem đơn", "trạng thái đơn", "xác nhận đơn",
        "khách hàng", "tìm khách", "thông tin khách",
        "sale order", "quotation",
    ]),

    # ── Analytics ─────────────────────────────────────────────────────────────
    ("analytics", [
        "doanh thu", "báo cáo", "thống kê", "phân tích", "revenue",
        "bán chạy", "top sản phẩm", "category nào bán được",
        "tháng này", "tuần này", "doanh số",
    ]),

    # ── ProductStock (sản phẩm + kho) ─────────────────────────────────────────
    ("product_stock", [
        # Sản phẩm
        "liệt kê", "danh sách sản phẩm", "có sản phẩm nào",
        "sản phẩm nào", "tìm sản phẩm", "xem sản phẩm",
        "giá", "bao nhiêu tiền", "giá bán", "list giá",
        "sku", "mã sản phẩm", "barcode",
        "thời trang", "mỹ phẩm", "skincare", "makeup", "fashion",
        "áo", "quần", "váy", "túi", "son", "kem", "serum", "nước hoa",
        # Kho
        "tồn kho", "còn hàng", "hết hàng", "còn bao nhiêu",
        "sắp hết", "cảnh báo kho", "stock", "kho hàng",
        "tổng quan kho", "giá trị kho",
    ]),
]

_COMPILED: list[tuple[str, re.Pattern]] = [
    (agent, re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE))
    for agent, kws in ROUTES
]


def pre_route(query: str) -> Optional[str]:
    """
    Trả về tên agent nếu khớp keyword, None nếu không chắc.

    Ưu tiên: đầu tiên khớp = winner (thứ tự ROUTES quan trọng).
    None → LLM supervisor quyết định.
    """
    for agent, pattern in _COMPILED:
        if pattern.search(query):
            return agent
    return None


def route_confidence(query: str) -> tuple[Optional[str], float]:
    """
    Trả về (agent, confidence) — dùng cho logging/debugging.
    confidence = số keywords khớp / tổng keyword của agent.
    """
    best_agent = None
    best_score = 0.0

    for agent, kws in ROUTES:
        hits = sum(1 for kw in kws if kw.lower() in query.lower())
        if hits > 0:
            score = hits / len(kws)
            if score > best_score:
                best_score = score
                best_agent = agent

    return best_agent, best_score
