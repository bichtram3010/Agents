---
description: Import 30 sản phẩm thời trang + mỹ phẩm từ products.json vào Odoo
---

Đọc file `backend/data/products.json` và import vào Odoo:

1. Tạo các `product.category` cần thiết (Fashion, Cosmetics + 7 sub) nếu chưa có.
2. Với mỗi sản phẩm trong `products[]`, upsert vào `product.template` theo `default_code` (SKU).
3. Báo cáo kết quả: created / updated / failed + thời gian.

Sử dụng skill `odoo-product-sync` để có hướng dẫn chi tiết.
