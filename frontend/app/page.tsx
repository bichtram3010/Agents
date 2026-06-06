"use client";

import { useEffect, useState } from "react";
import { CopilotPopup } from "@copilotkit/react-ui";
import { useCopilotReadable, useCopilotAction } from "@copilotkit/react-core";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type Product = {
  id: number;
  name: string;
  default_code: string;
  list_price: number;
  qty_available: number;
  categ_id: [number, string];
};

export default function Home() {
  const [products, setProducts] = useState<Product[]>([]);
  const [allProducts, setAllProducts] = useState<Product[]>([]);

  useEffect(() => {
    fetch(`${BACKEND}/api/products`)
      .then((r) => r.json())
      .then((data) => { setProducts(data); setAllProducts(data); })
      .catch(() => {});
  }, []);

  // Share product list — Claude biết ngay 30 sản phẩm, không cần gọi backend cho câu hỏi đơn giản
  useCopilotReadable({
    description: "Danh sách sản phẩm thời trang + mỹ phẩm đang hiển thị (từ Odoo).",
    value: products.map((p) => ({
      sku: p.default_code,
      name: p.name,
      price: p.list_price,
      stock: p.qty_available,
      category: p.categ_id?.[1],
    })),
  });

  // ── UI Actions (điều khiển dashboard trực tiếp, không qua backend) ──────────

  useCopilotAction({
    name: "filter_products",
    description: "Lọc danh sách sản phẩm trên màn hình theo từ khóa hoặc category",
    parameters: [{ name: "keyword", type: "string", description: "Từ khóa (tên, SKU, category)" }],
    handler: async ({ keyword }: { keyword: string }) => {
      const k = keyword.toLowerCase();
      const filtered = allProducts.filter(
        (p) => p.name.toLowerCase().includes(k) || (p.default_code || "").toLowerCase().includes(k)
          || (p.categ_id?.[1] || "").toLowerCase().includes(k),
      );
      setProducts(filtered);
      return `Đã lọc: ${filtered.length} sản phẩm khớp "${keyword}".`;
    },
  });

  useCopilotAction({
    name: "reset_products",
    description: "Hiển thị lại toàn bộ sản phẩm (bỏ filter)",
    parameters: [],
    handler: async () => {
      setProducts(allProducts);
      return `Đã hiển thị lại ${allProducts.length} sản phẩm.`;
    },
  });

  // ── Backend Actions (gọi Agno multi-agent) ───────────────────────────────────

  useCopilotAction({
    name: "ask_agent",
    description: [
      "Hỏi Agno multi-agent backend — dùng cho MỌI câu hỏi cần dữ liệu hoặc phân tích:",
      "tư vấn skincare/fashion, tồn kho, đơn hàng, doanh thu, phí ship, so sánh shop, phát hiện phá giá.",
      "KHÔNG dùng cho filter/reset dashboard — dùng filter_products/reset_products cho việc đó.",
    ].join(" "),
    parameters: [{ name: "question", type: "string", description: "Câu hỏi đầy đủ" }],
    handler: async ({ question }: { question: string }) => {
      const res = await fetch(`${BACKEND}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: question }] }),
      });
      const data = await res.json();
      return data.content || "Không có phản hồi.";
    },
  });

  useCopilotAction({
    name: "create_order",
    description: "Tạo đơn hàng trong Odoo. Phải có đủ: tên khách + SĐT + sản phẩm (SKU:qty).",
    parameters: [
      { name: "customer_name", type: "string", description: "Họ tên đầy đủ", required: true },
      { name: "customer_phone", type: "string", description: "SĐT (0901234567)", required: true },
      { name: "items_csv", type: "string", description: "SKU:qty cách phẩy. Vd: FSH-TS-001:2,COS-MK-022:1", required: true },
      { name: "confirm", type: "boolean", description: "true = xác nhận đơn, false = báo giá nháp", required: false },
    ],
    handler: async (args: { customer_name: string; customer_phone: string; items_csv: string; confirm?: boolean }) => {
      const placeholders = ["tên khách", "khách hàng", "customer", "test", "demo", "abc", "xyz", "n/a"];
      if (!args.customer_name || placeholders.some(p => args.customer_name.toLowerCase().includes(p))) {
        return "❌ Cần tên thật của khách hàng. Hỏi lại user: 'Tên đầy đủ của khách là gì?'";
      }
      const phone = args.customer_phone.replace(/[\s\-.]/g, "");
      if (!/^(0|\+84)\d{9,10}$/.test(phone)) {
        return `❌ SĐT '${args.customer_phone}' không hợp lệ. Hỏi lại user.`;
      }
      const items = args.items_csv.split(",").map(s => s.trim()).filter(Boolean).map(pair => {
        const [sku, qty] = pair.split(":").map(x => x.trim());
        return { sku, qty: parseInt(qty || "1", 10) };
      }).filter(it => it.sku && /^(FSH|COS)-/.test(it.sku));
      if (!items.length) return `❌ Không có SKU hợp lệ trong '${args.items_csv}'.`;

      const res = await fetch(`${BACKEND}/api/order/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_name: args.customer_name, customer_phone: phone, items, confirm: args.confirm || false }),
      });
      const data = await res.json();
      if (!res.ok) return `❌ ${data.detail || JSON.stringify(data)}`;
      return `✅ Đơn ${data.order_name} — ${data.partner.name} — ${(data.amount_total || 0).toLocaleString("vi-VN")} ₫ — ${data.state === "sale" ? "Đã xác nhận" : "Báo giá nháp"}\n${data.url}`;
    },
  });

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <main className="max-w-[1400px] mx-auto p-4">
      <header className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Odoo Multi-Agent — Fashion & Cosmetics</h1>
        <span className="text-sm text-neutral-500">{products.length} sản phẩm</span>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
        {products.map((p) => (
          <article key={p.id} className="border rounded-xl p-3 bg-white shadow-sm hover:shadow-md transition-shadow">
            <div className="text-xs text-neutral-400">{p.default_code}</div>
            <div className="font-semibold mt-1 line-clamp-2 min-h-[2.5rem]">{p.name}</div>
            <div className="text-xs text-neutral-400 mt-1">{p.categ_id?.[1]}</div>
            <div className="flex items-center justify-between mt-3">
              <span className="font-semibold text-rose-600">{p.list_price.toLocaleString("vi-VN")} ₫</span>
              <span className={`text-xs ${p.qty_available <= 30 ? "text-orange-500 font-bold" : "text-neutral-500"}`}>
                Kho: {p.qty_available}
              </span>
            </div>
          </article>
        ))}
        {products.length === 0 && (
          <div className="col-span-full text-neutral-400 text-sm border-2 border-dashed rounded-xl p-8 text-center">
            Chưa có dữ liệu. Backend: {BACKEND}
          </div>
        )}
      </div>

      <CopilotPopup
        defaultOpen={false}
        clickOutsideToClose={false}
        instructions={`Bạn là trợ lý bán hàng shop thời trang + mỹ phẩm. Quy tắc đơn giản:

1. Câu hỏi cần data/phân tích (tư vấn da, sản phẩm, tồn kho, ship, so sánh shop, đơn hàng) → gọi ask_agent(question)
2. Muốn lọc dashboard → filter_products(keyword)
3. Muốn xem lại hết → reset_products()
4. Tạo đơn hàng → hỏi tên + SĐT + sản phẩm trước, rồi create_order()

Lưu ý tạo đơn: KHÔNG tự đặt tên placeholder. Hỏi thật từ user.
Trả lời tiếng Việt, ngắn gọn.`}
        labels={{
          title: "Trợ lý Odoo",
          initial: "Xin chào! Mình có thể:\n• Tư vấn skincare / phối đồ\n• Xem sản phẩm, tồn kho\n• So sánh giá 3 shop\n• Tính phí ship, tạo đơn hàng\n\nBạn cần gì?",
          placeholder: "Nhập câu hỏi...",
        }}
      />
    </main>
  );
}
