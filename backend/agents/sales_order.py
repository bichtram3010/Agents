"""
Sales/Order Agent - báo giá và tra cứu đơn hàng Odoo.

Agent này nằm trong chatbot khách hàng nên chỉ tạo BÁO GIÁ NHÁP (state=draft).
Xác nhận đơn (action_confirm) là việc của nhân viên trong Odoo, hoặc
POST /api/order/create với confirm=true kèm header X-API-Key = ADMIN_API_KEY.
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import (
    list_sale_orders, create_quotation,
    search_customers, list_products,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_sales_order_agent() -> Agent:
    return Agent(
        name="SalesOrder",
        role="Tạo báo giá nháp, tra cứu đơn hàng, tìm kiếm khách hàng",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=4096,
        ),
        tools=[list_sale_orders, create_quotation, search_customers, list_products],
        instructions=[
            "Bạn là chuyên viên bán hàng. Hỗ trợ tạo báo giá nháp và theo dõi đơn.",
            "Khi tạo báo giá: 1) tìm khách bằng search_customers, 2) tìm sản phẩm bằng list_products, 3) gọi create_quotation.",
            "Bạn KHÔNG xác nhận được đơn. Báo giá là bản nháp; nói với khách rằng nhân viên sẽ xác nhận.",
            "Hiển thị state đơn hàng: draft=Nháp, sale=Đã xác nhận, done=Hoàn thành, cancel=Hủy.",
        ],
        markdown=True,
    )
