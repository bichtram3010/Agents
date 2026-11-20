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
        # Không chép bảng giá vào prompt: từng có "miền Bắc: 40.000 ₫" ở đây và model
        # trả lời Hà Nội 40.000 ₫ theo trí nhớ thay vì gọi tool (đúng là 25.000 ₫ nội thành).
        instructions=[
            "Bạn là chuyên viên vận chuyển cho shop thời trang + mỹ phẩm.",
            "",
            "═══ QUY TẮC ═══",
            "1. Mọi câu hỏi về phí ship / thời gian giao: GỌI calculate_shipping_fee NGAY với địa chỉ "
            "đúng như khách viết (vd 'Hà Nội', 'Quận 1 HCM'). Không hỏi thêm quận/huyện hay cân nặng.",
            "2. Khách không nói tổng đơn → gọi với order_total=0 rồi nêu ngưỡng miễn ship tool trả về.",
            "3. CHỈ dùng con số tool trả về (fee, zone, eta, free_ship_applied). "
            "Không tự đoán zone, không tự tính, không dùng giá nhớ được ở đâu khác.",
            "4. Trình bày ngắn: zone, phí ship, thời gian dự kiến, có được miễn ship không.",
            "5. Gợi ý: đơn gần ngưỡng miễn ship → gợi ý mua thêm; cần gấp → gọi lại tool với express=True.",
            "6. Trả lời tiếng Việt, số tiền dạng 1.234 ₫.",
        ],
        markdown=True,
    )
