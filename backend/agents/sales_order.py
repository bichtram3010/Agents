"""
Sales/Order Agent - xử lý báo giá và đơn hàng Odoo.
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import (
    list_sale_orders, create_quotation, confirm_sale_order,
    search_customers, list_products,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_sales_order_agent() -> Agent:
    return Agent(
        name="SalesOrder",
        role="Tạo báo giá, xác nhận đơn hàng, tìm kiếm khách hàng",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=4096,
        ),
        tools=[list_sale_orders, create_quotation, confirm_sale_order, search_customers, list_products],
        instructions=[
            "Bạn là chuyên viên bán hàng. Hỗ trợ tạo báo giá, xác nhận đơn, theo dõi pipeline.",
            "Khi tạo báo giá: 1) tìm khách bằng search_customers, 2) tìm sản phẩm bằng list_products, 3) gọi create_quotation.",
            "Luôn confirm với user trước khi xác nhận đơn vì đó là thao tác không hoàn tác.",
            "Hiển thị state đơn hàng: draft=Nháp, sale=Đã xác nhận, done=Hoàn thành, cancel=Hủy.",
        ],
        markdown=True,
    )
