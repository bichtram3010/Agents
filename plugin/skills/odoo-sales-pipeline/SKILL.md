---
name: odoo-sales-pipeline
description: Create and manage Odoo sale orders end-to-end. Use when the user wants to create a quotation, confirm an order, look up sales pipeline, or check sales by state.
---

# Odoo Sales Pipeline

## Tạo báo giá (quotation)

1. **Khách hàng**: `mcp__odoo__search_records` trên `res.partner` với domain `[["name","ilike",X]]` hoặc `[["email","ilike",X]]`. Nếu không thấy, tạo mới qua `res.partner` create.
2. **Sản phẩm**: `mcp__odoo__search_records` trên `product.template` lấy `id`, `name`, `list_price`.
3. **Tạo `sale.order`**:
   ```json
   {
     "partner_id": <int>,
     "order_line": [[0,0,{"product_id": <id>, "product_uom_qty": <qty>}], ...]
   }
   ```

## Xác nhận đơn

- Phải có sự đồng ý rõ ràng của user trước khi gọi `action_confirm` (vì không hoàn tác được).
- Sau confirm, state chuyển `draft` -> `sale`.

## Báo cáo pipeline

Group by `state`:

| state  | Tiếng Việt    |
|--------|---------------|
| draft  | Nháp          |
| sent   | Đã gửi        |
| sale   | Đã xác nhận   |
| done   | Hoàn thành    |
| cancel | Hủy           |

Dùng `mcp__odoo__aggregate_records` trên `sale.order` group by `state`, sum `amount_total`.
