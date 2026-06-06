---
name: odoo-inventory-report
description: Generate a low-stock report and inventory health dashboard from Odoo. Use when the user asks "tồn kho", "hàng sắp hết", "stock report", or wants a dashboard of inventory value.
---

# Odoo Inventory Report

## Báo cáo low-stock

1. `mcp__odoo__search_records` trên `product.template` với domain `[["qty_available","<=",30]]`.
2. Lấy `id, name, default_code, qty_available, categ_id, standard_price`.
3. Phân loại:
   - **Nguy** (qty <= 10): cần nhập ngay
   - **Thấp** (10 < qty <= 30): nhập trong 7 ngày
4. Tính giá trị tồn kho thiếu hụt: `(30 - qty) * standard_price` để gợi ý ngân sách restock.

## Dashboard tổng quan

```
Tổng SKU      : N
Tổng tồn      : N pcs
Giá trị kho   : N ₫ (theo standard_price)
Giá retail    : N ₫ (theo list_price)
Low / Critical: N / N
```

## Format output (markdown)

| SKU | Tên | Tồn kho | Mức |
|-----|-----|---------|-----|
| ... | ... | 5       | 🔴 Nguy |
| ... | ... | 25      | 🟡 Thấp |
