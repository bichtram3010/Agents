"""
Agno OS - Web UI playground để chat trực tiếp với Team + 6 subagents.

Chạy:
    cd D:\\TRAM\\odoo-multi-agent
    backend\\.venv\\Scripts\\activate
    uvicorn backend.agno_os:app --reload --port 7777

Sau đó mở: http://localhost:7777
- Click vào từng agent / team để chat
- Xem tool calls, reasoning, history
- So sánh response giữa các agent
"""
from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv

# Load env trước khi import agents
load_dotenv(Path(__file__).parent / ".env", override=True)

from agno.os import AgentOS  # noqa: E402

from .agents.product_manager import make_product_manager_agent  # noqa: E402
from .agents.sales_order import make_sales_order_agent  # noqa: E402
from .agents.inventory import make_inventory_agent  # noqa: E402
from .agents.analytics import make_analytics_agent  # noqa: E402
from .agents.consultant import make_consultant_agent  # noqa: E402
from .agents.shipping import make_shipping_agent  # noqa: E402
from .agents.team import build_team  # noqa: E402


# Khởi tạo các agents (mỗi cái là instance độc lập, có thể chat riêng trên UI)
agents = [
    make_product_manager_agent(),
    make_sales_order_agent(),
    make_inventory_agent(),
    make_analytics_agent(),
    make_consultant_agent(),
    make_shipping_agent(),
]

team = build_team()

# AgentOS = FastAPI app có sẵn UI để chat + inspect
agent_os = AgentOS(
    name="Odoo Multi-Agent Playground",
    description="Chat với 6 subagents + 1 supervisor team. ERP Odoo + RAG + Shipping.",
    agents=agents,
    teams=[team],
)

app = agent_os.get_app()
