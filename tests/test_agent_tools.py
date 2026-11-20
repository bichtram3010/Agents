"""Agents reachable from the customer chat must not change prices, stock or confirm orders."""
from __future__ import annotations

from backend.agents.product_stock import make_product_stock_agent
from backend.agents.sales_order import make_sales_order_agent
from backend.agents.team import get_all_agents

WRITE_TOOLS = {"create_product", "update_product_price", "adjust_stock", "confirm_sale_order",
               "import_products_json", "receive_goods", "set_stock_level",
               "create_single_product", "update_product_info"}


def _tool_names(agent) -> set[str]:
    return {getattr(t, "__name__", None) or getattr(t, "name", None) for t in agent.tools}


def test_product_stock_agent_is_read_only():
    names = _tool_names(make_product_stock_agent())
    assert "list_products" in names
    assert not names & WRITE_TOOLS


def test_sales_agent_cannot_confirm_orders():
    names = _tool_names(make_sales_order_agent())
    assert "create_quotation" in names
    assert "confirm_sale_order" not in names


def test_quotation_ignores_price_from_chat(monkeypatch):
    from backend.tools import odoo_tools

    created = []

    class FakeOdoo:
        def create(self, model, values):
            created.append((model, values))
            return 7

    monkeypatch.setattr(odoo_tools, "get_odoo", lambda: FakeOdoo())
    odoo_tools.create_quotation(3, [{"product_id": 11, "qty": 2, "price": 1000}])
    (_, values), = created
    (_, _, line), = values["order_line"]
    assert line == {"product_id": 11, "product_uom_qty": 2}


def test_shipping_prompt_has_no_price_table():
    """Found while recording the demo: the prompt listed 'miền Bắc: 40.000 ₫' and the
    model answered 40.000 ₫ for Hà Nội from memory instead of calling the tool (25.000 ₫).
    Fees must only come from calculate_shipping_fee."""
    import re

    from backend.agents.shipping import make_shipping_agent

    instructions = "\n".join(make_shipping_agent().instructions)
    assert not re.search(r"\d{2}\.000", instructions)
    assert "calculate_shipping_fee" in instructions


def test_comparison_prompt_names_the_real_shops_only():
    """Found while taking demo screenshots: the model invented 'Shop Xanh', 'Shop HAPPY'."""
    from backend.agents.comparison import make_comparison_agent

    instructions = "\n".join(make_comparison_agent().instructions)
    for shop in ("Shop Trâm", "Beauty Corner", "Cosmo Hub"):
        assert shop in instructions
    assert "Không nhắc shop hay sàn nào khác" in instructions


def test_no_chat_agent_has_a_write_tool():
    for agent in get_all_agents():
        assert not _tool_names(agent) & WRITE_TOOLS, agent.name
