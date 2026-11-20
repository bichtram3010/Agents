"""Shipping zones understand Vietnamese with diacritics; low-stock works on Odoo 19."""
from __future__ import annotations

import pytest

from backend.cache import get_odoo_cache
from backend.tools import multi_shop_tools, odoo_tools


@pytest.mark.parametrize("address,zone", [
    ("Da Nang", "mien_trung"),
    ("Đà Nẵng", "mien_trung"),
    ("Thừa Thiên Huế", "mien_trung"),
    ("Hà Nội", "noi_thanh_hn"),
    ("HN", "noi_thanh_hn"),
    ("TP.HCM", "noi_thanh_hcm"),
    ("Quận 1, Hồ Chí Minh", "noi_thanh_hcm"),
    ("Sài Gòn", "noi_thanh_hcm"),
    ("Hải Phòng", "mien_bac"),
    ("Thanh Hóa", "mien_bac"),
    ("Cần Thơ", "mien_nam_xa"),
    ("Vũng Tàu", "mien_nam_xa"),
    ("Mars", "khac"),
])
def test_zone_with_and_without_diacritics(address, zone):
    assert odoo_tools._resolve_zone(address) == zone
    # the multi-shop comparison uses the same table
    assert multi_shop_tools._resolve_zone(address) == zone


def test_short_codes_match_whole_words_only():
    # "hn" must not match inside another word
    assert odoo_tools._resolve_zone("Ohnstadt") == "khac"


def test_shipping_fee_for_vietnamese_input():
    result = odoo_tools.calculate_shipping_fee(destination="Đà Nẵng", order_total=300_000)
    assert result["zone"] == "mien_trung"
    assert result["fee"] == 30_000


class FakeOdoo:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search_read(self, model, domain=None, fields=None, limit=80, offset=0, order=None):
        self.calls.append({"model": model, "domain": domain, "limit": limit, "order": order})
        return [dict(r) for r in self.rows]


def test_low_stock_does_not_ask_odoo_to_sort_by_qty_available(monkeypatch):
    # Odoo 19: qty_available is not stored, so ORDER BY qty_available raises
    fake = FakeOdoo([
        {"id": 1, "default_code": "A", "qty_available": 97},
        {"id": 2, "default_code": "B", "qty_available": 78},
        {"id": 3, "default_code": "C", "qty_available": 90},
    ])
    monkeypatch.setattr(odoo_tools, "get_odoo", lambda: fake)
    get_odoo_cache().clear()

    rows = odoo_tools.low_stock_products(threshold=100, limit=2)

    assert [r["default_code"] for r in rows] == ["B", "C"]  # lowest stock first, limited
    (call,) = fake.calls
    assert not (call["order"] or "").startswith("qty_available")
    assert call["domain"] == [["qty_available", "<=", 100]]
    get_odoo_cache().clear()
