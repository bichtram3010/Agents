"""
Import script cải tiến — đọc data/products.json và đồng bộ vào Odoo.

Tính năng:
  - Upsert products (tạo mới hoặc cập nhật nếu SKU đã tồn tại)
  - Set tồn kho (stock.quant) cho từng sản phẩm
  - Tạo cây category tự động
  - Progress bar, báo lỗi từng sản phẩm (không dừng toàn bộ)
  - Idempotent: chạy nhiều lần không bị trùng data

Chạy:
  python -m backend.scripts.import_products
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from xmlrpc.client import Fault  # noqa: F401


def _is_none_marshal_error(e: Exception) -> bool:
    return "cannot marshal None" in str(e) or "allow_none" in str(e)

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from backend.tools.odoo_client import get_odoo  # noqa: E402

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "products.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def ensure_category(odoo, name: str, parent_id: int | None = None) -> int:
    domain = [["name", "=", name], ["parent_id", "=" if parent_id else "=", parent_id or False]]
    rec = odoo.search_read("product.category", domain, ["id"], limit=1)
    if rec:
        return rec[0]["id"]
    return odoo.create("product.category", {"name": name, "parent_id": parent_id or False})


def get_internal_location(odoo) -> int:
    """Lấy location kho nội bộ chính (WH/Stock)."""
    # Ưu tiên location tên 'Stock' trong kho mặc định
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
        raise RuntimeError("Không tìm thấy stock.location internal. Hãy tạo kho hàng trong Odoo trước.")
    print(f"  📦 Kho: {loc[0]['complete_name']} (id={loc[0]['id']})")
    return loc[0]["id"]


def set_stock_qty(odoo, product_tmpl_id: int, qty: float, location_id: int) -> bool:
    """Set tồn kho cho sản phẩm. Trả về True nếu thành công."""
    try:
        # Lấy product.product variant từ template
        variants = odoo.search_read(
            "product.product",
            [["product_tmpl_id", "=", product_tmpl_id]],
            ["id"], limit=1,
        )
        if not variants:
            return False
        product_id = variants[0]["id"]

        # Tìm stock.quant hiện có
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
        except Exception as e:
            if not _is_none_marshal_error(e):
                raise
            # Odoo OK nhưng return None → XML-RPC lỗi serialize → bỏ qua
        return True

    except Exception as e:
        print(f"    ⚠️  Set stock thất bại: {e}")
        return False


def progress(current: int, total: int, label: str = "") -> str:
    pct = int(current / total * 20)
    bar = "█" * pct + "░" * (20 - pct)
    return f"[{bar}] {current}/{total} {label}"


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  Odoo Product Import — Fashion & Cosmetics")
    print("=" * 60)

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    products = data["products"]
    total = len(products)

    print(f"\n📋 Tổng: {total} sản phẩm, {len(data['categories'])} category\n")

    odoo = get_odoo()
    print(f"✅ Kết nối Odoo: uid={odoo.uid}\n")

    # ── 1. Categories ────────────────────────────────────────────────────────
    print("📁 Đang tạo categories...")
    cat_map: dict[str, int] = {}
    for c in data["categories"]:
        if c["parent"] is None:
            cat_map[c["id"]] = ensure_category(odoo, c["name"])
    for c in data["categories"]:
        if c["parent"] is not None:
            cat_map[c["id"]] = ensure_category(odoo, c["name"], cat_map[c["parent"]])
    print(f"  ✅ {len(cat_map)} categories sẵn sàng\n")

    # ── 2. Internal location ─────────────────────────────────────────────────
    print("📦 Tìm kho hàng...")
    try:
        location_id = get_internal_location(odoo)
    except RuntimeError as e:
        print(f"  ❌ {e}")
        location_id = None
    print()

    # ── 3. Products ──────────────────────────────────────────────────────────
    print("🛍️  Đang import sản phẩm...\n")
    stats = {"created": 0, "updated": 0, "stock_ok": 0, "stock_fail": 0, "error": 0}
    errors: list[str] = []

    for i, p in enumerate(products, 1):
        label = f"{p['sku']} — {p['name'][:30]}"
        print(f"\r{progress(i, total, label)}", end="", flush=True)

        try:
            values = {
                "name": p["name"],
                "default_code": p["sku"],
                "list_price": float(p["list_price"]),
                "standard_price": float(p["standard_price"]),
                "categ_id": cat_map[p["category"]],
                "barcode": p.get("barcode", "") or "",
                "description_sale": p.get("description", ""),
                "type": "consu",
                "is_storable": True,
            }

            existing = odoo.search_read(
                "product.template",
                [["default_code", "=", p["sku"]]],
                ["id"], limit=1,
            )

            if existing:
                tmpl_id = existing[0]["id"]
                odoo.write("product.template", [tmpl_id], values)
                stats["updated"] += 1
                action = "↺ updated"
            else:
                tmpl_id = odoo.create("product.template", values)
                stats["created"] += 1
                action = "✚ created"

            # Set tồn kho
            qty = float(p.get("stock_qty", 0))
            if location_id and qty > 0:
                ok = set_stock_qty(odoo, tmpl_id, qty, location_id)
                if ok:
                    stats["stock_ok"] += 1
                else:
                    stats["stock_fail"] += 1

            # Nhỏ delay tránh rate limit
            time.sleep(0.1)

        except Exception as e:
            stats["error"] += 1
            errors.append(f"{p['sku']}: {e}")

    # ── 4. Summary ───────────────────────────────────────────────────────────
    print(f"\n\n{'=' * 60}")
    print("  KẾT QUẢ IMPORT")
    print("=" * 60)
    print(f"  ✚ Tạo mới  : {stats['created']}")
    print(f"  ↺ Cập nhật : {stats['updated']}")
    print(f"  📦 Tồn kho OK   : {stats['stock_ok']}")
    print(f"  ⚠️  Tồn kho lỗi  : {stats['stock_fail']}")
    print(f"  ❌ Lỗi sản phẩm  : {stats['error']}")
    print(f"  📊 Tổng xử lý   : {stats['created'] + stats['updated'] + stats['error']}/{total}")

    if errors:
        print("\n⚠️  Danh sách lỗi:")
        for err in errors:
            print(f"  - {err}")

    print("\n✅ Xong! Vào Odoo để kiểm tra: Inventory > Products")
    print("=" * 60)


if __name__ == "__main__":
    main()
