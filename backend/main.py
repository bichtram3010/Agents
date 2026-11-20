"""
FastAPI server exposing CopilotKit-compatible endpoints.

- POST /api/chat : câu hỏi từ action `ask_agent` của CopilotKit → pipeline
                    LLM cache → keyword pre-router → agent (fallback: supervisor),
                    có session memory theo `session_id`
- GET  /api/health : healthcheck
- GET  /api/products : sample REST mirror of Odoo data (debug)

Thao tác ghi quan trọng (xác nhận đơn, xóa cache) cần header X-API-Key = ADMIN_API_KEY.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env", override=True)

from .tracing import setup_langfuse, get_tracer  # noqa: E402
from .agents.team import get_team, get_agent  # noqa: E402
from .agents.router import pre_route, route_confidence  # noqa: E402
from .memory import get_session, session_stats  # noqa: E402
from .cache import get_llm_cache, should_cache, get_odoo_cache  # noqa: E402
from .tools.odoo_client import get_odoo  # noqa: E402
from .tools.odoo_tools import create_full_sale_order, calculate_shipping_fee  # noqa: E402
from .rag.retriever import semantic_search  # noqa: E402


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    agent: str | None = None
    session_id: str | None = None  # client gửi kèm để nhớ lịch sử


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup Langfuse tracing trước khi khởi động team
    setup_langfuse()
    # Warm up Odoo + team
    try:
        get_odoo().uid  # auth
    except Exception as e:  # pragma: no cover
        print(f"[warn] Odoo not reachable at startup: {e}")
    get_team()
    yield


app = FastAPI(title="Odoo Multi-Agent Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_admin(x_api_key: str | None = Header(default=None)) -> None:
    """Chặn thao tác ghi quan trọng nếu không có đúng header X-API-Key.

    ADMIN_API_KEY chưa đặt → các endpoint admin bị tắt hẳn (403).
    """
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        raise HTTPException(403, "Admin endpoints are disabled: set ADMIN_API_KEY")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Invalid or missing X-API-Key")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": os.getenv("LLM_MODEL", "unknown"),
        "woku_key": "configured" if os.getenv("WOKU_API_KEY") else "MISSING",
    }


@app.get("/api/stats")
def stats():
    """Debug endpoint: cache stats, session stats."""
    return {
        "llm_cache": get_llm_cache().stats(),
        "odoo_cache": get_odoo_cache().stats(),
        "sessions": session_stats(),
    }


@app.get("/api/products")
def products():
    odoo = get_odoo()
    return odoo.search_read(
        "product.template", [],
        ["id", "name", "default_code", "list_price", "categ_id", "qty_available"],
        limit=100, order="id asc",
    )


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(400, "Empty messages")
    last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
    if not last_user:
        raise HTTPException(400, "No user message")

    # Lịch sử hội thoại lấy từ session memory phía server (theo session_id),
    # nên client chỉ cần gửi câu mới nhất.
    run = _run_agent(req.messages, session_id=req.session_id)
    return {
        "role": "assistant",
        "content": run.content,
        "agent_used": run.agent_used,
        "session_id": run.session_id,
    }


# CopilotKit AG-UI compatible endpoint (Server-Sent Events optional)
@app.post("/api/copilotkit")
def copilot(req: ChatRequest):
    """Endpoint dùng cho CopilotKitRuntime với customAdapter pointing here."""
    return chat(req)


# ============================================================
# OpenAI-compatible /v1/chat/completions
# Cho phép CopilotKit's OpenAIAdapter gọi backend như là một LLM provider.
# Bên trong, mỗi request được route qua Agno multi-agent team.
# ============================================================
class OpenAIMessage(BaseModel):
    role: str
    content: str | None = None
    name: str | None = None
    tool_calls: list | None = None
    tool_call_id: str | None = None


class OpenAIChatRequest(BaseModel):
    model: str | None = None
    messages: list[OpenAIMessage]
    stream: bool | None = False
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list | None = None
    tool_choice: object | None = None
    user: str | None = None  # dùng làm session_id


# Agent có câu trả lời chỉ phụ thuộc kiến thức tĩnh (knowledge base, bảng phí ship)
CACHEABLE_AGENTS = frozenset({"consultant", "shipping"})

BUSY_MESSAGE = "Xin lỗi, hệ thống AI đang bận. Bạn thử lại sau ít phút nhé."


def _run_failed(result) -> bool:
    """agno RunOutput.status == ERROR (lỗi provider, rate limit...)."""
    status = getattr(result, "status", None)
    return str(getattr(status, "value", status) or "").upper() == "ERROR"


@dataclass
class AgentRun:
    content: str
    agent_used: str | None
    session_id: str


def _run_agent(messages: list[ChatMessage] | list[OpenAIMessage],
               session_id: str | None = None) -> AgentRun:
    """
    Pipeline tối ưu — giảm LLM calls tối đa (dùng cho cả /api/chat và /v1/chat/completions):

    1. LLM Cache     → 0 LLM calls nếu đã cache
    2. Pre-router    → gọi agent TRỰC TIẾP (bỏ supervisor LLM)
    3. Supervisor    → chỉ fallback khi pre-router không chắc

    Không có session_id → tạo session mới, không dùng chung một session "default"
    (trước đây mọi client không gửi id đều đọc được lịch sử của nhau).
    """
    sid = session_id or uuid.uuid4().hex
    clean = [m for m in messages if m.role in ("user", "assistant", "system") and m.content]
    if not clean:
        return AgentRun("Xin lỗi, tôi không nhận được nội dung.", None, sid)

    last_user = next((m.content for m in reversed(clean) if m.role == "user"), "")

    # ── Session memory ────────────────────────────────────────────────────────
    session = get_session(sid)
    session.add_user(last_user)
    full_prompt = session.build_prompt(last_user)

    # ── Pre-route: direct agent call → bỏ supervisor LLM ─────────────────────
    # last_agent: câu nối tiếp ("cái đó giá bao nhiêu?") ở lại agent của lượt trước.
    agent_name = pre_route(last_user, last_agent=session.last_agent)

    # ── LLM Cache → 0 LLM calls ───────────────────────────────────────────────
    # Chỉ cache agent trả lời từ kiến thức tĩnh. Sales tạo báo giá, ProductStock/
    # Analytics/Comparison đọc số liệu sống: cache sẽ trả "đã tạo báo giá S000x"
    # hay tồn kho cũ cho khách khác. Supervisor (agent chưa biết) cũng không cache.
    cacheable = agent_name in CACHEABLE_AGENTS and should_cache(last_user)
    llm_cache = get_llm_cache()
    if cacheable:
        cached = llm_cache.get(full_prompt)
        if cached:
            print(f"[cache:HIT] {agent_name}")
            session.add_assistant(cached.response, cached.agent_used)
            return AgentRun(cached.response, cached.agent_used, sid)

    t0 = time.time()
    tracer = get_tracer()

    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("session_id", sid)
        span.set_attribute("input", last_user[:500])
        span.set_attribute("model", os.getenv("LLM_MODEL", "unknown"))
        profile = session.profile.summary()
        if profile:
            span.set_attribute("user_profile", profile)

        if agent_name:
            # ✅ Direct call — không qua supervisor, tiết kiệm 1 LLM call
            agent = get_agent(agent_name)
            if agent:
                span.set_attribute("route", f"direct:{agent_name}")
                result = agent.run(full_prompt)
                print(f"[direct:{agent_name}] {int((time.time()-t0)*1000)}ms")
            else:
                # agent_name không hợp lệ → fallback
                agent_name = None

        if not agent_name:
            # ⚠️ Fallback supervisor — tốn thêm 1 LLM call
            span.set_attribute("route", "supervisor")
            result = get_team().run(full_prompt)
            agent_name = getattr(result, "agent_name", "supervisor")
            print(f"[supervisor→{agent_name}] {int((time.time()-t0)*1000)}ms")

        content = result.content if hasattr(result, "content") else str(result)
        # agno tự bắt lỗi provider (vd OpenRouter 429) và trả câu lỗi làm content với
        # status=ERROR: không cache câu đó, không đưa lỗi thô cho khách.
        failed = _run_failed(result)
        if failed:
            print(f"[agent:error] {agent_name}: {str(content)[:200]}")
            span.set_attribute("error", str(content)[:500])
            content = BUSY_MESSAGE
        span.set_attribute("output", content[:500])
        span.set_attribute("agent_used", str(agent_name))

    latency_ms = (time.time() - t0) * 1000

    # ── Update session + cache ────────────────────────────────────────────────
    session.add_assistant(content, agent_name)
    if cacheable and not failed and agent_name in CACHEABLE_AGENTS:
        llm_cache.set(full_prompt, content, agent_used=agent_name, latency_ms=latency_ms)

    return AgentRun(content, agent_name, sid)


def _openai_chunk(model: str, content_delta: str = "", finish: str | None = None) -> str:
    """Tạo 1 chunk SSE đúng format OpenAI streaming."""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": content_delta} if content_delta else {},
            "finish_reason": finish,
        }],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions")
def openai_chat_completions(req: OpenAIChatRequest):
    """
    OpenAI-compatible endpoint - dùng cho CopilotKit OpenAIAdapter.
    Trả streaming nếu stream=true, không thì JSON 1 lần.
    """
    model = req.model or "odoo-multi-agent"

    if req.stream:
        def event_stream():
            try:
                content = _run_agent(req.messages, session_id=req.user).content
            except Exception as e:  # pragma: no cover
                content = f"❌ Lỗi backend: {e}"

            # Stream theo từng chunk nhỏ để UI render từ từ
            chunk_size = 40
            for i in range(0, len(content), chunk_size):
                yield _openai_chunk(model, content[i:i + chunk_size])
            yield _openai_chunk(model, "", finish="stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # Non-streaming response
    content = _run_agent(req.messages, session_id=req.user).content
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/api/cache/clear", dependencies=[Depends(require_admin)])
def cache_clear():
    """Xóa toàn bộ cache (dùng khi cập nhật sản phẩm thủ công)."""
    llm_n = get_llm_cache().clear()
    odoo_n = get_odoo_cache().clear()
    return {"cleared": {"llm": llm_n, "odoo": odoo_n}}


@app.get("/v1/models")
def openai_models():
    """Cho CopilotKit liệt kê model nếu cần."""
    return {
        "object": "list",
        "data": [{"id": "odoo-multi-agent", "object": "model", "owned_by": "agno-team"}],
    }


# ----- RAG endpoints -----
class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filter_type: str = "all"  # "all" | "knowledge" | "product"


@app.post("/api/rag/search")
def rag_search(req: RagSearchRequest):
    """Trực tiếp gọi semantic_search, không qua agent. Dùng để debug RAG."""
    try:
        results = semantic_search(req.query, top_k=req.top_k, filter_type=req.filter_type)
        return {"query": req.query, "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(500, f"RAG search failed: {e}")


# ----- Order creation endpoint -----
class OrderItem(BaseModel):
    sku: str
    qty: int = 1


class CreateOrderRequest(BaseModel):
    customer_name: str
    customer_phone: str
    items: list[OrderItem]
    customer_email: str = ""
    customer_address: str = ""
    # True = xác nhận luôn (state=sale, cần X-API-Key admin), False = báo giá nháp (draft)
    confirm: bool = False


# ----- Shipping endpoint -----
class ShippingRequest(BaseModel):
    destination: str
    order_total: float = 0
    weight_kg: float = 0
    express: bool = False


@app.post("/api/shipping/calculate")
def shipping_calc(req: ShippingRequest):
    """Tính phí ship cho 1 đơn hàng."""
    result = calculate_shipping_fee(
        destination=req.destination,
        order_total=req.order_total,
        weight_kg=req.weight_kg,
        express=req.express,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Unknown error"))
    return result


@app.post("/api/order/create")
def order_create(req: CreateOrderRequest, x_api_key: str | None = Header(default=None)):
    """
    Tạo đơn hàng end-to-end trong Odoo:
    1. Tìm khách theo tên+sđt, nếu chưa có thì tạo mới (res.partner)
    2. Resolve SKU thành product variant
    3. Tạo sale.order với order_line
    4. (Optional, chỉ admin) action_confirm để chuyển sang state=sale

    Không có key admin chỉ tạo được báo giá nháp: khách hàng và chatbot không tự
    xác nhận đơn được, nhân viên xác nhận trong Odoo.
    """
    if req.confirm:
        require_admin(x_api_key)
    try:
        result = create_full_sale_order(
            customer_name=req.customer_name,
            customer_phone=req.customer_phone,
            items=[i.dict() for i in req.items],
            customer_email=req.customer_email,
            customer_address=req.customer_address,
            confirm=req.confirm,
        )
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Create order failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )
