"""
Các tool function cho Agno agents.
Mỗi function là 1 tool có docstring rõ ràng để LLM hiểu.
"""
from __future__ import annotations

from typing import Any

from .odoo_client import get_odoo
from ..cache.odoo_cache import odoo_cached


# ============================================================
# PRODUCT TOOLS - dùng cho Product Manager Agent
# ============================================================
@odoo_cached
def list_products(category: str | None = None, search: str | None = None, limit: int = 30) -> list[dict]:
    """Liệt kê sản phẩm trong Odoo. Có thể lọc theo category name (Fashion/Cosmetics/...) hoặc tên/SKU."""
    odoo = get_odoo()
    domain: list[Any] = []
    if category:
        domain.append(["categ_id.complete_name", "ilike", category])
    if search:
        domain.append("|")
        domain.append(["name", "ilike", search])
        domain.append(["default_code", "ilike", search])
    return odoo.search_read(
        "product.template", domain,
        fields=["id", "name", "default_code", "list_price", "standard_price", "categ_id", "qty_available", "barcode"],
        limit=limit, order="id asc",
    )


@odoo_cached
def get_product(product_id: int) -> dict | None:
    """Lấy chi tiết 1 sản phẩm theo ID."""
    odoo = get_odoo()
    rec = odoo.read("product.template", [product_id], [
        "name", "default_code", "list_price", "standard_price", "categ_id",
        "qty_available", "barcode", "description_sale",
    ])
    return rec[0] if rec else None


def create_product(name: str, default_code: str, list_price: float, standard_price: float,
                   category_id: int, description: str = "", barcode: str = "") -> dict:
    """Tạo mới 1 sản phẩm. category_id là ID của product.category."""
    odoo = get_odoo()
    pid = odoo.create("product.template", {
        "name": name, "default_code": default_code,
        "list_price": list_price, "standard_price": standard_price,
        "categ_id": category_id, "barcode": barcode,
        "description_sale": description, "type": "consu", "is_storable": True,
    })
    return {"id": pid, "ok": True}


def update_product_price(product_id: int, list_price: float) -> dict:
    """Cập nhật giá bán của sản phẩm."""
    odoo = get_odoo()
    odoo.write("product.template", [product_id], {"list_price": list_price})
    return {"id": product_id, "list_price": list_price, "ok": True}


@odoo_cached
def list_categories() -> list[dict]:
    """Liệt kê tất cả product.category."""
    odoo = get_odoo()
    return odoo.search_read("product.category", [], ["id", "name", "complete_name", "parent_id"], limit=100, order="parent_id asc, name asc")


# ============================================================
# SALES / ORDER TOOLS - dùng cho Sales Agent
# ============================================================
@odoo_cached
def list_sale_orders(state: str | None = None, limit: int = 20) -> list[dict]:
    """Liệt kê đơn hàng (sale.order). state: draft/sent/sale/done/cancel."""
    odoo = get_odoo()
    domain = [["state", "=", state]] if state else []
    return odoo.search_read(
        "sale.order", domain,
        fields=["id", "name", "partner_id", "date_order", "state", "amount_total"],
        limit=limit, order="date_order desc",
    )


def create_quotation(partner_id: int, lines: list[dict]) -> dict:
    """Tạo báo giá mới. lines = [{product_id, qty, price?}]."""
    odoo = get_odoo()
    order_lines = []
    for ln in lines:
        line_vals = {"product_id": ln["product_id"], "product_uom_qty": ln.get("qty", 1)}
        if "price" in ln:
            line_vals["price_unit"] = ln["price"]
        order_lines.append((0, 0, line_vals))
    oid = odoo.create("sale.order", {"partner_id": partner_id, "order_line": order_lines})
    return {"id": oid, "ok": True}


def confirm_sale_order(order_id: int) -> dict:
    """Xác nhận báo giá thành đơn hàng (state -> sale)."""
    odoo = get_odoo()
    odoo.execute("sale.order", "action_confirm", [[order_id]])
    return {"id": order_id, "state": "sale", "ok": True}


