"""
Analytics/Report Agent - phân tích doanh số và báo cáo.
"""
import os
from agno.agent import Agent
from agno.models.groq import Groq
from agno.models.openai import OpenAILike

from ..tools.odoo_tools import (
    sales_summary_by_category, stock_value_by_category,
    top_products_by_price, revenue_summary, stock_overview,
)

_GROQ_MODEL_ID = "llama-3.3-70b-versatile"


def _model():
    """Groq nếu có GROQ_API_KEY; không thì dùng chung LLM của các agent khác
    (WOKU_API_KEY / WOKU_BASE_URL / LLM_MODEL), để Analytics không chết khi thiếu key Groq."""
    if os.getenv("GROQ_API_KEY"):
        return Groq(id=_GROQ_MODEL_ID, api_key=os.getenv("GROQ_API_KEY"), max_tokens=4096)
    return OpenAILike(
        id=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
        api_key=os.getenv("WOKU_API_KEY"),
        base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
        max_tokens=4096,
    )


def make_analytics_agent() -> Agent:
    return Agent(
        name="Analytics",
        role="Phân tích doanh số, báo cáo theo danh mục, dashboard tổng quan",
        model=_model(),
        tools=[sales_summary_by_category, stock_value_by_category,
               top_products_by_price, revenue_summary, stock_overview],
        instructions=[
            "Bạn là chuyên viên phân tích dữ liệu kinh doanh.",
            "Khi user yêu cầu báo cáo, gọi các tool phù hợp rồi tổng hợp insight.",
            "Doanh số / bán được bao nhiêu theo danh mục → sales_summary_by_category.",
            "Giá trị hàng tồn kho theo danh mục → stock_value_by_category (đây KHÔNG phải doanh số).",
            "Luôn đưa ra: con số chính + nhận xét + đề xuất hành động.",
            "Format số tiền VND dạng có dấu phẩy, ví dụ 1.290.000 ₫.",
        ],
        markdown=True,
    )
