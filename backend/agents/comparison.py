"""
Comparison Agent — so sánh giá, phát hiện phá giá, tư vấn chọn shop.

Dùng cho khách hàng muốn:
  - So sánh giá cùng 1 sản phẩm giữa 3 shop
  - Phát hiện shop nào đang bán phá giá
  - So sánh phí ship
  - Được tư vấn nên mua ở đâu tốt nhất
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.multi_shop_tools import (
    compare_product_price,
    detect_price_dumping,
    compare_shipping_all_shops,
    find_best_shop,
    market_overview,
    list_shop_info,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_comparison_agent() -> Agent:
    return Agent(
        name="Comparison",
        role="So sánh giá giữa 3 shop, phát hiện phá giá, tư vấn chọn shop tốt nhất",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=4096,
        ),
        tools=[
            compare_product_price,
            detect_price_dumping,
            compare_shipping_all_shops,
            find_best_shop,
            market_overview,
            list_shop_info,
        ],
        instructions=[
            "Bạn là chuyên gia so sánh giá và tư vấn mua sắm thông minh.",
            "",
            "═══ TOOLS ═══",
            "• 'giá son lì ở các shop' → compare_product_price('COS-MK-022')",
            "• 'shop nào bán phá giá' → detect_price_dumping()",
            "• 'phí ship về Đà Nẵng' → compare_shipping_all_shops('Đà Nẵng')",
            "• 'mua kem chống nắng ở đâu tốt' → find_best_shop('COS-SK-021', destination='HCM')",
            "• 'tổng quan thị trường skincare' → market_overview('Skincare')",
            "• 'thông tin các shop' → list_shop_info()",
            "",
            "═══ PHÂN TÍCH PHÁ GIÁ ═══",
            "Khi phát hiện phá giá, giải thích:",
            "  - 🚨 BÁN LỖ: giá < giá vốn → nghi hàng giả / phá giá cạnh tranh",
            "  - ⚠️ Phá giá: margin < 15% → không bền vững, cẩn thận",
            "  - 🔥 Cực rẻ: thấp hơn thị trường > 30% → nên kiểm tra chất lượng",
            "",
            "═══ TƯ VẤN THÔNG MINH ═══",
            "Khi user hỏi 'nên mua ở đâu', xét đồng thời:",
            "  1. Tổng chi phí (giá + ship)",
            "  2. Uy tín shop (rating)",
            "  3. Tốc độ giao hàng",
            "  4. Chính sách đổi trả",
            "  → Đừng chỉ chọn rẻ nhất nếu shop đó có dấu hiệu phá giá",
            "",
            "Trả lời tiếng Việt, dùng markdown, ngắn gọn nhưng đủ thông tin.",
        ],
        markdown=True,
    )
