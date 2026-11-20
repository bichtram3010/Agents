"""
Cấu hình một DB Odoo mới (local, docker-compose.odoo.yml) cho repo này, chạy 1 lần
trước import_products / fix_stock / setup_shops:

  - Tiền tệ công ty = VND (giá trong products.json là VND)
  - Bật Pricelists (setup_shops tạo 3 bảng giá)
  - Bật Storage Locations (setup_shops tạo kho BC, CH)

Chạy từ thư mục gốc:
    python -m backend.scripts.setup_local_odoo
Idempotent: chạy lại không sao.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from backend.tools.odoo_client import get_odoo  # noqa: E402


def set_company_currency_vnd(odoo) -> None:
    vnd = odoo.search_read("res.currency", [["name", "=", "VND"], ["active", "in", [True, False]]],
                           ["id", "active"], limit=1)
    if not vnd:
        raise RuntimeError("Không tìm thấy tiền tệ VND trong Odoo")
    if not vnd[0]["active"]:
        odoo.write("res.currency", [vnd[0]["id"]], {"active": True})
    company = odoo.search_read("res.company", [], ["id", "currency_id"], limit=1)[0]
    if company["currency_id"][0] != vnd[0]["id"]:
        odoo.write("res.company", [company["id"]], {"currency_id": vnd[0]["id"]})
    # Bảng giá mặc định (tạo cùng DB) vẫn để USD: đơn hàng lấy tiền tệ theo bảng giá,
    # nên báo giá hiện "$" dù công ty dùng VND.
    usd_pricelists = odoo.search_read("product.pricelist", [["currency_id", "!=", vnd[0]["id"]]], ["id"])
    if usd_pricelists:
        odoo.write("product.pricelist", [p["id"] for p in usd_pricelists], {"currency_id": vnd[0]["id"]})
    print(f"✓ Tiền tệ công ty và bảng giá: VND (id {vnd[0]['id']})")


def enable_settings(odoo) -> None:
    # Odoo 19 không còn group_stock_multi_warehouses: "Storage Locations" bật cả nhiều kho.
    values = {
        "group_product_pricelist": True,
        "group_stock_multi_locations": True,
    }
    settings_id = odoo.create("res.config.settings", values)
    odoo.execute("res.config.settings", "execute", [[settings_id]])
    print("✓ Đã bật: Pricelists, Storage Locations (nhiều kho / vị trí)")


def main() -> None:
    odoo = get_odoo()
    print(f"Odoo uid={odoo.uid} @ {odoo.url} / {odoo.db}")
    set_company_currency_vnd(odoo)
    enable_settings(odoo)


if __name__ == "__main__":
    main()
