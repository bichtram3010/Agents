"""
ProductStock Agent — gộp ProductManager + Inventory thành 1 agent.

Lý do merge:
  - 2 agent cũ overlap tools (đều dùng list_products)
  - Supervisor thường nhầm lẫn route giữa 2 agent
  - Merge = bỏ được 1 LLM call/request + 1 model init

Trách nhiệm:
  - Xem / tạo / cập nhật sản phẩm
  - Tồn kho, cảnh báo, điều chỉnh
  - Danh mục, giá, barcode
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import (
    list_products, get_product, create_product,
    update_product_price, list_categories,
    low_stock_products, stock_overview, adjust_stock,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_product_stock_agent() -> Agent:
    return Agent(
        name="ProductStock",
        role="Quản lý sản phẩm và tồn kho cho shop thời trang + mỹ phẩm",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=2048,  # giảm từ 4096 — đủ cho responses ngắn
        ),
        tools=[
            list_products,
            get_product,
            create_product,
            update_product_price,
            list_categories,
            low_stock_products,
            stock_overview,
            adjust_stock,
        ],
        instructions=[
            "Bạn quản lý sản phẩm và kho hàng. Dùng đúng tool:",
            "  - Xem sản phẩm/giá → list_products hoặc get_product",
            "  - Tạo/sửa sản phẩm → create_product / update_product_price",
            "  - Tồn kho tổng quan → stock_overview",
            "  - Sản phẩm sắp hết → low_stock_products(threshold=30)",
            "  - Điều chỉnh tồn kho → adjust_stock",
            "Trả lời ngắn gọn, dùng bảng markdown, đơn vị VND.",
        ],
        markdown=True,
    )
