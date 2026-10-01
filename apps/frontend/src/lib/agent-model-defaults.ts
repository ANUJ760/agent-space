/**
 * Resolves the developer-configured default agent model.
 *
 * The backend owns this value (`DEFAULT_AGENT_MODEL` env var) and advertises it
 * through `GET /api/v1/agents/model-defaults`, so changing the default never
 * requires a frontend rebuild. The literal below is used while the request loads.
 */

import { apiFetch } from "@/lib/api-client";
import { GEMINI_DEFAULT_BASE_URL, GEMINI_FREE_TIER_MODELS } from "@/lib/gemini-client";
import type { AgentModelDefaults } from "@/types/api";

export const FALLBACK_AGENT_MODEL_DEFAULTS: AgentModelDefaults = {
  provider: "gemini",
  model: GEMINI_FREE_TIER_MODELS[0],
  base_url: GEMINI_DEFAULT_BASE_URL,
  user_supplied_keys_enabled: true,
  free_tier_models: [...GEMINI_FREE_TIER_MODELS],
  default_agent_available: false,
};

let cached: AgentModelDefaults | null = null;

export async function fetchAgentModelDefaults(
  force = false
): Promise<AgentModelDefaults> {
  if (cached && !force) return cached;
  cached = await apiFetch<AgentModelDefaults>("/api/v1/agents/model-defaults");
  return cached;
}

/** Canonical roles offered when assigning an agent to a project. */
export const AGENT_ROLES = [
  "DEVELOPER",
  "ARCHITECT",
  "TESTER",
  "REVIEWER",
  "RESEARCHER",
  "COORDINATOR",
] as const;
