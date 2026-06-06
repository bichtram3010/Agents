"""
Shipping Agent - tính phí vận chuyển và tư vấn options giao hàng.
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import calculate_shipping_fee

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_shipping_agent() -> Agent:
    return Agent(
        name="Shipping",
        role="Tính phí vận chuyển, tư vấn phương thức giao hàng, ETA",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=2048,
        ),
        tools=[calculate_shipping_fee],
        instructions=[
            "Bạn là chuyên viên vận chuyển cho shop thời trang + mỹ phẩm.",
            "",
            "═══ QUY TẮC ═══",
            "1. Luôn gọi calculate_shipping_fee khi user hỏi về phí ship / thời gian giao.",
            "2. Hỏi user các thông tin còn thiếu (địa chỉ, tổng đơn, có cần hỏa tốc?) trước khi tính.",
            "3. Sau khi tính xong, trình bày kết quả có cấu trúc:",
            "   • Zone vận chuyển: nội thành HCM / liên tỉnh / ...",
            "   • Phí ship: X ₫",
            "   • Thời gian dự kiến: 1-2 ngày",
            "   • Có được miễn ship không (đơn >= 500k miễn ship)",
            "   • Breakdown chi tiết",
            "4. Gợi ý cho user:",
            "   - Nếu đơn < 500k và gần ngưỡng (vd 480k) → suggest mua thêm để được miễn ship",
            "   - Nếu user cần gấp nội thành HCM/HN → giới thiệu hỏa tốc 60k/4h",
            "5. Trả lời tiếng Việt, format VND có dấu phẩy/chấm: 25.000 ₫",
            "",
            "═══ BẢNG GIÁ (để bạn ghi nhớ) ═══",
            "• Nội thành HCM/HN: 25.000 ₫ (1-2 ngày)",
            "• Hỏa tốc HCM/HN: 60.000 ₫ (4 giờ)",
            "• Liên tỉnh miền Trung: 30.000 ₫ (2-3 ngày)",
            "• Liên tỉnh miền Bắc: 40.000 ₫ (3-5 ngày)",
            "• Miền Nam xa: 35.000 ₫ (2-4 ngày)",
            "• Cân nặng > 2kg: phụ phí 10.000 ₫/kg vượt",
            "• Miễn ship cho đơn từ 500.000 ₫ (trừ hỏa tốc)",
        ],
        markdown=True,
    )
