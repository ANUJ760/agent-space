/**
 * Client-side Gemini gateway.
 *
 * Mirrors the server-side `agents/model_gateway.py` abstraction, but runs in the
 * browser so that agents can call Google Gemini with the user's own API key
 * without the key ever passing through the Agent Space backend.
 */

export const GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";

/** Free-tier models selectable without a paid plan. */
export const GEMINI_FREE_TIER_MODELS = [
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
  "gemini-3.5-flash",
  "gemini-3.5-flash-lite",
] as const;

export interface GeminiGenerateOptions {
  apiKey: string;
  model: string;
  baseUrl?: string;
  systemPrompt?: string | null;
  prompt: string;
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
}

export interface GeminiResponse {
  text: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export class GeminiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "GeminiError";
    this.status = status;
  }
}

function endpoint(baseUrl: string, model: string, action: string): string {
  const root = (baseUrl || GEMINI_DEFAULT_BASE_URL).replace(/\/+$/, "");
  return `${root}/models/${encodeURIComponent(model)}:${action}`;
}

function extractText(data: Record<string, unknown>): string {
  const candidates = (data.candidates ?? []) as Array<Record<string, unknown>>;
  const first = candidates[0];
  if (!first) return "";
  const content = first.content as Record<string, unknown> | undefined;
  const parts = (content?.parts ?? []) as Array<Record<string, unknown>>;
  return parts
    .map((part) => (typeof part.text === "string" ? part.text : ""))
    .join("")
    .trim();
}

function extractUsage(data: Record<string, unknown>): Pick<
  GeminiResponse,
  "promptTokens" | "completionTokens" | "totalTokens"
> {
  const usage = (data.usageMetadata ?? {}) as Record<string, unknown>;
  const promptTokens = Number(usage.promptTokenCount ?? 0);
  const completionTokens = Number(usage.candidatesTokenCount ?? 0);
  const totalTokens = Number(usage.totalTokenCount ?? promptTokens + completionTokens);
  return { promptTokens, completionTokens, totalTokens };
}

async function toGeminiError(res: Response): Promise<GeminiError> {
  let detail = `Gemini request failed (${res.status})`;
  try {
    const body = (await res.json()) as { error?: { message?: string } };
    if (body?.error?.message) detail = body.error.message;
  } catch {
    // Non-JSON error body — keep the generic message.
  }
  return new GeminiError(detail, res.status);
}

/** Non-streaming completion. */
export async function generateContent(
  options: GeminiGenerateOptions
): Promise<GeminiResponse> {
  const {
    apiKey,
    model,
    baseUrl = GEMINI_DEFAULT_BASE_URL,
    systemPrompt,
    prompt,
    temperature = 0.2,
    maxTokens = 4096,
    signal,
  } = options;

  if (!apiKey.trim()) {
    throw new GeminiError("No API key attached to this agent.");
  }

  const generationConfig: Record<string, unknown> = {
    temperature,
    maxOutputTokens: maxTokens,
  };
  const body: Record<string, unknown> = { contents: [{ role: "user", parts: [{ text: prompt }] }] };
  if (systemPrompt) {
    body.systemInstruction = { parts: [{ text: systemPrompt }] };
  }
  body.generationConfig = generationConfig;

  const res = await fetch(endpoint(baseUrl, model, "generateContent"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey.trim(),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) throw await toGeminiError(res);

  const data = (await res.json()) as Record<string, unknown>;
  return {
    text: extractText(data),
    model: (data.modelVersion as string) || model,
    ...extractUsage(data),
  };
}

/** Streaming completion; yields plain text deltas. */
export async function* streamGenerateContent(
  options: GeminiGenerateOptions
): AsyncGenerator<string, void, unknown> {
  const {
    apiKey,
    model,
    baseUrl = GEMINI_DEFAULT_BASE_URL,
    systemPrompt,
    prompt,
    temperature = 0.2,
    maxTokens = 4096,
    signal,
  } = options;

  if (!apiKey.trim()) {
    throw new GeminiError("No API key attached to this agent.");
  }

  const body: Record<string, unknown> = {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: { temperature, maxOutputTokens: maxTokens },
  };
  if (systemPrompt) {
    body.systemInstruction = { parts: [{ text: systemPrompt }] };
  }

  const res = await fetch(endpoint(baseUrl, model, "streamGenerateContent") + "?alt=sse", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey.trim(),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) throw await toGeminiError(res);
  if (!res.body) throw new GeminiError("Gemini returned an empty stream.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const payload = trimmed.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          const delta = extractText(JSON.parse(payload) as Record<string, unknown>);
          if (delta) yield delta;
        } catch {
          // Skip partial/invalid frames rather than aborting the stream.
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export interface KeyVerification {
  ok: boolean;
  message: string;
  models: string[];
}

/**
 * Verifies a user-supplied API key by listing the models it can reach.
 * Powers the "Verify key" affordance in the Add Agent form.
 */
export async function verifyApiKey(
  apiKey: string,
  baseUrl: string = GEMINI_DEFAULT_BASE_URL
): Promise<KeyVerification> {
  if (!apiKey.trim()) {
    return { ok: false, message: "Enter an API key first.", models: [] };
  }

  const root = baseUrl.replace(/\/+$/, "");
  try {
    const res = await fetch(`${root}/models?pageSize=100`, {
      headers: { "x-goog-api-key": apiKey.trim() },
    });

    if (!res.ok) {
      const error = await toGeminiError(res);
      if (res.status === 400 || res.status === 401 || res.status === 403) {
        return { ok: false, message: "Invalid API key.", models: [] };
      }
      return { ok: false, message: error.message, models: [] };
    }

    const data = (await res.json()) as { models?: Array<{ name?: string }> };
    const models = (data.models ?? [])
      .map((entry) => (entry.name ?? "").replace(/^models\//, ""))
      .filter((name) => name.startsWith("gemini"))
      .sort();

    return {
      ok: true,
      message: `Key accepted — ${models.length} model${models.length === 1 ? "" : "s"} available.`,
      models,
    };
  } catch {
    return {
      ok: false,
      message: "Could not reach Gemini. Check your network or connection.",
      models: [],
    };
  }
}
