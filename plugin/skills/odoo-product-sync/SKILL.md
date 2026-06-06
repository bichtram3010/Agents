---
name: odoo-product-sync
description: Bulk import or sync products from products.json into Odoo via the odoo MCP. Use when the user asks to "import products", "sync catalog", "load 30 products", or to refresh the product catalog from the JSON source-of-truth.
---

# Odoo Product Sync

Khi user yêu cầu import / sync sản phẩm từ `backend/data/products.json` vào Odoo, làm theo các bước sau.

## Quy trình

1. **Đọc JSON**: dùng `Read` trên `backend/data/products.json`. File có `categories[]` và `products[]`.
2. **Đảm bảo cây danh mục**: với mỗi category, dùng `mcp__odoo__search_records` trên `product.category` để check tồn tại. Nếu chưa có thì `mcp__odoo__create_record`.
3. **Upsert sản phẩm theo SKU**:
   - Tìm theo `default_code` = sku.
   - Nếu có: `mcp__odoo__update_record` với fields mới.
   - Nếu chưa: `mcp__odoo__create_record` trên `product.template` với:
     ```
     {
       "name": ..., "default_code": ...,
       "list_price": ..., "standard_price": ...,
       "categ_id": <id>, "barcode": ...,
       "description_sale": ..., "type": "consu", "is_storable": true
     }
     ```
4. **Báo cáo kết quả**: tổng số created / updated / failed.

## Lưu ý

- `qty_available` không set trực tiếp trên `product.template`. Muốn set tồn kho phải tạo `stock.quant` rồi gọi `action_apply_inventory` — xem skill `odoo-inventory-adjust`.
- Tiền tệ là VND, không scale.
- Nếu user chỉ định lọc theo `type` (Fashion / Cosmetics), filter trước khi import.

## Script tham chiếu

Đã có sẵn `backend/scripts/import_products.py` làm idempotent — có thể chạy `python -m backend.scripts.import_products` nếu môi trường có Python.
