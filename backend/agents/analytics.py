"""
Analytics/Report Agent - phân tích doanh số và báo cáo.
"""
import os
from agno.agent import Agent
from agno.models import Groq

from ..tools.odoo_tools import (
    sales_summary_by_category, top_products_by_price, revenue_summary, stock_overview,
)

_MODEL_ID = "llama-3.3-70b-versatile"

def make_analytics_agent() -> Agent:
    return Agent(
        name="Analytics",
        role="Phân tích doanh số, báo cáo theo danh mục, dashboard tổng quan",
        model=Groq(
            id=_MODEL_ID,
            api_key=os.getenv("GROQ_API_KEY"),
            max_tokens=4096,
        ),
        tools=[sales_summary_by_category, top_products_by_price, revenue_summary, stock_overview],
        instructions=[
            "Bạn là chuyên viên phân tích dữ liệu kinh doanh.",
            "Khi user yêu cầu báo cáo, gọi các tool phù hợp rồi tổng hợp insight.",
            "Luôn đưa ra: con số chính + nhận xét + đề xuất hành động.",
            "Format số tiền VND dạng có dấu phẩy, ví dụ 1.290.000 ₫.",
        ],
        markdown=True,
    )
