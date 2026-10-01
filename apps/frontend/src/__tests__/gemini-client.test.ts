import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  GEMINI_DEFAULT_BASE_URL,
  generateContent,
  streamGenerateContent,
  verifyApiKey,
} from "@/lib/gemini-client";

const BASE = "https://generativelanguage.googleapis.com/v1beta";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function sseResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      lines.forEach((line) => controller.enqueue(encoder.encode(`${line}\n`)));
      controller.close();
    },
  });
  return { ok: true, status: 200, body } as unknown as Response;
}

function textPayload(text: string) {
  return {
    candidates: [{ content: { parts: [{ text }] } }],
    usageMetadata: { promptTokenCount: 11, candidatesTokenCount: 7, totalTokenCount: 18 },
    modelVersion: "gemini-2.5-flash",
  };
}

describe("client-side Gemini gateway", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls generateContent with the browser-held key and parses the reply", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(textPayload("Hello there")));
    vi.stubGlobal("fetch", fetchMock);

    const result = await generateContent({
      apiKey: "AIzaSyUSERKEY",
      model: "gemini-2.5-flash",
      systemPrompt: "You are a reviewer.",
      prompt: "Review this diff.",
    });

    expect(result.text).toBe("Hello there");
    expect(result.model).toBe("gemini-2.5-flash");
    expect(result.totalTokens).toBe(18);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE}/models/gemini-2.5-flash:generateContent`);
    expect((init.headers as Record<string, string>)["x-goog-api-key"]).toBe("AIzaSyUSERKEY");

    const payload = JSON.parse(init.body as string);
    expect(payload.systemInstruction.parts[0].text).toBe("You are a reviewer.");
    expect(payload.contents[0].parts[0].text).toBe("Review this diff.");
  });

  it("refuses to call out when no key is attached", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateContent({ apiKey: "   ", model: "gemini-2.5-flash", prompt: "hi" })
    ).rejects.toThrow(/No API key/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces the provider's error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { message: "API key not valid" } }, 400)
      )
    );

    await expect(
      generateContent({ apiKey: "bad", model: "gemini-2.5-flash", prompt: "hi" })
    ).rejects.toThrow("API key not valid");
  });

  it("streams SSE text deltas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          `data: ${JSON.stringify(textPayload("Hel"))}`,
          `data: ${JSON.stringify(textPayload("lo"))}`,
          "data: [DONE]",
        ])
      )
    );

    const chunks: string[] = [];
    for await (const chunk of streamGenerateContent({
      apiKey: "key",
      model: "gemini-2.5-flash",
      prompt: "hi",
    })) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual(["Hel", "lo"]);
  });

  it("verifies a key against the models endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ models: [{ name: "models/gemini-2.5-flash" }, { name: "models/text-embedding" }] })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await verifyApiKey("AIzaSyGOOD");

    expect(result.ok).toBe(true);
    expect(result.models).toEqual(["gemini-2.5-flash"]);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/models?pageSize=100`);
  });

  it("flags an invalid key without throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ error: {} }, 401)));

    const result = await verifyApiKey("AIzaSyBAD");

    expect(result.ok).toBe(false);
    expect(result.message).toBe("Invalid API key.");
    expect(result.models).toEqual([]);
  });

  it("handles network failure and empty input", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(verifyApiKey("AIzaSyGOOD")).resolves.toMatchObject({ ok: false });

    await expect(verifyApiKey("")).resolves.toEqual({
      ok: false,
      message: "Enter an API key first.",
      models: [],
    });
  });

  it("exposes the free tier defaults", () => {
    expect(GEMINI_DEFAULT_BASE_URL).toBe(
      "https://generativelanguage.googleapis.com/v1beta"
    );
  });
});
