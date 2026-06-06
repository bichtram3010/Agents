"""
Script fix tồn kho: đọc stock_qty từ products.json và set vào Odoo.

Chạy:
  python -m backend.scripts.fix_stock

Xử lý:
  1. Đổi tất cả sản phẩm sang type='product' (storable, có tracking kho)
  2. Tìm internal location
  3. Set stock.quant cho từng sản phẩm
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from xmlrpc.client import Fault
from backend.tools.odoo_client import get_odoo  # noqa: E402


def _is_none_marshal_error(e: Exception) -> bool:
    """Odoo action_apply_inventory thành công nhưng trả None → XML-RPC lỗi serialize."""
    return "cannot marshal None" in str(e) or "allow_none" in str(e)

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "products.json"


def get_internal_location(odoo) -> int:
    # Thử WH/Stock trước
    loc = odoo.search_read(
        "stock.location",
        [["usage", "=", "internal"], ["name", "=", "Stock"]],
        ["id", "complete_name"], limit=1,
    )
    if not loc:
        loc = odoo.search_read(
            "stock.location",
            [["usage", "=", "internal"]],
            ["id", "complete_name"], limit=1,
        )
    if not loc:
        raise RuntimeError("Không tìm thấy kho nội bộ. Tạo kho trong Odoo trước.")
    print(f"  → Kho: {loc[0]['complete_name']} (id={loc[0]['id']})")
    return loc[0]["id"]


def set_stock(odoo, product_tmpl_id: int, qty: float, location_id: int) -> bool:
    # Lấy product.product variant
    variants = odoo.search_read(
        "product.product",
        [["product_tmpl_id", "=", product_tmpl_id]],
        ["id", "qty_available"], limit=1,
    )
    if not variants:
        return False

    product_id = variants[0]["id"]

    # Tìm hoặc tạo stock.quant
    quants = odoo.search_read(
        "stock.quant",
        [["product_id", "=", product_id], ["location_id", "=", location_id]],
        ["id"], limit=1,
    )

    if quants:
        odoo.write("stock.quant", [quants[0]["id"]], {"inventory_quantity": qty})
        quant_id = quants[0]["id"]
    else:
        quant_id = odoo.create("stock.quant", {
            "product_id": product_id,
            "location_id": location_id,
            "inventory_quantity": qty,
        })

    # Apply inventory adjustment
    try:
        odoo.execute("stock.quant", "action_apply_inventory", [[quant_id]])
        return True
    except Exception as e:
        # Odoo executed OK nhưng return value chứa None → XML-RPC không marshal được
        # → Đây là SUCCESS, không phải lỗi thật
        if _is_none_marshal_error(e):
            return True
        print(f"    ⚠️  {e}")
        return False


def main() -> None:
    print("=" * 55)
    print("  Fix Stock — Set tồn kho từ products.json")
    print("=" * 55)

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    products = data["products"]

    odoo = get_odoo()
    print(f"\n✅ Odoo uid={odoo.uid}")

    print("\n📦 Tìm kho hàng...")
    try:
        loc_id = get_internal_location(odoo)
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    # Lấy tất cả products hiện có trong Odoo
    print("\n📋 Đang đồng bộ tồn kho...\n")
    ok, fail, skip = 0, 0, 0

    for p in products:
        sku = p["sku"]
        qty = float(p.get("stock_qty", 0))

        # Tìm product template theo SKU
        existing = odoo.search_read(
            "product.template",
            [["default_code", "=", sku]],
            ["id", "name", "type", "qty_available"],
            limit=1,
        )

        if not existing:
            print(f"  ⚠️  {sku} — chưa có trong Odoo, bỏ qua (chạy import_products trước)")
            skip += 1
            continue

        tmpl = existing[0]
        tmpl_id = tmpl["id"]

        # Đổi sang type='product' nếu cần (storable product = có theo dõi kho)
        if tmpl.get("type") != "product":
            try:
                odoo.write("product.template", [tmpl_id], {"type": "product"})
            except Exception:
                # Một số Odoo version dùng is_storable thay type
                try:
                    odoo.write("product.template", [tmpl_id], {"is_storable": True})
                except Exception:
                    pass

        # Set stock
        success = set_stock(odoo, tmpl_id, qty, loc_id)

        status = "✅" if success else "❌"
        print(f"  {status} {sku:15} | {tmpl['name'][:30]:30} | qty={qty}")

        if success:
            ok += 1
        else:
            fail += 1

        time.sleep(0.05)  # tránh rate limit

    print(f"\n{'=' * 55}")
    print(f"  ✅ Thành công : {ok}")
    print(f"  ❌ Thất bại   : {fail}")
    print(f"  ⏭️  Bỏ qua    : {skip}")
    print(f"  📊 Tổng       : {ok + fail + skip}/{len(products)}")
    print("=" * 55)

    if skip > 0:
        print("\n⚠️  Có sản phẩm chưa tồn tại trong Odoo.")
        print("   Chạy trước: python -m backend.scripts.import_products")


if __name__ == "__main__":
    main()
