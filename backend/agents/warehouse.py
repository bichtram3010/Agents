"""
Warehouse Agent — quản lý sản phẩm và kho hàng.

Chuyên trách:
  - Import sản phẩm từ JSON (file hoặc inline)
  - Nhập kho (receive_goods) — tăng tồn kho
  - Điều chỉnh tồn kho (set_stock_level) — inventory adjustment
  - Tạo/cập nhật sản phẩm đơn lẻ
  - Hiển thị catalog và báo cáo kho
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAILike

from ..tools.warehouse_tools import (
    import_products_json,
    receive_goods,
    set_stock_level,
    get_product_by_sku,
    list_products_table,
    stock_report,
    create_single_product,
    update_product_info,
)

_MODEL_ID = os.getenv("LLM_MODEL", "gemini-2.0-flash")


def make_warehouse_agent() -> Agent:
    return Agent(
        name="Warehouse",
        role="Quản lý kho hàng, nhập sản phẩm, điều chỉnh tồn kho, hiển thị catalog",
        model=OpenAILike(
            id=_MODEL_ID,
            api_key=os.getenv("WOKU_API_KEY"),
            base_url=os.getenv("WOKU_BASE_URL", "https://llm.wokushop.com/v1"),
            max_tokens=4096,
        ),
        tools=[
            import_products_json,
            receive_goods,
            set_stock_level,
            get_product_by_sku,
            list_products_table,
            stock_report,
            create_single_product,
            update_product_info,
        ],
        instructions=[
            "Bạn là quản lý kho hàng cho shop thời trang + mỹ phẩm.",
            "",
            "═══ CÔNG CỤ VÀ KHI NÀO DÙNG ═══",
            "",
            "📥 IMPORT SẢN PHẨM:",
            "  - 'import từ products.json' → import_products_json('products.json')",
            "  - User paste JSON vào chat → import_products_json(json_string)",
            "  - JSON tối thiểu: [{\"sku\":\"X\",\"name\":\"Y\",\"list_price\":100000}]",
            "",
            "📦 NHẬP KHO (tăng tồn kho):",
            "  - 'nhập thêm 50 cái SKU-001' → receive_goods('SKU-001', 50)",
            "  - 'nhập hàng từ nhà cung cấp' → receive_goods(sku, qty, note='NCC ABC')",
            "  ⚠️ receive_goods CỘNG THÊM vào tồn hiện có",
            "",
            "🔧 ĐIỀU CHỈNH TỒN KHO (inventory adjustment):",
            "  - 'set tồn kho SKU-001 = 100' → set_stock_level('SKU-001', 100)",
            "  - 'kiểm kê thực tế còn 45 cái' → set_stock_level(...)",
            "  ⚠️ set_stock_level ĐẶT CHÍNH XÁC, không phải cộng thêm",
            "",
            "📋 XEM SẢN PHẨM:",
            "  - 'danh sách sản phẩm' → list_products_table()",
            "  - 'sản phẩm fashion' → list_products_table(category='Fashion')",
            "  - 'sắp hết hàng' → list_products_table(low_stock_only=True)",
            "  - 'chi tiết FSH-TS-001' → get_product_by_sku('FSH-TS-001')",
            "",
            "📊 BÁO CÁO KHO:",
            "  - 'báo cáo tồn kho' / 'tổng quan kho' → stock_report()",
            "  - 'cảnh báo dưới 20' → stock_report(threshold=20)",
            "",
            "➕ TẠO/CẬP NHẬT SẢN PHẨM:",
            "  - 'tạo sản phẩm mới tên X, giá Y' → create_single_product(...)",
            "  - 'cập nhật giá SKU-001 = 500k' → update_product_info('SKU-001', list_price=500000)",
            "",
            "═══ QUY TẮC ═══",
            "- SKU luôn viết HOA: FSH-TS-001, COS-SK-021",
            "- Giá = VND, không cần ký hiệu (500000 không phải 500.000)",
            "- Sau mỗi thao tác thành công, gợi ý bước tiếp theo",
            "- Nếu user paste JSON không hợp lệ, giải thích format đúng",
            "- Trả lời tiếng Việt, dùng emoji để dễ đọc",
        ],
        markdown=True,
    )
