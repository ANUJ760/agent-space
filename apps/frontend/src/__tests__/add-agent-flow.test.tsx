import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import AgentsPage from "@/app/agents/page";
import { apiFetch } from "@/lib/api-client";
import { getCredential, clearAllCredentials } from "@/lib/agent-credentials";
import type { Agent, AgentModelDefaults, Project } from "@/types/api";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api-client", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const DEFAULTS: AgentModelDefaults = {
  provider: "gemini",
  model: "gemini-2.5-flash",
  base_url: "https://generativelanguage.googleapis.com/v1beta",
  user_supplied_keys_enabled: true,
  free_tier_models: ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash"],
};

const PROJECTS: Project[] = [
  {
    id: "proj-1",
    organization_id: "org-1",
    name: "Payments Platform",
    slug: "payments-platform",
    description: null,
    status: "ACTIVE",
    created_by_id: null,
    created_at: "2026-09-30T00:00:00Z",
    updated_at: "2026-09-30T00:00:00Z",
  },
];

const EXISTING_AGENT: Agent = {
  id: "agent-existing",
  organization_id: "org-1",
  project_id: "proj-1",
  name: "Legacy Scout",
  slug: "legacy-scout",
  description: "Already registered",
  role: "REVIEWER",
  model: "claude-3-5-sonnet",
  model_provider: "anthropic",
  status: "ACTIVE",
  capabilities: [],
  created_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  version: 1,
};

const NEW_AGENT: Agent = {
  id: "agent-new",
  organization_id: "org-1",
  project_id: "proj-1",
  name: "Refactor Scout",
  slug: "refactor-scout",
  description: "",
  role: "ARCHITECT",
  model: "gemini-2.5-flash",
  model_provider: "gemini",
  status: "ACTIVE",
  capabilities: ["code_writing"],
  system_prompt: "Be terse.",
  created_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  version: 1,
};

function routeApiFetch(overrides: { create?: Partial<Agent> } = {}) {
  return (endpoint: string, options?: RequestInit) => {
    if (endpoint === "/api/v1/agents/model-defaults") return Promise.resolve(DEFAULTS);
    if (endpoint === "/api/v1/projects") return Promise.resolve(PROJECTS);
    if (endpoint === "/api/v1/agents" && (!options || !options.method)) {
      return Promise.resolve([EXISTING_AGENT]);
    }
    if (endpoint === "/api/v1/agents" && options?.method === "POST") {
      return Promise.resolve({ ...NEW_AGENT, ...overrides.create });
    }
    return Promise.resolve(null);
  };
}

describe("Add Agent (bring your own key)", () => {
  beforeEach(() => {
    localStorage.clear();
    clearAllCredentials();
    mockedApiFetch.mockReset();
    vi.restoreAllMocks();
  });

  it("registers the agent with the developer default model and stores the key client-side", async () => {
    mockedApiFetch.mockImplementation(routeApiFetch() as never);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ models: [{ name: "models/gemini-2.5-flash" }] }),
    } as unknown as Response);

    render(<AgentsPage />);
    await screen.findByText("Legacy Scout");

    fireEvent.click(screen.getAllByRole("button", { name: /add agent/i })[0]);

    fireEvent.change(screen.getByLabelText(/Agent Name/), {
      target: { value: "Refactor Scout" },
    });
    // Slug is derived from the name.
    expect((screen.getByLabelText(/URL Slug/) as HTMLInputElement).value).toBe(
      "refactor-scout"
    );

    // Dev-configured default model / provider are pre-selected.
    expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe(
      "gemini-2.5-flash"
    );
    expect((screen.getByLabelText("Provider") as HTMLInputElement).value).toBe("gemini");

    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "ARCHITECT" } });
    fireEvent.change(screen.getByLabelText("Project Assignment"), {
      target: { value: "proj-1" },
    });
    fireEvent.change(screen.getByLabelText("Capabilities"), {
      target: { value: "code_writing, testing" },
    });
    fireEvent.change(screen.getByLabelText(/Your Gemini API Key/), {
      target: { value: "AIzaSyUSERKEY" },
    });

    // "Verify" validates the key straight from the browser.
    fireEvent.click(screen.getByRole("button", { name: /verify/i }));
    await waitFor(() => expect(screen.getByText(/Key accepted/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));

    await waitFor(() => expect(screen.getByText("Refactor Scout")).toBeInTheDocument());

    const createCall = mockedApiFetch.mock.calls.find(
      ([endpoint, options]) => endpoint === "/api/v1/agents" && (options as RequestInit)?.method === "POST"
    );
    expect(createCall).toBeDefined();

    const body = JSON.parse((createCall?.[1]?.body ?? "{}") as string);
    expect(body).toMatchObject({
      name: "Refactor Scout",
      slug: "refactor-scout",
      role: "ARCHITECT",
      model: "gemini-2.5-flash",
      model_provider: "gemini",
      capabilities: ["code_writing", "testing"],
      project_id: "proj-1",
    });

    // The secret landed in the browser vault — not in the request payload.
    expect(JSON.stringify(body)).not.toContain("AIzaSyUSERKEY");
    expect(getCredential("agent-new")?.apiKey).toBe("AIzaSyUSERKEY");
    expect(getCredential("agent-new")?.provider).toBe("gemini");

    // Only the key-verification request left the browser.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][0]).toBe(
      "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100"
    );
  });

  it("requires an API key before creating an agent", async () => {
    mockedApiFetch.mockImplementation(routeApiFetch() as never);
    render(<AgentsPage />);
    await screen.findByText("Legacy Scout");

    fireEvent.click(screen.getAllByRole("button", { name: /add agent/i })[0]);
    fireEvent.change(screen.getByLabelText(/Agent Name/), {
      target: { value: "Keyless" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));

    expect(
      await screen.findByText(/An API key is required so the agent can run from your browser/i)
    ).toBeInTheDocument();
    expect(
      mockedApiFetch.mock.calls.some(
        ([endpoint, options]) =>
          endpoint === "/api/v1/agents" && (options as RequestInit)?.method === "POST"
      )
    ).toBe(false);
  });

  it("shows agents with no stored key as needing one", async () => {
    mockedApiFetch.mockImplementation(routeApiFetch() as never);
    render(<AgentsPage />);
    await screen.findByText("Legacy Scout");

    expect(screen.getAllByText("Not set").length).toBeGreaterThan(0);
    expect(screen.getByText("anthropic")).toBeInTheDocument();
  });
});
