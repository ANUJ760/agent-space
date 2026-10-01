import { generateContent, GEMINI_DEFAULT_BASE_URL } from "@/lib/gemini-client";
import type { AgentProvider } from "@/lib/agent-credentials";

export const PROVIDER_URLS: Record<AgentProvider, string> = {
  gemini: GEMINI_DEFAULT_BASE_URL,
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  "openai-compatible": "",
};

export const PROVIDER_MODELS: Record<AgentProvider, string[]> = {
  gemini: ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash"],
  openai: ["gpt-5.4-mini", "gpt-5.3-codex", "gpt-5-mini"],
  anthropic: ["claude-sonnet-5-5", "claude-haiku-4-5-20251001"],
  "openai-compatible": [],
};

export async function generateAgentText(input: {
  provider: AgentProvider;
  apiKey: string;
  model: string;
  systemPrompt?: string | null;
  prompt: string;
  maxTokens?: number;
  baseUrl?: string;
}): Promise<string> {
  const { provider, apiKey, model, systemPrompt, prompt, maxTokens = 8192, baseUrl } = input;
  if (provider === "gemini") {
    return (await generateContent({ apiKey, model, systemPrompt, prompt, maxTokens })).text;
  }
  const url = provider === "openai" ? `${PROVIDER_URLS.openai}/responses` : provider === "anthropic" ? `${PROVIDER_URLS.anthropic}/messages` : `${(baseUrl || "").replace(/\/+$/, "")}/chat/completions`;
  if (provider === "openai-compatible" && !/^https:\/\//.test(baseUrl || "") && !/^http:\/\/localhost(?::\d+)?\//.test(baseUrl || "")) throw new Error("Use an HTTPS API base URL for compatible providers.");
  const response = await fetch(url, {
    method: "POST",
    headers: provider === "openai" || provider === "openai-compatible"
      ? { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` }
      : { "Content-Type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" },
    body: JSON.stringify(provider === "openai"
      ? { model, instructions: systemPrompt || undefined, input: prompt, max_output_tokens: maxTokens }
      : provider === "anthropic" ? { model, system: systemPrompt || undefined, max_tokens: maxTokens, messages: [{ role: "user", content: prompt }] }
      : { model, max_tokens: maxTokens, messages: [{ role: "system", content: systemPrompt || "You are a helpful software agent." }, { role: "user", content: prompt }] }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message || `${provider} request failed (${response.status})`);
  if (provider === "openai") return (data.output || []).flatMap((item: { content?: Array<{ text?: string }> }) => item.content || []).map((part: { text?: string }) => part.text || "").join("").trim();
  if (provider === "openai-compatible") return String(data.choices?.[0]?.message?.content || "").trim();
  return (data.content || []).filter((part: { type?: string }) => part.type === "text").map((part: { text?: string }) => part.text || "").join("").trim();
}
