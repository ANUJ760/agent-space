/**
 * Client-side vault for user-supplied agent API keys ("bring your own key").
 *
 * These credentials are deliberately kept entirely in the browser: they are
 * written to user-scoped `localStorage`, read straight from there when an agent needs to
 * talk to its provider, and never included in any request to the Agent Space
 * backend. Losing this data (clearing site data, another browser) means
 * the user re-attaches their key — no server state is lost.
 *
 * The backend stores the *agent definition* (name, role, model, project
 * assignment); the key lives only here.
 */

const STORAGE_KEY = "agentspace.agent_credentials.v2";

export type AgentProvider = "gemini" | "openai" | "anthropic" | "openai-compatible";

export interface AgentCredential {
  agentId: string;
  provider: AgentProvider;
  /** Raw secret. Read with {@link getCredential} only at call time. */
  apiKey: string;
  baseUrl: string;
  updatedAt: string;
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof localStorage !== "undefined";
}

function storageKey(): string {
  if (!isBrowser()) return STORAGE_KEY;
  try {
    const user = JSON.parse(localStorage.getItem("agentspace_user") || "null") as
      | { id?: string; organizationId?: string }
      | null;
    return `${STORAGE_KEY}.${user?.organizationId || "anonymous"}.${user?.id || "anonymous"}`;
  } catch {
    return `${STORAGE_KEY}.anonymous.anonymous`;
  }
}

function readAll(): Record<string, AgentCredential> {
  if (!isBrowser()) return {};
  try {
    const raw = localStorage.getItem(storageKey());
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => {
        const item = value as Partial<AgentCredential> | null;
        return item && typeof item.apiKey === "string" && typeof item.baseUrl === "string";
      })
    ) as Record<string, AgentCredential>;
  } catch {
    return {};
  }
}

function writeAll(entries: Record<string, AgentCredential>): void {
  if (!isBrowser()) throw new Error("API keys can only be stored in a browser.");
    if (Object.keys(entries).length === 0) {
      localStorage.removeItem(storageKey());
      return;
    }
    localStorage.setItem(storageKey(), JSON.stringify(entries));
}

/** Returns every stored credential keyed by agent id. */
export function listCredentials(): Record<string, AgentCredential> {
  return readAll();
}

/** Returns the credential for an agent, or `null` if no key is attached. */
export function getCredential(agentId: string): AgentCredential | null {
  return readAll()[agentId] ?? null;
}

/** True when the user has attached an API key to this agent. */
export function hasCredential(agentId: string): boolean {
  return getCredential(agentId) !== null;
}

/** Fail before registering an agent if this browser cannot persist its key. */
export function ensureCredentialStorageAvailable(): void {
  if (!isBrowser()) throw new Error("API keys can only be stored in a browser.");
  const probe = `${storageKey()}.probe`;
  try {
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
  } catch {
    throw new Error("Browser storage is unavailable. Enable site storage to save your API key.");
  }
}

/** Attaches (or replaces) the API key for an agent. */
export function saveCredential(input: {
  agentId: string;
  provider: AgentProvider;
  apiKey: string;
  baseUrl: string;
}): AgentCredential {
  const entries = readAll();
  const credential: AgentCredential = {
    agentId: input.agentId,
    provider: input.provider,
    apiKey: input.apiKey.trim(),
    baseUrl: input.baseUrl.replace(/\/+$/, ""),
    updatedAt: new Date().toISOString(),
  };
  entries[input.agentId] = credential;
  writeAll(entries);
  return credential;
}

/** Detaches the API key from an agent. */
export function removeCredential(agentId: string): void {
  const entries = readAll();
  if (!(agentId in entries)) return;
  delete entries[agentId];
  writeAll(entries);
}

/** Removes every stored key for the current signed-in user. */
export function clearAllCredentials(): void {
  writeAll({});
}

/**
 * Renders a key for display without exposing it, e.g. `AIza••••••••••3f7c`.
 * Short keys are fully masked.
 */
export function maskApiKey(apiKey: string): string {
  const trimmed = apiKey.trim();
  if (trimmed.length === 0) return "";
  if (trimmed.length <= 10) return "•".repeat(trimmed.length);
  return `${trimmed.slice(0, 4)}${"•".repeat(10)}${trimmed.slice(-4)}`;
}
