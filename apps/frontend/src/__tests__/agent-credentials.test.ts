import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  clearAllCredentials,
  getCredential,
  hasCredential,
  listCredentials,
  maskApiKey,
  removeCredential,
  saveCredential,
} from "@/lib/agent-credentials";

describe("client-side agent credential vault", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("starts empty", () => {
    expect(listCredentials()).toEqual({});
    expect(hasCredential("agent-1")).toBe(false);
    expect(getCredential("agent-1")).toBeNull();
  });

  it("stores a key per agent id and never calls the network", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    saveCredential({
      agentId: "agent-1",
      provider: "gemini",
      apiKey: "  AIzaSySECRET123  ",
      baseUrl: "https://generativelanguage.googleapis.com/v1beta/",
    });
    saveCredential({
      agentId: "agent-2",
      provider: "gemini",
      apiKey: "AIzaSyOTHER456",
      baseUrl: "https://generativelanguage.googleapis.com/v1beta",
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(listCredentials()).toHaveProperty("agent-1");
    expect(listCredentials()).toHaveProperty("agent-2");

    const stored = getCredential("agent-1");
    expect(stored?.apiKey).toBe("AIzaSySECRET123");
    expect(stored?.provider).toBe("gemini");
    // Trailing slash is normalised away.
    expect(stored?.baseUrl).toBe("https://generativelanguage.googleapis.com/v1beta");
    expect(stored?.updatedAt).toEqual(expect.any(String));
  });

  it("replaces a key without leaving the previous value behind", () => {
    saveCredential({ agentId: "a", provider: "gemini", apiKey: "first", baseUrl: "u" });
    saveCredential({ agentId: "a", provider: "gemini", apiKey: "second", baseUrl: "u" });
    expect(getCredential("a")?.apiKey).toBe("second");
    expect(Object.keys(listCredentials())).toHaveLength(1);
  });

  it("removes a single key and can clear them all", () => {
    saveCredential({ agentId: "a", provider: "gemini", apiKey: "one", baseUrl: "u" });
    saveCredential({ agentId: "b", provider: "gemini", apiKey: "two", baseUrl: "u" });

    removeCredential("a");
    expect(hasCredential("a")).toBe(false);
    expect(hasCredential("b")).toBe(true);

    clearAllCredentials();
    expect(listCredentials()).toEqual({});
  });

  it("ignores unknown removals and corrupt storage", () => {
    expect(() => removeCredential("missing")).not.toThrow();

    localStorage.setItem("agentspace.agent_credentials.v1", "{not json");
    expect(listCredentials()).toEqual({});
  });

  it("masks keys for display", () => {
    expect(maskApiKey("AIzaSyABCDEFGHIJ1234")).toBe("AIza••••••••••1234");
    expect(maskApiKey("short")).toBe("•••••");
    expect(maskApiKey("   ")).toBe("");
  });
});
