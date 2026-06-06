"""
Inventory Agent - giám sát tồn kho và cảnh báo hết hàng.
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import low_stock_products, stock_overview, adjust_stock, list_products

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_inventory_agent() -> Agent:
    return Agent(
        name="Inventory",
        role="Giám sát tồn kho, cảnh báo hết hàng, điều chỉnh số lượng",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=4096,
        ),
        tools=[low_stock_products, stock_overview, adjust_stock, list_products],
        instructions=[
            "Bạn là chuyên viên kho. Theo dõi tồn kho, cảnh báo các SKU sắp hết hàng (<= 30).",
            "Khi user hỏi tổng quan, dùng stock_overview.",
            "Khi điều chỉnh kho, giải thích rõ thay đổi và yêu cầu xác nhận.",
            "Đề xuất nhập hàng khi tồn kho thấp.",
        ],
        markdown=True,
    )