@odoo_cached
def search_customers(query: str, limit: int = 10) -> list[dict]:
    """Tìm khách hàng theo tên, email hoặc số điện thoại."""
    odoo = get_odoo()
    domain = ["|", "|",
             ["name", "ilike", query],
             ["email", "ilike", query],
             ["phone", "ilike", query]]
    return odoo.search_read("res.partner", domain, ["id", "name", "email", "phone"], limit=limit)


def create_or_get_customer(name: str, phone: str = "", email: str = "",
                            address: str = "") -> dict:
    """Tìm khách theo tên+sđt; nếu chưa có thì tạo mới. Trả về dict {id, name, ...}."""
    odoo = get_odoo()
    # Tìm khớp chính xác trước
    domain = [["name", "=", name]]
    if phone:
        domain = ["&", domain[0], ["phone", "=", phone]]
    existing = odoo.search_read("res.partner", domain,
                                ["id", "name", "email", "phone"], limit=1)
    if existing:
        return {**existing[0], "created": False}

    # Tạo mới
    values: dict = {"name": name, "customer_rank": 1}
    if phone:
        values["phone"] = phone
    if email:
        values["email"] = email
    if address:
        values["street"] = address
    pid = odoo.create("res.partner", values)
    return {"id": pid, "name": name, "phone": phone, "email": email, "created": True}


# ============================================================
# SHIPPING TOOLS - dùng cho Shipping Agent
# ============================================================
# Bảng giá ship - source of truth (đồng bộ với faq.md trong knowledge base)
SHIPPING_TABLE = {
    # zone -> (base_fee, eta_days, eta_express_hours)
    "noi_thanh_hcm": {"base": 25000, "eta": "1-2 ngày", "express_fee": 60000, "express_eta": "4 giờ"},
    "noi_thanh_hn":  {"base": 25000, "eta": "1-2 ngày", "express_fee": 60000, "express_eta": "4 giờ"},
    "mien_trung":    {"base": 30000, "eta": "2-3 ngày", "express_fee": None,  "express_eta": None},
    "mien_bac":      {"base": 40000, "eta": "3-5 ngày", "express_fee": None,  "express_eta": None},
    "mien_nam_xa":   {"base": 35000, "eta": "2-4 ngày", "express_fee": None,  "express_eta": None},
    "khac":          {"base": 45000, "eta": "3-5 ngày", "express_fee": None,  "express_eta": None},
}

FREE_SHIP_THRESHOLD = 500_000  # VND, miễn ship cho đơn từ 500k

# Mapping tỉnh thành -> zone (rút gọn)
_PROVINCE_ZONE = {
    "hcm": "noi_thanh_hcm", "ho chi minh": "noi_thanh_hcm", "tp hcm": "noi_thanh_hcm",
    "sai gon": "noi_thanh_hcm", "saigon": "noi_thanh_hcm",
    "ha noi": "noi_thanh_hn", "hanoi": "noi_thanh_hn", "hn": "noi_thanh_hn",
    "da nang": "mien_trung", "hue": "mien_trung", "quang nam": "mien_trung",
    "quang ngai": "mien_trung", "binh dinh": "mien_trung", "khanh hoa": "mien_trung",
    "nha trang": "mien_trung", "phu yen": "mien_trung",
    "hai phong": "mien_bac", "quang ninh": "mien_bac", "lao cai": "mien_bac",
    "thai nguyen": "mien_bac", "bac giang": "mien_bac", "thanh hoa": "mien_bac",
    "nghe an": "mien_bac", "ha tinh": "mien_bac",
    "can tho": "mien_nam_xa", "an giang": "mien_nam_xa", "kien giang": "mien_nam_xa",
    "ca mau": "mien_nam_xa", "soc trang": "mien_nam_xa", "dong thap": "mien_nam_xa",
    "vung tau": "mien_nam_xa", "ba ria": "mien_nam_xa",
}


def _resolve_zone(address: str) -> str:
    """Đoán zone vận chuyển từ chuỗi địa chỉ. Mặc định 'khac'."""
    a = address.lower().strip()
    for keyword, zone in _PROVINCE_ZONE.items():
        if keyword in a:
            return zone
    return "khac"


