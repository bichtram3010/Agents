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
# Thứ tự QUAN TRỌNG: khớp đầu tiên thắng, nên ý định rõ đặt trước, từ chung đặt sau.
# Keyword khớp theo NGUYÊN TỪ (\b): "áo" không khớp trong "báo", "top" không khớp
# trong "croptop". Kiểm bằng tests/test_router.py (các câu test trong README).

ROUTES: list[tuple[str, list[str]]] = [

    # ── Comparison (rất specific) ─────────────────────────────────────────────
    ("comparison", [
        "so sánh", "shop nào", "mua ở đâu", "ở đâu", "chỗ nào rẻ", "bên nào rẻ",
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

    # ── Analytics (trước Sales: "thống kê đơn hàng" là báo cáo) ──────────────
    ("analytics", [
        "doanh thu", "báo cáo", "thống kê", "phân tích", "revenue",
        "bán chạy", "top", "top sản phẩm", "category nào bán được", "doanh số",
    ]),

    # ── Sales / Orders ────────────────────────────────────────────────────────
    ("sales", [
        "tạo đơn", "đặt hàng", "báo giá", "chốt đơn", "đặt mua",
        "đơn hàng", "xem đơn", "trạng thái đơn", "xác nhận đơn",
        "khách hàng", "tìm khách", "thông tin khách",
        "sale order", "quotation",
    ]),

    # ── ProductStock: ý định xem danh sách / kho rõ ràng (trước Consultant) ──
    ("product_stock", [
        "liệt kê", "danh sách sản phẩm", "danh sách", "list giá",
        "sku", "mã sản phẩm", "barcode",
        "tồn kho", "còn hàng", "hết hàng", "còn bao nhiêu",
        "sắp hết", "cảnh báo kho", "stock", "kho hàng",
        "tổng quan kho", "giá trị kho",
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
        # Context/scenario (bỏ "dưới", "khoảng": quá chung, cướp câu liệt kê)
        "đi quân sự", "sinh viên", "công sở", "đi tiệc", "hẹn hò",
        "ngân sách", "budget", "tầm giá",
        "recommend", "gợi ý", "đề xuất", "chọn giúp",
    ]),

    # ── ProductStock: từ chung về sản phẩm / giá (cuối cùng) ─────────────────
    ("product_stock", [
        "có sản phẩm nào", "sản phẩm nào", "tìm sản phẩm", "xem sản phẩm",
        "giá", "bao nhiêu tiền", "giá bán",
        "thời trang", "mỹ phẩm", "makeup", "fashion",
        "áo", "quần", "váy", "túi", "son", "kem", "nước hoa",
    ]),
]

# Mục cuối là từ chung ("giá", "son"...): thua câu nối tiếp của lượt trước.
INTENT_ROUTES = ROUTES[:-1]
GENERIC_ROUTE = ROUTES[-1]

# Dấu hiệu câu nối tiếp: câu nhắc tới thứ vừa nói ở lượt trước.
FOLLOW_UP_MARKERS = [
    "cái đó", "cái này", "cái kia", "cái nào", "nó",
    "sản phẩm đó", "sản phẩm này", "món đó", "món này", "loại đó", "loại này",
    "loại nào", "mẫu đó", "mẫu này", "còn", "thế còn", "vậy còn", "thì sao",
    "vừa rồi", "lúc nãy", "ở trên",
]


def _compile(keywords: list[str]) -> re.Pattern:
    words = sorted(keywords, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in words) + r")\b", re.IGNORECASE)


_COMPILED: list[tuple[str, re.Pattern]] = [(agent, _compile(kws)) for agent, kws in INTENT_ROUTES]
_GENERIC: tuple[str, re.Pattern] = (GENERIC_ROUTE[0], _compile(GENERIC_ROUTE[1]))
_FOLLOW_UP = _compile(FOLLOW_UP_MARKERS)


def pre_route(query: str, last_agent: Optional[str] = None) -> Optional[str]:
    """
    Trả về tên agent nếu chắc, None để LLM supervisor quyết định.

    Thứ tự:
      1. Keyword ý định rõ (ROUTES trừ mục cuối), khớp đầu tiên thắng.
      2. Câu nối tiếp ("cái đó", "còn...", "thì sao") và có agent lượt trước
         → giữ agent đó (giống classifier của agent-squad giữ agent cho follow-up).
      3. Từ chung về sản phẩm / giá → ProductStock.
      4. Không khớp gì → None.
    """
    for agent, pattern in _COMPILED:
        if pattern.search(query):
            return agent
    if last_agent and _FOLLOW_UP.search(query):
        return last_agent
    agent, pattern = _GENERIC
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
