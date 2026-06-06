"""
Product Manager Agent - quản lý danh mục sản phẩm trong Odoo.
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import (
    list_products, get_product, create_product,
    update_product_price, list_categories,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_product_manager_agent() -> Agent:
    return Agent(
        name="ProductManager",
        role="Quản lý sản phẩm thời trang và mỹ phẩm trên Odoo",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=4096,
        ),
        tools=[list_products, get_product, create_product, update_product_price, list_categories],
        instructions=[
            "Bạn là chuyên viên quản lý danh mục sản phẩm cho shop thời trang + mỹ phẩm.",
            "Khi user hỏi về sản phẩm, dùng list_products / get_product để lấy dữ liệu thật từ Odoo.",
            "Khi tạo sản phẩm mới, luôn yêu cầu đủ: tên, SKU (default_code), giá bán, giá vốn, category.",
            "Trả lời ngắn gọn, có cấu trúc, dùng đơn vị VND.",
            "Nếu user hỏi về tồn kho hoặc đơn hàng, nói rằng đó không phải phạm vi của bạn.",
        ],
        markdown=True,
    )
