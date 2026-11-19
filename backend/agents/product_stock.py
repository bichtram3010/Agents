"""
ProductStock Agent — gộp ProductManager + Inventory thành 1 agent.

Lý do merge:
  - 2 agent cũ overlap tools (đều dùng list_products)
  - Supervisor thường nhầm lẫn route giữa 2 agent
  - Merge = bỏ được 1 LLM call/request + 1 model init

Trách nhiệm (CHỈ ĐỌC — agent này nằm trong chatbot khách hàng):
  - Xem sản phẩm, giá, danh mục, barcode
  - Tồn kho, cảnh báo sắp hết

Tạo/sửa sản phẩm, đổi giá, chỉnh tồn kho là việc của admin: dùng Warehouse agent
(backend/agents/warehouse.py, chạy riêng) hoặc Odoo, không mở qua chat.
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import (
    list_products, get_product, list_categories,
    low_stock_products, stock_overview,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_product_stock_agent() -> Agent:
    return Agent(
        name="ProductStock",
        role="Tra cứu sản phẩm và tồn kho cho shop thời trang + mỹ phẩm (chỉ đọc)",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=2048,  # giảm từ 4096 — đủ cho responses ngắn
        ),
        tools=[
            list_products,
            get_product,
            list_categories,
            low_stock_products,
            stock_overview,
        ],
        instructions=[
            "Bạn tra cứu sản phẩm và kho hàng. Dùng đúng tool:",
            "  - Xem sản phẩm/giá → list_products hoặc get_product",
            "  - Danh mục → list_categories",
            "  - Tồn kho tổng quan → stock_overview",
            "  - Sản phẩm sắp hết → low_stock_products(threshold=30)",
            "Bạn KHÔNG được tạo/sửa sản phẩm, đổi giá hay chỉnh tồn kho. "
            "Nếu được yêu cầu, trả lời rằng việc này do nhân viên làm trong Odoo.",
            "Trả lời ngắn gọn, dùng bảng markdown, đơn vị VND.",
        ],
        markdown=True,
    )
