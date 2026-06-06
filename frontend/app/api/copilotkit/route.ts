/**
 * CopilotKit Runtime - dùng woku shop qua Anthropic native API.
 * Woku shop hỗ trợ Anthropic format tại https://llm.wokushop.com
 */
import {
  CopilotRuntime,
  AnthropicAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import Anthropic from "@anthropic-ai/sdk";
import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Woku shop hỗ trợ Anthropic API format
const anthropic = new Anthropic({
  apiKey: process.env.WOKU_API_KEY || "missing-key",
  baseURL: "https://llm.wokushop.com",
});

const serviceAdapter = new AnthropicAdapter({
  anthropic,
  model: process.env.LLM_MODEL || "claude-haiku-4-5-20251001",
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
      provider: "wokushop-anthropic",
      model: process.env.LLM_MODEL || "claude-haiku-4-5-20251001",
    }),
    { headers: { "Content-Type": "application/json" } }
  );
}
