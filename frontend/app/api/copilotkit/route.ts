/**
 * CopilotKit Runtime — chọn LLM theo biến môi trường (frontend/.env.local):
 *
 *  - Có LLM_BASE_URL → API tương thích OpenAI (OpenRouter, Gemini, Groq, OpenAI...):
 *      LLM_BASE_URL=https://openrouter.ai/api/v1
 *      LLM_API_KEY=sk-or-...
 *      LLM_MODEL=baidu/ernie-5.5-flash-preview:free   (model phải hỗ trợ tool calling)
 *  - Không có → giữ cách cũ: woku.shop qua Anthropic native API (WOKU_API_KEY, WOKU_BASE_URL).
 */
import {
  CopilotRuntime,
  AnthropicAdapter,
  OpenAIAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";
import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MODEL = process.env.LLM_MODEL || "claude-haiku-4-5-20251001";
const OPENAI_COMPAT = Boolean(process.env.LLM_BASE_URL);

const serviceAdapter = OPENAI_COMPAT
  ? new OpenAIAdapter({
      openai: new OpenAI({
        apiKey: process.env.LLM_API_KEY || "missing-key",
        baseURL: process.env.LLM_BASE_URL,
      }),
      model: MODEL,
      // nhiều model miễn phí không gọi song song nhiều tool được
      disableParallelToolCalls: true,
    })
  : new AnthropicAdapter({
      anthropic: new Anthropic({
        apiKey: process.env.WOKU_API_KEY || "missing-key",
        baseURL: process.env.WOKU_BASE_URL || "https://llm.wokushop.com",
      }),
      model: MODEL,
    } as any);

const runtimeInstance = new CopilotRuntime();

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime: runtimeInstance,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};

export async function GET() {
  return new Response(
    JSON.stringify({
      ok: true,
      provider: OPENAI_COMPAT ? "openai-compatible" : "wokushop-anthropic",
      model: MODEL,
    }),
    { headers: { "Content-Type": "application/json" } }
  );
}
