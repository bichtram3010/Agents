"""
Multi-Shop Comparison Tools — query 3 shops trong cùng Odoo.

Mỗi shop = 1 warehouse (tồn kho riêng) + 1 pricelist (giá riêng).
Metadata shops được load từ data/shops_meta.json (tạo bởi setup_shops.py).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .odoo_client import get_odoo

META_FILE = Path(__file__).resolve().parents[1] / "data" / "shops_meta.json"

PROVINCE_ZONE = {
    "hcm": "noi_thanh_hcm", "ho chi minh": "noi_thanh_hcm", "sài gòn": "noi_thanh_hcm",
    "ha noi": "noi_thanh_hn", "hà nội": "noi_thanh_hn", "hn": "noi_thanh_hn",
    "da nang": "mien_trung", "đà nẵng": "mien_trung", "huế": "mien_trung",
    "hai phong": "mien_bac", "hải phòng": "mien_bac", "thanh hóa": "mien_bac",
    "can tho": "mien_nam_xa", "cần thơ": "mien_nam_xa", "vũng tàu": "mien_nam_xa",
}


@lru_cache(maxsize=1)
def _load_shops() -> list[dict]:
    if not META_FILE.exists():
        raise RuntimeError(
            "Chưa setup shops. Chạy: python -m backend.scripts.setup_shops"
        )
    return json.loads(META_FILE.read_text(encoding="utf-8"))


def _resolve_zone(address: str) -> str:
    a = address.lower()
    for kw, zone in PROVINCE_ZONE.items():
        if kw in a:
            return zone
    return "khac"


def _calc_ship(shop: dict, zone: str, order_total: float, express: bool = False) -> dict:
    s = shop["shipping"]
    if express:
        fee = s.get("express_fee", 9999999)
        eta = s.get("express_eta", "N/A")
    else:
        fee = s.get(zone, s["khac"])
        eta = s.get("standard_eta", "2-5 ngày")
        if order_total >= s.get("free_ship_threshold", 9999999):
            fee = 0
    return {"fee": fee, "eta": eta, "free_ship": fee == 0}


def _get_product_price(odoo, pricelist_id: int, product_tmpl_id: int,
                       list_price: float) -> float:
    """Lấy giá từ pricelist. Fallback về list_price nếu không có item."""
    items = odoo.search_read(
        "product.pricelist.item",
        [["pricelist_id", "=", pricelist_id],
         ["product_tmpl_id", "=", product_tmpl_id],
         ["compute_price", "=", "fixed"]],
        ["fixed_price"], limit=1,
    )
    if items:
        return float(items[0]["fixed_price"])
    return float(list_price)


def _get_shop_stock(odoo, location_id: int, product_tmpl_id: int) -> float:
    """Lấy tồn kho tại location của shop."""
    if not location_id:
        return 0
    variants = odoo.search_read("product.product",
                                [["product_tmpl_id", "=", product_tmpl_id]],
                                ["id"], limit=1)
    if not variants:
        return 0
    product_id = variants[0]["id"]
    quants = odoo.search_read("stock.quant",
                              [["product_id", "=", product_id],
                               ["location_id", "=", location_id]],
                              ["quantity"], limit=1)
    return float(quants[0]["quantity"]) if quants else 0


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════════════════════════════════════

def compare_product_price(sku: str) -> str:
    """
    So sánh giá 1 sản phẩm giữa 3 shop.

    Args:
        sku: Mã SKU sản phẩm (vd: COS-SK-021, FSH-TS-001)

    Hiển thị: tên shop, giá bán, tồn kho, trạng thái (rẻ nhất/đắt nhất/phá giá).
    """
    odoo = get_odoo()
    shops = _load_shops()

    # Lấy product info
    product = odoo.search_read(
        "product.template", [["default_code", "=", sku.upper()]],
        ["id", "name", "list_price", "standard_price"], limit=1,
    )
    if not product:
        return f"❌ Không tìm thấy sản phẩm SKU: {sku}"

    p = product[0]
    tmpl_id = p["id"]
    standard_price = float(p["standard_price"])
    base_price = float(p["list_price"])

    rows: list[dict] = []
    for shop in shops:
        price = _get_product_price(odoo, shop["pricelist_id"], tmpl_id, base_price)
        stock = _get_shop_stock(odoo, shop.get("location_id"), tmpl_id)

        margin_pct = (price - standard_price) / standard_price * 100 if standard_price else 0
        vs_base_pct = (price - base_price) / base_price * 100 if base_price else 0

        # Phát hiện phá giá
        if price < standard_price:
            status = "🚨 BÁN LỖ"
        elif price < standard_price * 1.10:
            status = "⚠️ Phá giá"
        elif vs_base_pct < -25:
            status = "🔥 Rất rẻ"
        elif vs_base_pct > 15:
            status = "💎 Cao cấp"
        else:
            status = "✅ Bình thường"

        rows.append({
            "shop": shop["name"],
            "price": price,
            "stock": stock,
            "margin_pct": margin_pct,
            "vs_base_pct": vs_base_pct,
            "status": status,
        })

    # Sort theo giá tăng dần
    rows.sort(key=lambda x: x["price"])
    rows[0]["cheapest"] = True

    lines = [
        f"## 🏷️ So sánh giá: **{p['name']}** (`{sku.upper()}`)\n",
        f"_Giá gốc: {base_price:,.0f} ₫ | Giá vốn: {standard_price:,.0f} ₫_\n",
        "| Shop | Giá bán | Tồn kho | So với gốc | Trạng thái |",
        "|------|---------|---------|------------|-----------|",
    ]
    for r in rows:
        vs = f"+{r['vs_base_pct']:.0f}%" if r['vs_base_pct'] >= 0 else f"{r['vs_base_pct']:.0f}%"
        stock_str = f"⚠️ {r['stock']:.0f}" if r["stock"] <= 30 else f"{r['stock']:.0f}"
        crown = " 👑" if r.get("cheapest") else ""
        lines.append(
            f"| **{r['shop']}**{crown} | **{r['price']:,.0f} ₫** | {stock_str} | {vs} | {r['status']} |"
        )

    return "\n".join(lines)


def detect_price_dumping(threshold_margin_pct: float = 15.0) -> str:
    """
    Phát hiện shop đang bán phá giá (margin thấp bất thường).

    Args:
        threshold_margin_pct: Ngưỡng margin tối thiểu (%). Dưới ngưỡng = nghi ngờ phá giá.
                               Mặc định 15% (bán với margin < 15% = phá giá).

    Kiểm tra tất cả sản phẩm có trong pricelist của mỗi shop.
    """
    odoo = get_odoo()
    shops = _load_shops()

    # Lấy tất cả sản phẩm + giá vốn
    products = odoo.search_read(
        "product.template", [["default_code", "!=", False]],
        ["id", "name", "default_code", "list_price", "standard_price"],
        limit=200,
    )
    product_map = {p["id"]: p for p in products}

    dump_findings: list[dict] = []

    for shop in shops:
        # Lấy tất cả pricelist items của shop
        items = odoo.search_read(
            "product.pricelist.item",
            [["pricelist_id", "=", shop["pricelist_id"]],
             ["compute_price", "=", "fixed"],
             ["product_tmpl_id", "!=", False]],
            ["product_tmpl_id", "fixed_price"],
            limit=200,
        )

        for item in items:
            tmpl_id_raw = item["product_tmpl_id"]
            tmpl_id = tmpl_id_raw[0] if isinstance(tmpl_id_raw, list) else tmpl_id_raw
            p = product_map.get(tmpl_id)
            if not p:
                continue

            price = float(item["fixed_price"])
            standard = float(p["standard_price"])
            base = float(p["list_price"])
            if standard <= 0:
                continue

            margin_pct = (price - standard) / standard * 100
            vs_market_pct = (price - base) / base * 100 if base else 0

            severity = None
            if price < standard:
                severity = "🚨 BÁN LỖ"
            elif margin_pct < threshold_margin_pct:
                severity = "⚠️ Phá giá"
            elif vs_market_pct < -30:
                severity = "🔥 Cực rẻ"

            if severity:
                dump_findings.append({
                    "shop": shop["name"],
                    "sku": p["default_code"],
                    "name": p["name"],
                    "price": price,
                    "standard": standard,
                    "base_price": base,
                    "margin_pct": margin_pct,
                    "vs_market_pct": vs_market_pct,
                    "severity": severity,
                })

    if not dump_findings:
        return f"✅ Không phát hiện shop nào bán phá giá (ngưỡng margin {threshold_margin_pct}%)"

    dump_findings.sort(key=lambda x: x["margin_pct"])

    lines = [
        f"## 🔍 Phát hiện Bán Phá Giá\n",
        f"_Ngưỡng margin: < {threshold_margin_pct}% | Tìm thấy {len(dump_findings)} trường hợp_\n",
        "| Shop | SKU | Giá bán | Giá vốn | Margin | So thị trường | Mức độ |",
        "|------|-----|---------|---------|--------|---------------|--------|",
    ]
    for f in dump_findings[:20]:
        vs = f"{f['vs_market_pct']:+.0f}%"
        lines.append(
            f"| **{f['shop']}** | `{f['sku']}` | {f['price']:,.0f} ₫ | "
            f"{f['standard']:,.0f} ₫ | {f['margin_pct']:.0f}% | {vs} | {f['severity']} |"
        )

    # Summary theo shop
    from collections import Counter
    shop_counts = Counter(f["shop"] for f in dump_findings)
    lines.append("\n### Tóm tắt theo shop")
    for shop_name, count in shop_counts.most_common():
        lines.append(f"- **{shop_name}**: {count} sản phẩm phá giá")

    return "\n".join(lines)


def compare_shipping_all_shops(destination: str, order_total: float = 0,
                                express: bool = False) -> str:
    """
    So sánh phí ship từ tất cả 3 shop đến 1 địa chỉ.

    Args:
        destination: Địa chỉ giao hàng (vd: "Quận 1 HCM", "Đà Nẵng", "Hà Nội")
        order_total: Tổng đơn hàng (VND) — dùng để check miễn ship
        express: True = hỏa tốc
    """
    shops = _load_shops()
    zone = _resolve_zone(destination)

    lines = [
        f"## 🚚 So sánh Phí Ship → {destination}\n",
        f"_Zone: `{zone}` | Đơn hàng: {order_total:,.0f} ₫ | "
        f"{'Hỏa tốc 🚀' if express else 'Tiêu chuẩn'}_\n",
        "| Shop | Phí ship | Thời gian | Miễn ship từ | Ghi chú |",
        "|------|---------|-----------|-------------|---------|",
    ]

    results = []
    for shop in shops:
        ship = _calc_ship(shop, zone, order_total, express)
        free_threshold = shop["shipping"].get("free_ship_threshold", 9999999)
        free_str = f"{free_threshold:,.0f} ₫" if free_threshold < 9_000_000 else "Không có"
        note = "🆓 Miễn ship!" if ship["free_ship"] else ""
        results.append((shop, ship, free_str, note))

    results.sort(key=lambda x: x[1]["fee"])
    results[0][1]["cheapest"] = True

    for shop, ship, free_str, note in results:
        crown = " 👑" if ship.get("cheapest") else ""
        fee_str = "**MIỄN PHÍ**" if ship["free_ship"] else f"{ship['fee']:,.0f} ₫"
        lines.append(
            f"| **{shop['name']}**{crown} | {fee_str} | {ship['eta']} | {free_str} | {note} |"
        )

    # Gợi ý
    cheapest_shop = results[0][0]
    lines.append(f"\n💡 **Phí ship rẻ nhất**: {cheapest_shop['name']}")
    if order_total > 0:
        for shop, ship, _, _ in results:
            threshold = shop["shipping"].get("free_ship_threshold", 9999999)
            if threshold < 9_000_000 and order_total < threshold:
                gap = threshold - order_total
                lines.append(
                    f"💡 Mua thêm **{gap:,.0f} ₫** ở {shop['name']} → được miễn ship!"
                )

    return "\n".join(lines)


def find_best_shop(sku: str, qty: int = 1, destination: str = "HCM") -> str:
    """
    Tìm shop tốt nhất để mua 1 sản phẩm (giá + ship + tồn kho + uy tín).

    Args:
        sku: Mã SKU sản phẩm
        qty: Số lượng mua
        destination: Địa chỉ giao hàng
    """
    odoo = get_odoo()
    shops = _load_shops()

    product = odoo.search_read(
        "product.template", [["default_code", "=", sku.upper()]],
        ["id", "name", "list_price", "standard_price"], limit=1,
    )
    if not product:
        return f"❌ Không tìm thấy SKU: {sku}"

    p = product[0]
    tmpl_id = p["id"]
    standard_price = float(p["standard_price"])
    zone = _resolve_zone(destination)

    results = []
    for shop in shops:
        price = _get_product_price(odoo, shop["pricelist_id"], tmpl_id, float(p["list_price"]))
        stock = _get_shop_stock(odoo, shop.get("location_id"), tmpl_id)

        if stock < qty:
            continue  # không đủ hàng

        order_total = price * qty
        ship = _calc_ship(shop, zone, order_total)
        total_cost = order_total + ship["fee"]

        # Score: lower = better
        # 60% giá, 30% ship, 10% rating (trừ đi vì rating cao = tốt)
        score = total_cost * 0.9 - shop["rating"] * 10000

        # Penalty nếu nghi phá giá (không đáng tin)
        margin = (price - standard_price) / standard_price * 100 if standard_price else 100
        if price < standard_price:
            score += 500000  # penalty nặng: bán lỗ = nghi hàng giả
        elif margin < 10:
            score += 200000  # penalty nhẹ: quá rẻ = nghi vấn

        results.append({
            "shop": shop,
            "price": price,
            "stock": stock,
            "ship_fee": ship["fee"],
            "ship_eta": ship["eta"],
            "total": total_cost,
            "margin_pct": margin,
            "score": score,
            "free_ship": ship["free_ship"],
        })

    if not results:
        return f"❌ Không shop nào có đủ {qty} sản phẩm `{sku.upper()}`"

    results.sort(key=lambda x: x["score"])
    best = results[0]

    lines = [
        f"## 🏆 Shop Tốt Nhất cho `{sku.upper()}`\n",
        f"_Sản phẩm: {p['name']} | Số lượng: {qty} | Giao đến: {destination}_\n",
        "| # | Shop | Giá | Ship | Tổng | Tồn kho | Rating | Nhận xét |",
        "|---|------|-----|------|------|---------|--------|----------|",
    ]

    for i, r in enumerate(results, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        ship_str = "**MIỄN**" if r["free_ship"] else f"{r['ship_fee']:,.0f} ₫"
        note = ""
        if r["margin_pct"] < 10:
            note = "⚠️ Giá nghi vấn"
        elif r["margin_pct"] < 0:
            note = "🚨 Bán lỗ!"
        elif i == 1:
            note = "✅ Khuyến nghị"
        lines.append(
            f"| {medal} | **{r['shop']['name']}** | {r['price']:,.0f} ₫ | "
            f"{ship_str} | **{r['total']:,.0f} ₫** | {r['stock']:.0f} | "
            f"⭐ {r['shop']['rating']} | {note} |"
        )

    winner = best["shop"]
    lines.append(f"\n### ✅ Khuyến nghị: **{winner['name']}**")
    lines.append(f"- Tổng chi phí: **{best['total']:,.0f} ₫** "
                 f"(giá {best['price']:,.0f} ₫ + ship {best['ship_fee']:,.0f} ₫)")
    lines.append(f"- Thời gian nhận: {best['ship_eta']}")
    lines.append(f"- Rating: ⭐ {winner['rating']} ({winner.get('reviews', 0):,} đánh giá)")
    if winner.get("tags"):
        lines.append(f"- Đặc điểm: {', '.join(winner['tags'])}")

    return "\n".join(lines)


def market_overview(category: str | None = None) -> str:
    """
    Phân tích tổng quan thị trường: shop nào rẻ nhất / đắt nhất theo danh mục.

    Args:
        category: Lọc theo danh mục (vd: "Skincare", "Fashion"). None = tất cả.
    """
    odoo = get_odoo()
    shops = _load_shops()

    domain = [["default_code", "!=", False]]
    if category:
        domain.append(["categ_id.complete_name", "ilike", category])

    products = odoo.search_read(
        "product.template", domain,
        ["id", "name", "default_code", "list_price", "standard_price", "categ_id"],
        limit=100,
    )

    if not products:
        return "❌ Không tìm thấy sản phẩm."

    shop_stats: dict[str, dict] = {
        s["name"]: {"total": 0, "count": 0, "cheaper": 0, "dearer": 0, "dumping": 0}
        for s in shops
    }

    for p in products:
        tmpl_id = p["id"]
        base = float(p["list_price"])
        standard = float(p["standard_price"])
        prices = []

        for shop in shops:
            price = _get_product_price(odoo, shop["pricelist_id"], tmpl_id, base)
            prices.append((shop["name"], price))
            stat = shop_stats[shop["name"]]
            stat["total"] += price
            stat["count"] += 1
            if standard > 0 and price < standard * 1.1:
                stat["dumping"] += 1

        if len(prices) > 1:
            min_price = min(p[1] for p in prices)
            max_price = max(p[1] for p in prices)
            for name, price in prices:
                if price == min_price:
                    shop_stats[name]["cheaper"] += 1
                if price == max_price:
                    shop_stats[name]["dearer"] += 1

    title = f"## 📊 Phân Tích Thị Trường{' — ' + category if category else ''}\n"
    lines = [
        title,
        f"_Phân tích {len(products)} sản phẩm trên {len(shops)} shop_\n",
        "| Shop | Giá TB | Rẻ nhất | Đắt nhất | Phá giá | Rating |",
        "|------|--------|---------|----------|---------|--------|",
    ]

    shop_list = [(s["name"], shop_stats[s["name"]], s) for s in shops]
    shop_list.sort(key=lambda x: x[1]["total"] / max(x[1]["count"], 1))

    for name, stat, shop in shop_list:
        avg = stat["total"] / max(stat["count"], 1)
        crown = " 👑" if name == shop_list[0][0] else ""
        lines.append(
            f"| **{name}**{crown} | {avg:,.0f} ₫ | {stat['cheaper']} SP | "
            f"{stat['dearer']} SP | ⚠️ {stat['dumping']} SP | ⭐ {shop['rating']} |"
        )

    cheapest_shop = shop_list[0][0]
    lines.append(f"\n💡 **Giá trung bình rẻ nhất**: {cheapest_shop}")
    lines.append(f"💡 **Uy tín nhất** (rating cao): "
                 f"{max(shops, key=lambda s: s['rating'])['name']}")

    return "\n".join(lines)


def list_shop_info() -> str:
    """Hiển thị thông tin tổng quan về 3 shop: rating, tags, chính sách ship."""
    shops = _load_shops()
    lines = ["## 🏪 Thông Tin 3 Shop\n"]
    for shop in shops:
        s = shop["shipping"]
        free_threshold = s.get("free_ship_threshold", 9999999)
        free_str = f"{free_threshold:,.0f} ₫" if free_threshold < 9_000_000 else "Không miễn ship"
        lines += [
            f"### {shop['name']}",
            f"_{shop['description']}_\n",
            f"- ⭐ Rating: **{shop['rating']}** ({shop.get('reviews', 0):,} đánh giá)",
            f"- 🏷️ Tags: {', '.join(shop.get('tags', []))}",
            f"- 🚚 Ship HCM: {s['noi_thanh_hcm']:,} ₫ | Miễn ship từ: {free_str}",
            f"- ⚡ Hỏa tốc: {s.get('express_fee', 'N/A'):,} ₫ ({s.get('express_eta', 'N/A')})\n",
        ]
    return "\n".join(lines)
