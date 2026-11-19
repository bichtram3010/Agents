"""Analytics tools aggregate in Odoo (formatted_read_group, Odoo 19+) instead of
summing a capped search_read in Python. Odoo is replaced by a recording fake."""
from __future__ import annotations

import xmlrpc.client

import pytest

from backend.cache import get_odoo_cache
from backend.tools import odoo_client, odoo_tools


class FakeOdoo(odoo_client.OdooClient):
    """Real OdooClient logic; only execute() is faked (no network)."""

    def __init__(self, responses: dict, missing_formatted: bool = False):
        self.calls: list[tuple] = []
        self.responses = responses
        self.missing_formatted = missing_formatted

    def execute(self, model, method, args, kwargs=None):
        self.calls.append((model, method, args, kwargs or {}))
        if method == "formatted_read_group" and self.missing_formatted:
            raise xmlrpc.client.Fault(
                1, f"The method '{model}.formatted_read_group' does not exist")
        return self.responses[(model, method)]


@pytest.fixture(autouse=True)
def clear_cache():
    get_odoo_cache().clear()
    yield
    get_odoo_cache().clear()


def use(monkeypatch, fake):
    monkeypatch.setattr(odoo_tools, "get_odoo", lambda: fake)
    return fake


def test_revenue_summary_is_summed_by_odoo(monkeypatch):
    fake = use(monkeypatch, FakeOdoo({("sale.order", "formatted_read_group"): [
        {"__extra_domain": [], "amount_total:sum": 12_500_000.0, "__count": 1234},
    ]}))

    result = odoo_tools.revenue_summary()

    assert result == {"state": "sale", "order_count": 1234, "total_revenue": 12_500_000.0}
    (model, method, args, kwargs), = fake.calls
    assert (model, method, args) == ("sale.order", "formatted_read_group", [[["state", "=", "sale"]]])
    assert kwargs["groupby"] == []
    assert set(kwargs["aggregates"]) == {"amount_total:sum", "__count"}


def test_revenue_summary_with_no_orders(monkeypatch):
    use(monkeypatch, FakeOdoo({("sale.order", "formatted_read_group"): [
        {"__extra_domain": [], "amount_total:sum": None, "__count": 0},
    ]}))
    assert odoo_tools.revenue_summary() == {"state": "sale", "order_count": 0, "total_revenue": 0.0}


def test_older_odoo_falls_back_to_read_group(monkeypatch):
    fake = use(monkeypatch, FakeOdoo(
        {("sale.order", "read_group"): [{"amount_total": 300.0, "__count": 2}]},
        missing_formatted=True,
    ))
    assert odoo_tools.revenue_summary()["total_revenue"] == 300.0
    assert [c[1] for c in fake.calls] == ["formatted_read_group", "read_group"]
    assert fake.calls[1][3]["lazy"] is False


def test_sales_by_category_uses_sale_report(monkeypatch):
    fake = use(monkeypatch, FakeOdoo({("sale.report", "formatted_read_group"): [
        {"categ_id": [4, "Skincare"], "price_total:sum": 900.0, "product_uom_qty:sum": 6.0, "__count": 3},
        {"categ_id": False, "price_total:sum": 50.0, "product_uom_qty:sum": 1.0, "__count": 1},
    ]}))

    rows = odoo_tools.sales_summary_by_category()

    assert rows == [
        {"category": "Skincare", "revenue": 900.0, "qty_sold": 6.0, "order_lines": 3},
        {"category": "Uncategorized", "revenue": 50.0, "qty_sold": 1.0, "order_lines": 1},
    ]
    (model, method, args, kwargs), = fake.calls
    assert model == "sale.report"
    assert args == [[["state", "=", "sale"]]]
    assert kwargs["groupby"] == ["categ_id"]
    assert kwargs["order"] == "price_total:sum desc"


def test_stock_value_reads_every_product(monkeypatch):
    fake = use(monkeypatch, FakeOdoo({("product.template", "search_read"): [
        {"categ_id": [1, "Áo"], "list_price": 100.0, "qty_available": 2, "standard_price": 60.0},
        {"categ_id": [1, "Áo"], "list_price": 50.0, "qty_available": 4, "standard_price": 20.0},
    ]}))

    rows = odoo_tools.stock_value_by_category()

    assert rows == [{"category": "Áo", "products": 2, "stock_qty": 6,
                     "stock_value": 200.0, "retail_value": 400.0}]
    (_, _, _, kwargs), = fake.calls
    assert kwargs["limit"] is None  # no silent 100-product cap


def test_analytics_agent_has_the_new_tools():
    from backend.agents.analytics import make_analytics_agent

    names = {t.__name__ for t in make_analytics_agent().tools}
    assert {"revenue_summary", "sales_summary_by_category", "stock_value_by_category"} <= names