def calculate_shipping_fee(
    destination: str,
    order_total: float = 0,
    weight_kg: float = 0,
    express: bool = False,
) -> dict:
    """
    Tính phí vận chuyển.

    Args:
        destination: địa chỉ giao hàng (vd "Quận 1, TP HCM" hoặc "Đà Nẵng")
        order_total: tổng giá trị đơn (VND) - dùng để check miễn ship
        weight_kg: cân nặng gói hàng kg, > 2kg cộng phụ phí 10k/kg
        express: True = hỏa tốc, chỉ áp dụng nội thành HCM/HN

    Returns:
        {fee, zone, eta, free_ship_applied, breakdown}
    """
    zone = _resolve_zone(destination)
    cfg = SHIPPING_TABLE[zone]

    breakdown = []
    fee = cfg["base"]
    breakdown.append(f"Phí cơ bản {zone}: {fee:,} ₫")

    # Phụ phí cân nặng > 2kg
    if weight_kg > 2:
        extra_weight = max(0, weight_kg - 2)
        extra_fee = int(extra_weight * 10000)
        fee += extra_fee
        breakdown.append(f"Phụ phí cân nặng ({weight_kg}kg, thừa {extra_weight}kg): +{extra_fee:,} ₫")

    # Hỏa tốc
    if express:
        if cfg["express_fee"] is None:
            return {
                "ok": False,
                "error": f"Zone {zone} không hỗ trợ hỏa tốc (chỉ có nội thành HCM/HN)",
            }
        fee = cfg["express_fee"]  # ghi đè bằng phí hỏa tốc
        breakdown = [f"Phí hỏa tốc {zone}: {fee:,} ₫"]

    # Miễn ship nếu đơn >= 500k và KHÔNG phải hỏa tốc
    free_ship = False
    if not express and order_total >= FREE_SHIP_THRESHOLD:
        breakdown.append(f"Đơn {order_total:,} ₫ ≥ {FREE_SHIP_THRESHOLD:,} ₫ → MIỄN PHÍ SHIP")
        fee = 0
        free_ship = True

    return {
        "ok": True,
        "fee": fee,
        "zone": zone,
        "eta": cfg["express_eta"] if express else cfg["eta"],
        "express": express,
        "free_ship_applied": free_ship,
        "breakdown": breakdown,
        "order_total": order_total,
        "destination": destination,
    }


def create_full_sale_order(
    customer_name: str,
    customer_phone: str,
    items: list[dict],
    customer_email: str = "",
    customer_address: str = "",
    confirm: bool = False,
) -> dict:
    """
    End-to-end: tìm/tạo khách + tìm sản phẩm theo SKU + tạo đơn + (tùy chọn) xác nhận.

    items = [{"sku": "FSH-TS-001", "qty": 2}, ...]
    Trả về: {order_id, order_name, partner, line_count, amount_total, state, ok}
    """
    odoo = get_odoo()

    # 1) Tìm hoặc tạo khách
    partner = create_or_get_customer(
        name=customer_name,
        phone=customer_phone,
        email=customer_email,
        address=customer_address,
    )

    # 2) Resolve SKU -> product.product variant id
    skus = [it["sku"] for it in items]
    variants = odoo.search_read(
        "product.product", [["default_code", "in", skus]],
        ["id", "default_code", "name", "list_price"], limit=100,
    )
    sku_to_variant = {v["default_code"]: v for v in variants}

    order_lines = []
    missing = []
    for it in items:
        v = sku_to_variant.get(it["sku"])
        if not v:
            missing.append(it["sku"])
            continue
        order_lines.append((0, 0, {
            "product_id": v["id"],
            "product_uom_qty": it.get("qty", 1),
        }))

    if not order_lines:
        return {"ok": False, "error": f"Không tìm thấy SKU: {missing}"}

    # 3) Tạo đơn
    order_id = odoo.create("sale.order", {
        "partner_id": partner["id"],
        "order_line": order_lines,
    })

    # 4) (Tùy chọn) Xác nhận
    if confirm:
        odoo.execute("sale.order", "action_confirm", [[order_id]])

    # 5) Đọc lại để trả thông tin đầy đủ
    rec = odoo.read("sale.order", [order_id],
                    ["name", "state", "amount_total"])[0]

    return {
        "ok": True,
        "order_id": order_id,
        "order_name": rec["name"],
        "state": rec["state"],
        "amount_total": rec["amount_total"],
        "partner": partner,
        "line_count": len(order_lines),
        "missing_skus": missing,
        "url": f"https://shopmypham.odoo.com/odoo/sales/{order_id}",
    }


