"""
Setup 3 shops trong cùng 1 Odoo instance.

Mỗi shop = 1 Warehouse + 1 Pricelist + tồn kho riêng + giá riêng.

Shops:
  shop1 = "Shop Trâm"      → WH (mặc định)  + giá gốc
  shop2 = "Beauty Corner"  → WH2 (mới tạo)  + giá cao hơn 10-20%
  shop3 = "Cosmo Hub"      → WH3 (mới tạo)  + giá thấp hơn (một số phá giá)

Chạy:
  python -m backend.scripts.setup_shops
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from backend.tools.odoo_client import get_odoo  # noqa: E402

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "products.json"
SHOPS_META_FILE = Path(__file__).resolve().parents[1] / "data" / "shops_meta.json"

# ── Cấu hình 3 shops ─────────────────────────────────────────────────────────

SHOPS = [
    {
        "id": "shop1",
        "name": "Shop Trâm",
        "wh_code": None,       # None = dùng WH mặc định
        "wh_name": None,
        "price_factor": 1.0,   # giá gốc
        "price_overrides": {},  # giá riêng cho từng SKU
        "description": "Shop chính hãng, uy tín",
        "tags": ["chính hãng", "đổi trả 30 ngày"],
        "rating": 4.8,
        "shipping": {
            "noi_thanh_hcm": 25000, "noi_thanh_hn": 25000,
            "mien_trung": 30000,    "mien_bac": 40000,
            "mien_nam_xa": 35000,   "khac": 45000,
            "free_ship_threshold": 500000,
            "express_fee": 60000,
        },
    },
    {
        "id": "shop2",
        "name": "Beauty Corner",
        "wh_code": "BC",
        "wh_name": "Beauty Corner Warehouse",
        "price_factor": 1.15,  # đắt hơn 15%
        "price_overrides": {
            "COS-SK-018": 780000,   # Serum Vit C: nhập cao cấp hơn
            "COS-FR-028": 1390000,  # Nước hoa: cao hơn
            "FSH-OW-009": 1090000,  # Blazer: cao cấp hơn
        },
        "description": "Chuyên mỹ phẩm nhập khẩu cao cấp",
        "tags": ["cao cấp", "nhập khẩu EU", "quà tặng"],
        "rating": 4.5,
        "shipping": {
            "noi_thanh_hcm": 30000, "noi_thanh_hn": 30000,
            "mien_trung": 38000,    "mien_bac": 48000,
            "mien_nam_xa": 42000,   "khac": 52000,
            "free_ship_threshold": 700000,
            "express_fee": 75000,
        },
    },
    {
        "id": "shop3",
        "name": "Cosmo Hub",
        "wh_code": "CH",
        "wh_name": "Cosmo Hub Warehouse",
        "price_factor": 0.85,  # rẻ hơn 15% mặc định
        "price_overrides": {
            # Một số SKU phá giá (bán gần/dưới giá vốn)
            "COS-SK-018": 320000,   # Serum Vit C: giá vốn 280k → margin rất thấp!
            "COS-MK-022": 125000,   # Son lì: giá vốn 110k → gần như phá giá!
            "COS-SK-016": 260000,   # Sữa rửa mặt: giá vốn 130k, thị trường 320k
            "FSH-TS-001": 159000,   # Áo thun: giá vốn 85k, thị trường 199k
            "COS-FR-030": 145000,   # Body mist: giá vốn 75k, rất rẻ
        },
        "description": "Giá tốt nhất thị trường, combo tiết kiệm",
        "tags": ["giá rẻ", "flash sale", "combo"],
        "rating": 4.1,
        "shipping": {
            "noi_thanh_hcm": 18000, "noi_thanh_hn": 18000,
            "mien_trung": 25000,    "mien_bac": 35000,
            "mien_nam_xa": 30000,   "khac": 40000,
            "free_ship_threshold": 9_999_999,  # không miễn ship
            "express_fee": 50000,
        },
    },
]

# Stock qty riêng cho từng shop (lấy từ products.json * factor)
SHOP_STOCK_FACTORS = {
    "shop1": 1.0,
    "shop2": 0.4,   # Beauty Corner ít hàng hơn
    "shop3": 2.5,   # Cosmo Hub nhiều hàng (bán giá thấp, cần volume)
}


def _is_none_error(e):
    return "cannot marshal None" in str(e) or "allow_none" in str(e)


# ── Setup helpers ─────────────────────────────────────────────────────────────

def get_or_create_warehouse(odoo, code: str, name: str) -> dict:
    """Tìm hoặc tạo warehouse. Trả về {id, lot_stock_id}."""
    wh = odoo.search_read("stock.warehouse", [["code", "=", code]],
                          ["id", "name", "lot_stock_id"], limit=1)
    if wh:
        print(f"  → Warehouse '{name}' đã tồn tại (id={wh[0]['id']})")
        return wh[0]

    wh_id = odoo.create("stock.warehouse", {
        "name": name,
        "code": code,
    })
    time.sleep(1)  # Odoo cần thời gian tạo location
    wh = odoo.search_read("stock.warehouse", [["id", "=", wh_id]],
                          ["id", "name", "lot_stock_id"], limit=1)
    print(f"  → Tạo warehouse '{name}' (id={wh_id})")
    return wh[0] if wh else {"id": wh_id, "lot_stock_id": False}


def get_or_create_pricelist(odoo, name: str, currency_id: int) -> int:
    """Tìm hoặc tạo pricelist."""
    pl = odoo.search_read("product.pricelist", [["name", "=", name]], ["id"], limit=1)
    if pl:
        print(f"  → Pricelist '{name}' đã tồn tại (id={pl[0]['id']})")
        return pl[0]["id"]
    pl_id = odoo.create("product.pricelist", {
        "name": name,
        "currency_id": currency_id,
        "active": True,
    })
    print(f"  → Tạo pricelist '{name}' (id={pl_id})")
    return pl_id


def set_pricelist_items(odoo, pricelist_id: int, products: list[dict],
                        price_factor: float, overrides: dict) -> int:
    """Tạo pricelist items cho từng sản phẩm."""
    count = 0
    for p in products:
        sku = p["sku"]
        base_price = float(p["list_price"])

        if sku in overrides:
            price = float(overrides[sku])
        else:
            price = round(base_price * price_factor, -3)  # làm tròn hàng nghìn

        # Tìm product.template
        tmpl = odoo.search_read("product.template", [["default_code", "=", sku]], ["id"], limit=1)
        if not tmpl:
            continue
        tmpl_id = tmpl[0]["id"]

        # Xóa item cũ nếu có
        old = odoo.search_read("product.pricelist.item", [
            ["pricelist_id", "=", pricelist_id],
            ["product_tmpl_id", "=", tmpl_id],
        ], ["id"])
        if old:
            odoo.unlink("product.pricelist.item", [o["id"] for o in old])

        # Tạo item mới
        odoo.create("product.pricelist.item", {
            "pricelist_id": pricelist_id,
            "product_tmpl_id": tmpl_id,
            "compute_price": "fixed",
            "fixed_price": price,
            "applied_on": "1_product",
        })
        count += 1

    return count


def set_shop_stock(odoo, products: list[dict], location_id: int, factor: float) -> tuple:
    """Set tồn kho cho shop theo factor."""
    ok, fail = 0, 0
    for p in products:
        sku = p["sku"]
        qty = int(float(p.get("stock_qty", 0)) * factor)
        if qty <= 0:
            qty = max(5, int(float(p.get("stock_qty", 10)) * factor))

        tmpl = odoo.search_read("product.template", [["default_code", "=", sku]], ["id"], limit=1)
        if not tmpl:
            continue
        tmpl_id = tmpl[0]["id"]

        variants = odoo.search_read("product.product", [["product_tmpl_id", "=", tmpl_id]],
                                    ["id"], limit=1)
        if not variants:
            continue
        product_id = variants[0]["id"]

        quants = odoo.search_read("stock.quant",
                                  [["product_id", "=", product_id], ["location_id", "=", location_id]],
                                  ["id"], limit=1)
        if quants:
            odoo.write("stock.quant", [quants[0]["id"]], {"inventory_quantity": qty})
            quant_id = quants[0]["id"]
        else:
            quant_id = odoo.create("stock.quant", {
                "product_id": product_id,
                "location_id": location_id,
                "inventory_quantity": qty,
            })

        try:
            odoo.execute("stock.quant", "action_apply_inventory", [[quant_id]])
            ok += 1
        except Exception as e:
            if _is_none_error(e):
                ok += 1
            else:
                fail += 1

    return ok, fail


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Setup Multi-Shop trong Odoo")
    print("=" * 60)

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    products = data["products"]

    odoo = get_odoo()
    print(f"\n✅ Odoo uid={odoo.uid}\n")

    # Lấy VND currency
    currencies = odoo.search_read("res.currency", [["name", "=", "VND"]], ["id"], limit=1)
    if not currencies:
        currencies = odoo.search_read("res.currency", [["active", "in", [True, False]],
                                                        ["name", "=", "VND"]], ["id"], limit=1)
    if currencies:
        currency_id = currencies[0]["id"]
        print(f"💱 Currency VND id={currency_id}")
    else:
        # Fallback: dùng currency mặc định
        default_currency = odoo.search_read("res.currency", [["active", "=", True]], ["id"], limit=1)
        currency_id = default_currency[0]["id"] if default_currency else 1
        print(f"💱 Dùng currency id={currency_id} (VND không tìm thấy)")

    shops_meta = []

    for shop in SHOPS:
        sid = shop["id"]
        print(f"\n{'─' * 50}")
        print(f"🏪 Setup: {shop['name']} ({sid})")
        print(f"{'─' * 50}")

        # 1) Warehouse
        if shop["wh_code"]:
            wh = get_or_create_warehouse(odoo, shop["wh_code"], shop["wh_name"])
            wh_id = wh["id"]
            # Lấy location_id (lot_stock_id = WH/Stock)
            if wh.get("lot_stock_id"):
                location_id = wh["lot_stock_id"][0] if isinstance(wh["lot_stock_id"], list) else wh["lot_stock_id"]
            else:
                loc = odoo.search_read("stock.location",
                                       [["warehouse_id", "=", wh_id], ["usage", "=", "internal"]],
                                       ["id"], limit=1)
                location_id = loc[0]["id"] if loc else None
        else:
            # Shop 1: dùng WH mặc định
            wh_list = odoo.search_read("stock.warehouse", [["code", "=", "WH"]],
                                       ["id", "lot_stock_id"], limit=1)
            if not wh_list:
                wh_list = odoo.search_read("stock.warehouse", [], ["id", "lot_stock_id"], limit=1)
            wh_id = wh_list[0]["id"] if wh_list else None
            lot = wh_list[0].get("lot_stock_id") if wh_list else None
            location_id = (lot[0] if isinstance(lot, list) else lot) if lot else None
            print(f"  → Dùng warehouse mặc định id={wh_id}, location={location_id}")

        # 2) Pricelist
        pl_name = f"{shop['name']} — Bảng giá"
        pl_id = get_or_create_pricelist(odoo, pl_name, currency_id)

        # 3) Pricelist items
        n_items = set_pricelist_items(odoo, pl_id, products,
                                      shop["price_factor"], shop["price_overrides"])
        print(f"  → Set {n_items} pricelist items")

        # 4) Stock
        if location_id:
            factor = SHOP_STOCK_FACTORS[sid]
            ok, fail = set_shop_stock(odoo, products, location_id, factor)
            print(f"  → Stock: {ok} OK, {fail} lỗi (factor={factor})")
        else:
            print("  ⚠️  Không tìm thấy location, bỏ qua set stock")

        shops_meta.append({
            "id": sid,
            "name": shop["name"],
            "description": shop["description"],
            "tags": shop["tags"],
            "rating": shop["rating"],
            "warehouse_id": wh_id,
            "location_id": location_id,
            "pricelist_id": pl_id,
            "price_factor": shop["price_factor"],
            "price_overrides": shop["price_overrides"],
            "shipping": shop["shipping"],
        })

    # Lưu metadata
    SHOPS_META_FILE.write_text(
        json.dumps(shops_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n\n✅ Đã lưu shops_meta.json ({len(shops_meta)} shops)")
    print(f"   Path: {SHOPS_META_FILE}")
    print("\n" + "=" * 60)
    print("  SETUP HOÀN TẤT!")
    print("  Giờ có thể dùng Comparison Agent để so sánh giữa các shop.")
    print("=" * 60)


if __name__ == "__main__":
    main()
