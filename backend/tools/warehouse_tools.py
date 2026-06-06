"""
Warehouse Tools — import sản phẩm, quản lý kho, hiển thị catalog.

Tools này dùng cho Warehouse Agent:
  - import_products_json      → import từ JSON string
  - receive_goods             → nhập thêm hàng vào kho (tăng qty)
  - set_stock_level           → điều chỉnh tồn kho về mức cụ thể
  - get_product_by_sku        → lấy thông tin 1 sản phẩm theo SKU
  - list_products_table       → hiển thị catalog dạng bảng markdown
  - stock_report              → báo cáo tồn kho đầy đủ
  - create_single_product     → tạo 1 sản phẩm mới từ thông tin
  - update_product_info       → cập nhật tên/mô tả/giá
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .odoo_client import get_odoo
from ..cache.odoo_cache import odoo_cached, get_odoo_cache

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_create_category(odoo, name: str, parent_name: str | None = None) -> int:
    """Tìm hoặc tạo category. Hỗ trợ parent."""
    parent_id = None
    if parent_name:
        p = odoo.search_read("product.category", [["name", "=", parent_name]], ["id"], limit=1)
        if p:
            parent_id = p[0]["id"]
        else:
            parent_id = odoo.create("product.category", {"name": parent_name})

    domain = [["name", "=", name], ["parent_id", "=" if parent_id else "=", parent_id or False]]
    rec = odoo.search_read("product.category", domain, ["id"], limit=1)
    if rec:
        return rec[0]["id"]
    return odoo.create("product.category", {"name": name, "parent_id": parent_id or False})


def _get_internal_location(odoo) -> int | None:
    loc = odoo.search_read("stock.location", [["usage", "=", "internal"], ["name", "=", "Stock"]],
                           ["id"], limit=1)
    if not loc:
        loc = odoo.search_read("stock.location", [["usage", "=", "internal"]], ["id"], limit=1)
    return loc[0]["id"] if loc else None


def _set_quant(odoo, product_tmpl_id: int, qty: float, location_id: int) -> bool:
    variants = odoo.search_read("product.product", [["product_tmpl_id", "=", product_tmpl_id]],
                                ["id"], limit=1)
    if not variants:
        return False
    product_id = variants[0]["id"]
    quants = odoo.search_read("stock.quant",
                              [["product_id", "=", product_id], ["location_id", "=", location_id]],
                              ["id", "inventory_quantity"], limit=1)
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
    except Exception as e:
        # Odoo executed OK, chỉ return value chứa None → XML-RPC không marshal được
        if "cannot marshal None" not in str(e) and "allow_none" not in str(e):
            return False
    return True


def _receive_quant(odoo, product_tmpl_id: int, qty_add: float, location_id: int) -> float:
    """Tăng tồn kho thêm qty_add (nhập hàng thêm)."""
    variants = odoo.search_read("product.product", [["product_tmpl_id", "=", product_tmpl_id]],
                                ["id", "qty_available"], limit=1)
    if not variants:
        return 0
    product_id = variants[0]["id"]
    current_qty = float(variants[0].get("qty_available", 0))
    new_qty = current_qty + qty_add
    _set_quant(odoo, product_tmpl_id, new_qty, location_id)
    return new_qty


# ── Tools ─────────────────────────────────────────────────────────────────────

def import_products_json(json_data: str) -> str:
    """
    Import sản phẩm từ JSON string vào Odoo.

    JSON có thể là:
    - Danh sách: [{"sku": "X", "name": "Y", "list_price": 100000, ...}, ...]
    - Object có key "products": {"products": [...]}
    - Hoặc đường dẫn file: "products.json" (trong thư mục data/)

    Các field hỗ trợ:
      sku, name, category, parent_category, list_price, standard_price,
      stock_qty, barcode, description
    """
    odoo = get_odoo()

    # Parse input
    if json_data.strip().endswith(".json"):
        fp = DATA_DIR / json_data.strip()
        if not fp.exists():
            return f"❌ Không tìm thấy file: {fp}"
        raw = json.loads(fp.read_text(encoding="utf-8"))
    else:
        try:
            raw = json.loads(json_data)
        except json.JSONDecodeError as e:
            return f"❌ JSON không hợp lệ: {e}"

    products = raw if isinstance(raw, list) else raw.get("products", [])
    if not products:
        return "❌ Không có sản phẩm nào trong dữ liệu."

    location_id = _get_internal_location(odoo)
    created, updated, stock_set, errors = 0, 0, 0, []

    for p in products:
        try:
            sku = p.get("sku") or p.get("default_code", "")
            name = p.get("name", "")
            if not name:
                errors.append(f"Bỏ qua: thiếu name (sku={sku})")
                continue

            # Category
            cat_name = p.get("category", "General")
            parent_cat = p.get("parent_category")
            cat_id = _get_or_create_category(odoo, cat_name, parent_cat)

            values: dict[str, Any] = {
                "name": name,
                "list_price": float(p.get("list_price", 0)),
                "standard_price": float(p.get("standard_price", 0)),
                "categ_id": cat_id,
                "type": "consu",
                "is_storable": True,
            }
            if sku:
                values["default_code"] = sku
            if p.get("barcode"):
                values["barcode"] = str(p["barcode"])
            if p.get("description"):
                values["description_sale"] = p["description"]

            # Upsert
            existing = odoo.search_read("product.template",
                                        [["default_code", "=", sku]] if sku else [["name", "=", name]],
                                        ["id"], limit=1)
            if existing:
                tmpl_id = existing[0]["id"]
                odoo.write("product.template", [tmpl_id], values)
                updated += 1
            else:
                tmpl_id = odoo.create("product.template", values)
                created += 1

            # Stock
            qty = float(p.get("stock_qty", p.get("qty", 0)))
            if location_id and qty > 0:
                _set_quant(odoo, tmpl_id, qty, location_id)
                stock_set += 1

        except Exception as e:
            errors.append(f"{p.get('sku', p.get('name', '?'))}: {e}")

    # Invalidate cache
    get_odoo_cache().invalidate_prefix("list_products")
    get_odoo_cache().invalidate_prefix("stock_overview")

    lines = [
        "## ✅ Import hoàn tất\n",
        f"| Mục | Số lượng |",
        f"|-----|---------|",
        f"| ✚ Tạo mới | {created} |",
        f"| ↺ Cập nhật | {updated} |",
        f"| 📦 Set tồn kho | {stock_set} |",
        f"| ❌ Lỗi | {len(errors)} |",
        f"| 📊 Tổng | {created + updated + len(errors)} |",
    ]
    if errors:
        lines.append("\n**Chi tiết lỗi:**")
        for e in errors[:5]:
            lines.append(f"- {e}")
        if len(errors) > 5:
            lines.append(f"- ... và {len(errors)-5} lỗi khác")

    return "\n".join(lines)


def receive_goods(sku: str, qty: float, note: str = "") -> str:
    """
    Nhập thêm hàng vào kho (tăng tồn kho).

    Args:
        sku: Mã SKU sản phẩm (vd: COS-SK-021)
        qty: Số lượng nhập thêm (phải > 0)
        note: Ghi chú (tùy chọn, vd: "Nhập từ NCC ABC")

    Khác với set_stock_level: hàm này CỘNG THÊM vào tồn kho hiện có.
    """
    if qty <= 0:
        return "❌ Số lượng nhập phải > 0"

    odoo = get_odoo()
    product = odoo.search_read("product.template", [["default_code", "=", sku.upper()]],
                               ["id", "name", "qty_available"], limit=1)
    if not product:
        return f"❌ Không tìm thấy sản phẩm SKU: {sku}"

    p = product[0]
    location_id = _get_internal_location(odoo)
    if not location_id:
        return "❌ Chưa có kho hàng. Tạo kho trong Odoo trước."

    old_qty = float(p["qty_available"])
    new_qty = _receive_quant(odoo, p["id"], qty, location_id)

    get_odoo_cache().invalidate_prefix("stock_overview")
    get_odoo_cache().invalidate_prefix("low_stock_products")
    get_odoo_cache().invalidate_prefix(f"get_product")

    note_str = f"\n📝 Ghi chú: {note}" if note else ""
    return (
        f"## 📦 Nhập kho thành công\n\n"
        f"| | |\n|---|---|\n"
        f"| **Sản phẩm** | {p['name']} |\n"
        f"| **SKU** | {sku.upper()} |\n"
        f"| **Tồn kho trước** | {old_qty:,.0f} |\n"
        f"| **Nhập thêm** | +{qty:,.0f} |\n"
        f"| **Tồn kho sau** | **{new_qty:,.0f}** |"
        f"{note_str}"
    )


def set_stock_level(sku: str, qty: float) -> str:
    """
    Điều chỉnh tồn kho về mức cụ thể (inventory adjustment).

    Args:
        sku: Mã SKU sản phẩm
        qty: Số lượng tồn kho mới (tuyệt đối, không phải delta)

    Dùng khi kiểm kê và muốn set chính xác tồn kho.
    """
    if qty < 0:
        return "❌ Tồn kho không thể âm"

    odoo = get_odoo()
    product = odoo.search_read("product.template", [["default_code", "=", sku.upper()]],
                               ["id", "name", "qty_available"], limit=1)
    if not product:
        return f"❌ Không tìm thấy sản phẩm SKU: {sku}"

    p = product[0]
    location_id = _get_internal_location(odoo)
    if not location_id:
        return "❌ Chưa có kho hàng."

    old_qty = float(p["qty_available"])
    _set_quant(odoo, p["id"], qty, location_id)

    delta = qty - old_qty
    delta_str = f"+{delta:,.0f}" if delta >= 0 else f"{delta:,.0f}"

    get_odoo_cache().invalidate_prefix("stock_overview")
    get_odoo_cache().invalidate_prefix("low_stock_products")

    return (
        f"## ✅ Điều chỉnh tồn kho\n\n"
        f"| | |\n|---|---|\n"
        f"| **Sản phẩm** | {p['name']} |\n"
        f"| **SKU** | {sku.upper()} |\n"
        f"| **Cũ → Mới** | {old_qty:,.0f} → **{qty:,.0f}** |\n"
        f"| **Thay đổi** | {delta_str} |"
    )


def get_product_by_sku(sku: str) -> str:
    """
    Lấy thông tin chi tiết 1 sản phẩm theo SKU.

    Args:
        sku: Mã SKU (vd: COS-SK-021, FSH-TS-001)
    """
    odoo = get_odoo()
    product = odoo.search_read(
        "product.template", [["default_code", "=", sku.upper()]],
        ["id", "name", "default_code", "list_price", "standard_price",
         "categ_id", "qty_available", "barcode", "description_sale"],
        limit=1,
    )
    if not product:
        return f"❌ Không tìm thấy sản phẩm SKU: {sku}"

    p = product[0]
    margin = ((p["list_price"] - p["standard_price"]) / p["list_price"] * 100) if p["list_price"] else 0
    low_stock = "⚠️ Sắp hết" if p["qty_available"] <= 30 else "✅ Đủ hàng"

    return (
        f"## 🏷️ {p['name']}\n\n"
        f"| Thông tin | Giá trị |\n|---|---|\n"
        f"| **SKU** | `{p['default_code']}` |\n"
        f"| **Danh mục** | {p['categ_id'][1] if p['categ_id'] else '-'} |\n"
        f"| **Giá bán** | {p['list_price']:,.0f} ₫ |\n"
        f"| **Giá vốn** | {p['standard_price']:,.0f} ₫ |\n"
        f"| **Biên lợi nhuận** | {margin:.1f}% |\n"
        f"| **Tồn kho** | {p['qty_available']:,.0f} — {low_stock} |\n"
        f"| **Barcode** | {p['barcode'] or '-'} |\n"
        + (f"\n**Mô tả:** {p['description_sale']}" if p.get("description_sale") else "")
    )


def list_products_table(category: str | None = None, low_stock_only: bool = False,
                        limit: int = 50) -> str:
    """
    Hiển thị danh sách sản phẩm dạng bảng markdown.

    Args:
        category: Lọc theo tên category (vd: "Fashion", "Skincare"). None = tất cả.
        low_stock_only: True = chỉ hiện sản phẩm tồn kho <= 30
        limit: Số sản phẩm tối đa (mặc định 50)
    """
    odoo = get_odoo()
    domain: list = []
    if category:
        domain.append(["categ_id.complete_name", "ilike", category])
    if low_stock_only:
        domain.append(["qty_available", "<=", 30])

    products = odoo.search_read(
        "product.template", domain,
        ["name", "default_code", "list_price", "categ_id", "qty_available"],
        limit=limit, order="categ_id asc, name asc",
    )

    if not products:
        return "❌ Không tìm thấy sản phẩm nào."

    title = "## 🛍️ Danh sách sản phẩm"
    if category:
        title += f" — {category}"
    if low_stock_only:
        title += " (⚠️ Tồn kho thấp)"

    header = f"\n{title}\n\n"
    header += f"_Tổng: {len(products)} sản phẩm_\n\n"
    header += "| SKU | Tên sản phẩm | Danh mục | Giá bán | Tồn kho |\n"
    header += "|-----|-------------|----------|---------|--------|\n"

    rows = []
    for p in products:
        sku = p.get("default_code") or "-"
        cat = p["categ_id"][1].split(" / ")[-1] if p.get("categ_id") else "-"
        qty = p["qty_available"]
        qty_str = f"⚠️ {qty:.0f}" if qty <= 30 else f"{qty:.0f}"
        price = f"{p['list_price']:,.0f} ₫"
        name = p["name"][:35] + "..." if len(p["name"]) > 35 else p["name"]
        rows.append(f"| `{sku}` | {name} | {cat} | {price} | {qty_str} |")

    return header + "\n".join(rows)


def stock_report(threshold: int = 30) -> str:
    """
    Báo cáo tổng quan tồn kho: thống kê, sản phẩm sắp hết, giá trị kho.

    Args:
        threshold: Ngưỡng cảnh báo tồn kho thấp (mặc định 30)
    """
    odoo = get_odoo()
    products = odoo.search_read(
        "product.template", [],
        ["name", "default_code", "qty_available", "standard_price", "list_price", "categ_id"],
        limit=500,
    )

    total_products = len(products)
    total_qty = sum(p["qty_available"] for p in products)
    total_cost_value = sum(p["qty_available"] * p["standard_price"] for p in products)
    total_retail_value = sum(p["qty_available"] * p["list_price"] for p in products)
    low_stock = [p for p in products if 0 < p["qty_available"] <= threshold]
    out_of_stock = [p for p in products if p["qty_available"] <= 0]

    report = [
        "## 📊 Báo Cáo Tồn Kho\n",
        "### Tổng quan",
        f"| Chỉ số | Giá trị |",
        f"|--------|---------|",
        f"| Tổng sản phẩm | {total_products} |",
        f"| Tổng số lượng | {total_qty:,.0f} |",
        f"| Giá trị vốn | {total_cost_value:,.0f} ₫ |",
        f"| Giá trị bán lẻ | {total_retail_value:,.0f} ₫ |",
        f"| SP sắp hết (≤{threshold}) | ⚠️ {len(low_stock)} |",
        f"| SP hết hàng | 🔴 {len(out_of_stock)} |",
    ]

    if low_stock:
        report.append(f"\n### ⚠️ Sắp hết hàng (tồn kho ≤ {threshold})")
        report.append("| SKU | Tên | Tồn kho |")
        report.append("|-----|-----|---------|")
        for p in sorted(low_stock, key=lambda x: x["qty_available"])[:15]:
            sku = p.get("default_code") or "-"
            report.append(f"| `{sku}` | {p['name'][:40]} | **{p['qty_available']:.0f}** |")

    if out_of_stock:
        report.append(f"\n### 🔴 Hết hàng ({len(out_of_stock)} sản phẩm)")
        report.append("| SKU | Tên |")
        report.append("|-----|-----|")
        for p in out_of_stock[:10]:
            sku = p.get("default_code") or "-"
            report.append(f"| `{sku}` | {p['name'][:40]} |")

    return "\n".join(report)


def create_single_product(name: str, sku: str, list_price: float,
                          category: str = "General",
                          standard_price: float = 0,
                          stock_qty: float = 0,
                          description: str = "") -> str:
    """
    Tạo 1 sản phẩm mới trong Odoo.

    Args:
        name: Tên sản phẩm
        sku: Mã SKU (unique)
        list_price: Giá bán (VND)
        category: Tên danh mục (mặc định "General")
        standard_price: Giá vốn (VND)
        stock_qty: Số lượng tồn kho ban đầu
        description: Mô tả sản phẩm
    """
    odoo = get_odoo()

    # Kiểm tra SKU đã tồn tại chưa
    existing = odoo.search_read("product.template", [["default_code", "=", sku]], ["id"], limit=1)
    if existing:
        return f"❌ SKU `{sku}` đã tồn tại. Dùng set_stock_level hoặc update để cập nhật."

    cat_id = _get_or_create_category(odoo, category)

    values: dict[str, Any] = {
        "name": name,
        "default_code": sku,
        "list_price": float(list_price),
        "standard_price": float(standard_price),
        "categ_id": cat_id,
        "type": "consu",
        "is_storable": True,
    }
    if description:
        values["description_sale"] = description

    tmpl_id = odoo.create("product.template", values)

    # Set tồn kho ban đầu
    stock_msg = ""
    if stock_qty > 0:
        location_id = _get_internal_location(odoo)
        if location_id:
            _set_quant(odoo, tmpl_id, stock_qty, location_id)
            stock_msg = f"\n| **Tồn kho** | {stock_qty:,.0f} |"

    get_odoo_cache().invalidate_prefix("list_products")

    return (
        f"## ✅ Tạo sản phẩm thành công\n\n"
        f"| | |\n|---|---|\n"
        f"| **Tên** | {name} |\n"
        f"| **SKU** | `{sku}` |\n"
        f"| **Danh mục** | {category} |\n"
        f"| **Giá bán** | {list_price:,.0f} ₫ |\n"
        f"| **Giá vốn** | {standard_price:,.0f} ₫ |"
        f"{stock_msg}"
        f"\n\n_Odoo ID: {tmpl_id}_"
    )


def update_product_info(sku: str, name: str | None = None,
                        list_price: float | None = None,
                        standard_price: float | None = None,
                        description: str | None = None) -> str:
    """
    Cập nhật thông tin sản phẩm (tên, giá, mô tả).

    Args:
        sku: Mã SKU cần cập nhật
        name: Tên mới (None = giữ nguyên)
        list_price: Giá bán mới (None = giữ nguyên)
        standard_price: Giá vốn mới (None = giữ nguyên)
        description: Mô tả mới (None = giữ nguyên)
    """
    odoo = get_odoo()
    product = odoo.search_read("product.template", [["default_code", "=", sku.upper()]],
                               ["id", "name", "list_price"], limit=1)
    if not product:
        return f"❌ Không tìm thấy sản phẩm SKU: {sku}"

    p = product[0]
    values: dict[str, Any] = {}
    changes = []

    if name is not None:
        values["name"] = name
        changes.append(f"Tên: {p['name']} → {name}")
    if list_price is not None:
        values["list_price"] = float(list_price)
        changes.append(f"Giá bán: {p['list_price']:,.0f} → {list_price:,.0f} ₫")
    if standard_price is not None:
        values["standard_price"] = float(standard_price)
        changes.append(f"Giá vốn mới: {standard_price:,.0f} ₫")
    if description is not None:
        values["description_sale"] = description
        changes.append("Đã cập nhật mô tả")

    if not values:
        return "⚠️ Không có thông tin nào để cập nhật."

    odoo.write("product.template", [p["id"]], values)
    get_odoo_cache().invalidate_prefix("list_products")
    get_odoo_cache().invalidate_prefix("get_product")

    changes_str = "\n".join(f"- {c}" for c in changes)
    return f"## ✅ Cập nhật `{sku.upper()}` — {p['name']}\n\n{changes_str}"
