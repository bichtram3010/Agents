# Odoo Multi-Agent — Fashion & Cosmetics

Hệ thống **multi-agent AI** tích hợp Odoo ERP, hỗ trợ tư vấn bán hàng, quản lý kho, so sánh giá đa shop, phát hiện phá giá — được xây dựng bằng Agno Framework + FastAPI + Next.js + CopilotKit.

---

## Mục lục

1. [Kiến trúc tổng thể](#1-kiến-trúc-tổng-thể)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Các Agent](#3-các-agent)
4. [RAG — Knowledge Base](#4-rag--knowledge-base)
5. [Multi-Shop Intelligence](#5-multi-shop-intelligence)
6. [Session Memory & Caching](#6-session-memory--caching)
7. [Langfuse Tracing](#7-langfuse-tracing)
8. [Scripts Admin](#8-scripts-admin)
9. [Cài đặt & Chạy](#9-cài-đặt--chạy)
10. [Biến môi trường](#10-biến-môi-trường)
11. [API Endpoints](#11-api-endpoints)
12. [Câu hỏi test](#12-câu-hỏi-test)

---

## 1. Kiến trúc tổng thể

```
Browser (Next.js :3000)
        │
        │  POST /api/copilotkit  (CopilotKit 1.8.14 + AnthropicAdapter)
        ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (:8000)                     │
│                                                          │
│  [Keyword Pre-Router] → bỏ qua LLM supervisor nếu rõ    │
│  [Session Memory]     → nhớ lịch sử, profile user       │
│  [LLM Cache]          → tránh gọi LLM lặp cho cùng câu  │
│                                                          │
│  Agno Team (Supervisor — LLM routing)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ Product  │ │  Sales   │ │Inventory │ │ Analytics  │  │
│  │ Manager  │ │  Order   │ │          │ │            │  │
│  ├──────────┤ ├──────────┤ ├──────────┤ ├────────────┤  │
│  │Consultant│ │ Shipping │ │Comparison│ │(Warehouse) │  │
│  │  + RAG   │ │          │ │ Multi-   │ │ admin only │  │
│  └──────────┘ └──────────┘ │  Shop    │ └────────────┘  │
│                             └──────────┘                 │
│                                                          │
│  [Odoo Cache]  → cache XML-RPC calls (TTL per model)     │
│  [Langfuse]    → OpenTelemetry tracing mọi request       │
└──────────────────────┬──────────────────────────────────┘
                       │  XML-RPC
                       ▼
            ┌────────────────────┐
            │  Odoo SaaS 19.3    │
            │  shopmypham1.odoo  │
            │  3 Warehouses      │
            │  3 Pricelists      │
            │  30 sản phẩm       │
            └────────────────────┘
```

**LLM Provider:** woku.shop (`https://llm.wokushop.com`) — OpenAI-compatible + Anthropic native API

**Model mặc định:** `claude-haiku-4-5-20251001` (nhẹ, nhanh, hỗ trợ tool use)

---

## 2. Cấu trúc thư mục

```
odoo-multi-agent/
├── backend/
│   ├── agents/
│   │   ├── team.py              # Supervisor — route request đến agent phù hợp
│   │   ├── router.py            # Keyword pre-router (bỏ qua LLM supervisor nếu rõ intent)
│   │   ├── product_manager.py   # Quản lý sản phẩm, giá, danh mục
│   │   ├── sales_order.py       # Báo giá, đơn hàng, khách hàng
│   │   ├── inventory.py         # Tồn kho, cảnh báo hết hàng
│   │   ├── analytics.py         # Doanh thu, báo cáo, phân tích
│   │   ├── consultant.py        # Tư vấn sản phẩm + RAG knowledge base
│   │   ├── shipping.py          # Tính phí ship, hỏa tốc, miễn ship
│   │   ├── comparison.py        # So sánh giá đa shop, phát hiện phá giá
│   │   └── warehouse.py         # [Admin only] Import, nhập kho, điều chỉnh tồn kho
│   │
│   ├── tools/
│   │   ├── odoo_client.py       # XML-RPC client kết nối Odoo
│   │   ├── odoo_tools.py        # CRUD tools (có Odoo cache decorator)
│   │   ├── warehouse_tools.py   # Tools nhập kho, import JSON, set stock
│   │   └── multi_shop_tools.py  # So sánh giá, phá giá, ship đa shop
│   │
│   ├── rag/
│   │   ├── embeddings.py        # sentence-transformers multilingual (384 dim)
│   │   ├── ingest.py            # Chunk + embed knowledge base vào ChromaDB
│   │   ├── retriever.py         # semantic_search() — top-k chunks
│   │   └── vector_store.py      # ChromaDB collection
│   │
│   ├── memory/
│   │   └── session.py           # Session memory: lịch sử, user profile, SKU đã hỏi
│   │
│   ├── cache/
│   │   ├── llm_cache.py         # LLM response cache (hash-based, TTL 60min)
│   │   └── odoo_cache.py        # Odoo query cache (TTL per model type)
│   │
│   ├── scripts/
│   │   ├── import_products.py   # Import 30 sản phẩm vào Odoo
│   │   ├── fix_stock.py         # Set tồn kho từ products.json
│   │   └── setup_shops.py       # Tạo 3 warehouses + 3 pricelists trong Odoo
│   │
│   ├── data/
│   │   ├── products.json        # 30 sản phẩm (15 thời trang + 15 mỹ phẩm)
│   │   ├── shops_meta.json      # [generated] Metadata 3 shops sau khi setup
│   │   └── knowledge/
│   │       ├── skincare.md      # Kiến thức skincare cho RAG
│   │       ├── fashion.md       # Kiến thức thời trang cho RAG
│   │       └── faq.md           # FAQ shop (chính sách, ship, đổi trả)
│   │
│   ├── main.py                  # FastAPI app — endpoints, middleware
│   ├── tracing.py               # Langfuse OTEL setup
│   ├── requirements.txt
│   ├── .env                     # Secrets (không commit)
│   └── .env.example
│
└── frontend/
    ├── app/
    │   ├── layout.tsx            # CopilotKit provider wrapper
    │   ├── page.tsx              # Dashboard sản phẩm + CopilotPopup
    │   └── api/copilotkit/
    │       └── route.ts          # CopilotKit runtime (AnthropicAdapter → woku shop)
    ├── package.json
    ├── .env.local                # Frontend env (không commit)
    └── .env.example
```

---

## 3. Các Agent

### Supervisor Team
**File:** `backend/agents/team.py`

Nhận request → keyword pre-route → hoặc LLM route → subagent phù hợp.

| Agent | Trách nhiệm | Tools chính |
|-------|------------|-------------|
| **ProductManager** | Xem/tạo/cập nhật sản phẩm, danh mục, giá | `list_products`, `get_product`, `create_product`, `update_product_price` |
| **SalesOrder** | Báo giá, đơn hàng, tìm khách | `list_sale_orders`, `create_quotation`, `confirm_sale_order`, `search_customers` |
| **Inventory** | Tồn kho, cảnh báo hết hàng | `low_stock_products`, `stock_overview`, `adjust_stock` |
| **Analytics** | Doanh thu, báo cáo, top sản phẩm | `revenue_summary`, `sales_summary_by_category`, `top_products_by_price` |
| **Consultant** | Tư vấn theo loại da, scenario, budget | `knowledge_search` (RAG), `product_search` (RAG), `list_products` |
| **Shipping** | Phí ship, ETA, hỏa tốc, miễn ship | `calculate_shipping_fee` |
| **Comparison** | So sánh giá đa shop, phá giá | `compare_product_price`, `detect_price_dumping`, `find_best_shop` |
| **Warehouse** *(admin)* | Import JSON, nhập kho, set stock | `import_products_json`, `receive_goods`, `set_stock_level` |

### Keyword Pre-Router
**File:** `backend/agents/router.py`

Trước khi gọi LLM supervisor, kiểm tra keyword đơn giản để route nhanh:
- Nếu khớp → gợi ý agent trực tiếp (tiết kiệm ~1 LLM call/request)
- Nếu không khớp → để LLM supervisor quyết định

---

## 4. RAG — Knowledge Base

**Stack:** ChromaDB + sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dim)

**Knowledge Base** (`backend/data/knowledge/`):
- `skincare.md` — quy trình chăm da theo loại da, thành phần (Retinol, HA, BHA...), cách dùng
- `fashion.md` — phối đồ theo occasion, tone màu, body type
- `faq.md` — chính sách đổi trả, phí ship, bảo hành, voucher

**Luồng RAG:**
```
User query
    ↓
semantic_search(query, top_k=5)   ← ChromaDB cosine similarity
    ↓
Top-k chunks (knowledge + product catalog)
    ↓
Consultant Agent tổng hợp + trả lời
```

**Build index:**
```bash
python -m backend.rag.ingest
```

**Debug RAG:**
```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "da dầu mụn ẩn", "top_k": 3}'
```

---

## 5. Multi-Shop Intelligence

**3 Shops trong cùng 1 Odoo instance:**

| Shop | Định vị | Warehouse | Pricelist |
|------|---------|-----------|-----------|
| **Shop Trâm** | Chính hãng, uy tín | WH (mặc định) | Giá gốc |
| **Beauty Corner** | Cao cấp, nhập khẩu | WH2 (BC) | +10-20% |
| **Cosmo Hub** | Giá rẻ, flash sale | WH3 (CH) | -15% avg, một số phá giá |

**Setup shops:**
```bash
python -m backend.scripts.setup_shops
```
Script tự động tạo: 2 warehouse mới (BC, CH) + 3 pricelist + set giá + set tồn kho riêng cho từng shop.

**Tính năng Comparison Agent:**

| Tính năng | Tool | Ví dụ câu hỏi |
|-----------|------|---------------|
| So sánh giá 1 SKU | `compare_product_price` | "Giá kem chống nắng ở 3 shop" |
| Phát hiện phá giá | `detect_price_dumping` | "Shop nào đang bán phá giá?" |
| So sánh phí ship | `compare_shipping_all_shops` | "Phí ship về Đà Nẵng từ mỗi shop" |
| Tìm shop tốt nhất | `find_best_shop` | "Mua son lì ở đâu tốt nhất?" |
| Tổng quan thị trường | `market_overview` | "Phân tích giá skincare 3 shop" |
| Thông tin shop | `list_shop_info` | "Các shop có chính sách gì?" |

**Logic phát hiện phá giá:**
```
price < standard_price           → 🚨 BÁN LỖ (bán dưới giá vốn)
margin < 15%                     → ⚠️  Phá giá (margin quá thấp)
price < market_avg * 70%         → 🔥  Cực rẻ (nghi ngờ)
```

---

## 6. Session Memory & Caching

### Session Memory (`backend/memory/session.py`)
- **TTL:** 30 phút không hoạt động
- **Lưu trữ:** lịch sử hội thoại (10 turns), user profile, SKU đã đề cập
- **Auto-extract profile:** nhận diện loại da, ngân sách, scenario từ text user

```python
# Ví dụ auto-extract
"da mình bị dầu, ngân sách 500k"
→ profile.skin_type = "dầu"
→ profile.budget = 500_000
```

### LLM Cache (`backend/cache/llm_cache.py`)
- **TTL:** 60 phút
- **Max:** 500 entries
- **Skip cache:** các query liên quan tạo đơn, tồn kho realtime
- **Hash:** MD5 của `normalized(query + context)`

### Odoo Cache (`backend/cache/odoo_cache.py`)
- **Decorator `@odoo_cached`** bọc ngoài tool functions
- **Auto-invalidate** khi có write operation (tạo/sửa sản phẩm, đơn hàng)

| Loại data | TTL |
|-----------|-----|
| `list_products` | 5 phút |
| `list_categories` | 30 phút |
| `stock_overview` | 2 phút |
| `revenue_summary` | 1 phút |

**Xem stats:**
```bash
curl http://localhost:8000/api/stats
# → {llm_cache: {hits, misses, hit_rate}, odoo_cache: {...}, sessions: {...}}
```

**Xóa cache:**
```bash
curl -X POST http://localhost:8000/api/cache/clear
```

---

## 7. Langfuse Tracing

Mỗi chat request tạo 1 **trace** trong Langfuse với:
- `input` — câu hỏi user
- `output` — câu trả lời agent
- `agent_used` — agent nào xử lý
- `user_profile` — profile đã trích xuất
- `session_id` — session của user
- `latency_ms` — thời gian xử lý

**Setup:**
1. Đăng ký tại https://cloud.langfuse.com (free)
2. Tạo project → lấy Public Key + Secret Key
3. Điền vào `backend/.env`

```env
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 8. Scripts Admin

> Các script này dùng cho admin, **không phải khách hàng**.

```bash
# Import 30 sản phẩm + tồn kho vào Odoo
python -m backend.scripts.import_products

# Fix tồn kho (nếu bị reset về 0)
python -m backend.scripts.fix_stock

# Setup 3 shops (tạo warehouse + pricelist + giá riêng)
python -m backend.scripts.setup_shops

# Build RAG index (ChromaDB)
python -m backend.rag.ingest
```

**Warehouse Agent** (admin CLI — không nằm trong chatbot khách hàng):
```python
from backend.agents.warehouse import make_warehouse_agent
agent = make_warehouse_agent()
agent.print_response("Nhập thêm 50 cái FSH-TS-001")
agent.print_response("Danh sách sản phẩm skincare")
agent.print_response("Báo cáo tồn kho")
```

---

## 9. Cài đặt & Chạy

### Yêu cầu
- Python 3.11+
- Node.js 18+
- Odoo SaaS account (bật tính năng **Pricelists** trong Settings)

### Bước 1 — Backend

```powershell
cd odoo-multi-agent

# Tạo virtual env
cd backend
python -m venv .venv
cd ..

# Kích hoạt (Windows)
backend\.venv\Scripts\activate

# Cài packages
pip install -r backend\requirements.txt

# Tạo .env từ template
copy backend\.env.example backend\.env
# Điền các giá trị vào backend\.env
```

### Bước 2 — Khởi động Backend

```powershell
# Set env cho phiên hiện tại (Windows)
$env:WOKU_API_KEY = "sk-xxx"

# Chạy từ thư mục GỐC (bắt buộc — relative imports)
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Kiểm tra:
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/stats
```

### Bước 3 — Import dữ liệu (lần đầu)

```powershell
# Import sản phẩm
backend\.venv\Scripts\python.exe -m backend.scripts.import_products

# Fix tồn kho
backend\.venv\Scripts\python.exe -m backend.scripts.fix_stock

# Setup 3 shops (cần Odoo bật Pricelists)
backend\.venv\Scripts\python.exe -m backend.scripts.setup_shops

# Build RAG index
backend\.venv\Scripts\python.exe -m backend.rag.ingest
```

### Bước 4 — Frontend

```powershell
cd frontend

# Tạo .env.local
copy .env.example .env.local
# Điền WOKU_API_KEY, LLM_MODEL, BACKEND_URL

# Cài packages
npm install

# Chạy dev
npm run dev
```

Truy cập: **http://localhost:3000**

---

## 10. Biến môi trường

### `backend/.env`

```env
# LLM Provider — woku.shop (OpenAI-compatible + Anthropic native)
WOKU_API_KEY=sk-xxx
WOKU_BASE_URL=https://llm.wokushop.com/v1
LLM_MODEL=claude-haiku-4-5-20251001

# Odoo SaaS connection
ODOO_URL=https://shopmypham1.odoo.com
ODOO_DB=shopmypham1
ODOO_USERNAME=your-email@gmail.com
ODOO_PASSWORD=your-password

# FastAPI
APP_HOST=0.0.0.0
APP_PORT=8000
CORS_ORIGIN=http://localhost:3000

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

### `frontend/.env.local`

```env
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

# woku.shop — Anthropic native API (cho CopilotKit AnthropicAdapter)
WOKU_API_KEY=sk-xxx
WOKU_BASE_URL=https://llm.wokushop.com
LLM_MODEL=claude-haiku-4-5-20251001
```

### Models đang hoạt động trên woku.shop (2026-06)

| Model | Tốc độ | Dùng cho |
|-------|--------|---------|
| `claude-haiku-4-5-20251001` | ⚡ Nhanh | Chat, tư vấn hàng ngày |
| `gemini-2.5-flash` | ⚡ Nhanh | Thay thế nếu Haiku down |
| `deepseek-chat` | 🔄 Vừa | Phân tích dữ liệu |
| `gpt-4o-mini` | ⚡ Nhanh | Fallback |

---

## 11. API Endpoints

### Chat & CopilotKit
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/chat` | Chat đơn giản (non-streaming) |
| POST | `/v1/chat/completions` | OpenAI-compatible (streaming) |
| POST | `/api/copilotkit` | CopilotKit runtime |

### Products & Data
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/products` | Danh sách sản phẩm từ Odoo |
| GET | `/api/health` | Health check + model info |
| GET | `/api/stats` | Cache stats, session stats |
| POST | `/api/cache/clear` | Xóa toàn bộ cache |

### RAG
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/rag/search` | Semantic search knowledge base |

### Orders & Shipping
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/order/create` | Tạo đơn hàng trong Odoo |
| POST | `/api/shipping/calculate` | Tính phí ship |

---

## 12. Câu hỏi test

### Tư vấn sản phẩm (Consultant + RAG)
```
Da mình hay bóng nhờn, lỗ chân lông to — dùng gì?
Sắp đi quân sự 2 tuần, tư vấn kem chống nắng cho sinh viên
Outfit phỏng vấn cho nữ 22 tuổi, tone trầm
Da mụn ẩn, ngân sách 1 triệu, routine buổi sáng
```

### Sản phẩm & Kho (ProductManager + Inventory)
```
Liệt kê tất cả sản phẩm skincare dưới 500k
SKU nào tồn kho dưới 30?
Top 5 sản phẩm giá cao nhất
```

### Đơn hàng & Sales
```
Tạo báo giá cho khách Nguyễn Văn A, SĐT 0901234567, 2 áo thun FSH-TS-001
Doanh thu các đơn đã xác nhận
Tìm khách hàng tên Trâm
```

### Phí ship
```
Phí ship về Đà Nẵng đơn 300k
Hỏa tốc về Quận 1 HCM giá bao nhiêu?
Mua 600k có miễn ship không?
```

### So sánh đa shop (Comparison)
```
So sánh giá kem chống nắng COS-SK-021 giữa các shop
Shop nào đang bán phá giá?
Phí ship về Hà Nội từ 3 shop, đơn 400k
Mua son lì ở đâu tốt nhất, giao về HCM?
Tổng quan thị trường skincare — shop nào giá tốt nhất?
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11, FastAPI, Agno 2.6.9 |
| **LLM** | woku.shop (Claude Haiku / Gemini Flash) |
| **Agent Framework** | Agno Team + 7 Subagents |
| **RAG** | ChromaDB + sentence-transformers (MiniLM-L12-v2) |
| **ERP** | Odoo SaaS 19.3 (XML-RPC) |
| **Memory** | In-memory SessionStore (TTL 30min) |
| **Cache** | In-memory LLM Cache + Odoo Query Cache |
| **Tracing** | Langfuse 4.7.1 + OpenTelemetry |
| **Frontend** | Next.js 15, CopilotKit 1.8.14, TailwindCSS |
| **LLM Adapter** | AnthropicAdapter (woku native Anthropic API) |

---

## License

MIT
