"""
Langfuse tracing setup cho Agno multi-agent backend.
Dùng OpenTelemetry (OTEL) để capture toàn bộ agent runs, LLM calls, tool calls.
"""
from __future__ import annotations

import os
import base64
import logging

logger = logging.getLogger(__name__)

_initialized = False


def setup_langfuse() -> bool:
    """
    Khởi tạo Langfuse OTEL tracing.
    Trả về True nếu thành công, False nếu thiếu key.
    """
    global _initialized
    if _initialized:
        return True

    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # Skip nếu chưa có key thật
    if not pk or pk.startswith("pk-lf-...") or not sk or sk.startswith("sk-lf-..."):
        print("[tracing] ⚠️  Langfuse keys chưa được cấu hình — bỏ qua tracing.")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        # Langfuse OTLP endpoint + Basic Auth
        auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        exporter = OTLPSpanExporter(
            endpoint=f"{host.rstrip('/')}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {auth}"},
        )

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        print(f"[tracing] ✅ Langfuse OTEL initialized → {host}")
        _initialized = True
        return True

    except Exception as e:
        print(f"[tracing] ❌ Langfuse setup failed: {e}")
        return False


def get_tracer(name: str = "odoo-multi-agent"):
    """Lấy OTEL tracer để tạo spans thủ công."""
    from opentelemetry import trace
    return trace.get_tracer(name)