# ============================================================
# INVENTORY TOOLS - dùng cho Inventory Agent
# ============================================================
@odoo_cached
def low_stock_products(threshold: int = 30, limit: int = 50) -> list[dict]:
    """Sản phẩm có tồn kho <= threshold."""
    odoo = get_odoo()
    return odoo.search_read(
        "product.template", [["qty_available", "<=", threshold]],
        fields=["id", "name", "default_code", "qty_available", "categ_id"],
        limit=limit, order="qty_available asc",
    )


@odoo_cached
def stock_overview() -> dict:
    """Tổng quan tồn kho: tổng sản phẩm, tổng giá trị, số mặt sắp hết."""
    odoo = get_odoo()
    products = odoo.search_read(
        "product.template", [],
        ["qty_available", "standard_price"], limit=1000,
    )
    total_qty = sum(p["qty_available"] for p in products)
    total_value = sum(p["qty_available"] * p["standard_price"] for p in products)
    low = sum(1 for p in products if p["qty_available"] <= 30)
    return {
        "total_products": len(products),
        "total_quantity_on_hand": total_qty,
        "total_inventory_value": round(total_value, 2),
        "low_stock_count": low,
    }


def adjust_stock(product_id: int, new_qty: float, location_id: int | None = None) -> dict:
    """Điều chỉnh tồn kho: tạo stock.quant cho 1 sản phẩm.
    Yêu cầu module 'stock' được cài. location_id mặc định là kho chính."""
    odoo = get_odoo()
    # Lấy product.product (variant) từ template
    variant = odoo.search_read("product.product", [["product_tmpl_id", "=", product_id]], ["id"], limit=1)
    if not variant:
        return {"ok": False, "error": "Không tìm thấy product variant"}
    if location_id is None:
        loc = odoo.search_read("stock.location", [["usage", "=", "internal"]], ["id"], limit=1)
        if not loc:
            return {"ok": False, "error": "Chưa cấu hình stock.location internal"}
        location_id = loc[0]["id"]
    quant_id = odoo.create("stock.quant", {
        "product_id": variant[0]["id"], "location_id": location_id, "inventory_quantity": new_qty,
    })
    odoo.execute("stock.quant", "action_apply_inventory", [[quant_id]])
    return {"ok": True, "product_id": product_id, "new_qty": new_qty}


# ============================================================
# ANALYTICS TOOLS - dùng cho Analytics Agent
# ============================================================
@odoo_cached
def sales_summary_by_category(limit: int = 100) -> list[dict]:
    """Tổng giá trị sản phẩm theo category (list_price * qty_available)."""
    odoo = get_odoo()
    products = odoo.search_read(
        "product.template", [],
        ["categ_id", "list_price", "qty_available", "standard_price"], limit=limit,
    )
    bucket: dict[str, dict] = {}
    for p in products:
        cat = p["categ_id"][1] if p["categ_id"] else "Uncategorized"
        b = bucket.setdefault(cat, {"category": cat, "products": 0, "stock_qty": 0, "stock_value": 0.0, "retail_value": 0.0})
        b["products"] += 1
        b["stock_qty"] += p["qty_available"]
        b["stock_value"] += p["qty_available"] * p["standard_price"]
        b["retail_value"] += p["qty_available"] * p["list_price"]
    return [{**v, "stock_value": round(v["stock_value"], 2), "retail_value": round(v["retail_value"], 2)} for v in bucket.values()]


@odoo_cached
def top_products_by_price(limit: int = 10) -> list[dict]:
    """Top sản phẩm giá bán cao nhất."""
    odoo = get_odoo()
    return odoo.search_read(
        "product.template", [],
        ["name", "default_code", "list_price", "categ_id"],
        limit=limit, order="list_price desc",
    )


@odoo_cached
def revenue_summary(state: str = "sale") -> dict:
    """Tổng doanh thu các đơn ở trạng thái cho trước."""
    odoo = get_odoo()
    orders = odoo.search_read("sale.order", [["state", "=", state]], ["amount_total"], limit=1000)
    return {
        "state": state,
        "order_count": len(orders),
        "total_revenue": round(sum(o["amount_total"] for o in orders), 2),
    }
