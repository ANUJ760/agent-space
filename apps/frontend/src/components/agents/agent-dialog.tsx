"use client";

import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import { Bot, Eye, EyeOff, KeyRound, Loader2, Plus, ShieldCheck, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api-client";
import {
  getCredential,
  ensureCredentialStorageAvailable,
  maskApiKey,
  removeCredential,
  saveCredential,
  type AgentProvider,
} from "@/lib/agent-credentials";
import { AGENT_ROLES } from "@/lib/agent-model-defaults";
import { GEMINI_DEFAULT_BASE_URL, verifyApiKey } from "@/lib/gemini-client";
import { PROVIDER_MODELS, PROVIDER_URLS } from "@/lib/agent-provider";
import type { Agent, AgentModelDefaults, Project } from "@/types/api";

const INPUT_CLASS =
  "w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring";
const LABEL_CLASS = "text-xs font-semibold text-muted-foreground uppercase tracking-wider";

type VerifyState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "ok"; message: string }
  | { status: "error"; message: string };

interface AgentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projects: Project[];
  defaults: AgentModelDefaults;
  /** When editing, the agent being updated. Omit to create a new agent. */
  agent?: Agent | null;
  /** Pre-selects a project, e.g. when launched from a project workspace. */
  presetProjectId?: string | null;
  onSaved: (agent: Agent, created: boolean) => void;
  onDeleted?: (agent: Agent) => void;
}

export function AgentDialog({
  isOpen,
  onClose,
  projects,
  defaults,
  agent = null,
  presetProjectId = null,
  onSaved,
  onDeleted,
}: AgentDialogProps) {
  const modelListId = useId();
  const isEditing = Boolean(agent);
  const keysEnabled = defaults.user_supplied_keys_enabled;

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [role, setRole] = useState<string>(AGENT_ROLES[0]);
  const [model, setModel] = useState(defaults.model);
  const [provider, setProvider] = useState<AgentProvider | "default">("default");
  const [projectId, setProjectId] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [storedKeyMask, setStoredKeyMask] = useState<string | null>(null);
  const [removeStoredKey, setRemoveStoredKey] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [verify, setVerify] = useState<VerifyState>({ status: "idle" });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the form whenever the dialog is opened.
  useEffect(() => {
    if (!isOpen) return;

    const stored = agent ? getCredential(agent.id) : null;

    setName(agent?.name ?? "");
    setSlug(agent?.slug ?? "");
    setSlugTouched(Boolean(agent));
    setDescription(agent?.description ?? "");
    setRole(agent?.role ?? AGENT_ROLES[0]);
    setProvider(agent?.model_provider === "openai" || agent?.model_provider === "anthropic" || agent?.model_provider === "gemini" || agent?.model_provider === "openai-compatible" ? agent.model_provider : defaults.default_agent_available ? "default" : "gemini");
    setModel(agent?.model_provider === "default" ? defaults.model : agent?.model ?? defaults.model);
    setProjectId(agent?.project_id ?? presetProjectId ?? "");
    setSystemPrompt(agent?.system_prompt ?? "");
    setCapabilities((agent?.capabilities ?? []).join(", "));
    setApiKey("");
    setBaseUrl(stored?.baseUrl || "");
    setStoredKeyMask(stored ? maskApiKey(stored.apiKey) : null);
    setRemoveStoredKey(false);
    setShowKey(false);
    setVerify({ status: "idle" });
    setError(null);
  }, [isOpen, agent, defaults.model, presetProjectId]);

  const modelOptions = useMemo(() => {
    const options = provider === "default" ? [defaults.model] : PROVIDER_MODELS[provider];
    if (model && !options.includes(model)) options.unshift(model);
    return options;
  }, [defaults.model, model, provider]);

  const roleOptions = useMemo(() => {
    const options: string[] = [...AGENT_ROLES];
    if (role && !options.includes(role)) options.unshift(role);
    return options;
  }, [role]);

  const handleNameChange = useCallback(
    (value: string) => {
      setName(value);
      if (slugTouched) return;
      setSlug(
        value
          .toLowerCase()
          .trim()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "")
      );
    },
    [slugTouched]
  );

  const handleVerify = async () => {
    if (!apiKey.trim()) {
      setVerify({ status: "error", message: "Enter an API key to verify." });
      return;
    }
    if (provider !== "gemini") return;
    setVerify({ status: "checking" });
    const result = await verifyApiKey(apiKey, defaults.base_url || GEMINI_DEFAULT_BASE_URL);
    setVerify(
      result.ok
        ? { status: "ok", message: result.message }
        : { status: "error", message: result.message }
    );
  };

  const handleRemoveKey = () => {
    setRemoveStoredKey(true);
    setApiKey("");
    setStoredKeyMask(null);
    setVerify({ status: "idle" });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!name.trim() || !slug.trim()) {
      setError("Agent name and slug are required.");
      return;
    }
    if (!model.trim()) { setError("Enter a model ID for this provider."); return; }
    if (provider === "default" && !defaults.default_agent_available) {
      setError("Default agent is unavailable. Ask the developer to set DEFAULT_GEMINI_API_KEY, or select your own provider.");
      return;
    }
    if (provider === "openai-compatible" && !/^https:\/\//.test(baseUrl) && !/^http:\/\/localhost(?::\d+)?\//.test(baseUrl)) {
      setError("Enter an HTTPS API base URL for this provider.");
      return;
    }
    if (provider !== "default" && !keysEnabled) {
      setError("Personal API keys are disabled by the administrator.");
      return;
    }
    if (provider !== "default" && (!isEditing || agent?.model_provider !== provider || removeStoredKey) && !apiKey.trim()) {
      setError("An API key is required so the agent can run from your browser.");
      return;
    }
    if (isEditing && verify.status === "error") {
      setError(verify.message);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    const capabilitiesList = capabilities
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean);

    try {
      if (provider !== "default" && apiKey.trim()) ensureCredentialStorageAvailable();
      let saved: Agent;
      let created = false;

      if (agent) {
        saved = await apiFetch<Agent>(`/api/v1/agents/${agent.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: name.trim(),
            description: description.trim(),
            role,
            model: provider === "default" ? defaults.model : model.trim(),
            model_provider: provider,
            capabilities: capabilitiesList,
            system_prompt: systemPrompt.trim(),
            project_id: projectId || null,
          }),
        });
      } else {
        saved = await apiFetch<Agent>("/api/v1/agents", {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            slug: slug.trim(),
            description: description.trim(),
            role,
            model: provider === "default" ? defaults.model : model.trim(),
            model_provider: provider,
            capabilities: capabilitiesList,
            system_prompt: systemPrompt.trim(),
            project_id: projectId || null,
          }),
        });
        created = true;
      }

      // The key is written to the browser vault only, never to the backend.
      if (removeStoredKey || (agent && agent.model_provider !== provider)) removeCredential(saved.id);
      if (provider !== "default" && apiKey.trim()) {
        saveCredential({
          agentId: saved.id,
          provider,
          apiKey,
          baseUrl: provider === "openai-compatible" ? baseUrl : PROVIDER_URLS[provider],
        });
      }
      if (provider === "default") removeCredential(saved.id);

      onSaved(saved, created);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save agent");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!agent) return;
    setIsDeleting(true);
    setError(null);
    try {
      await apiFetch<null>(`/api/v1/agents/${agent.id}`, { method: "DELETE" });
      removeCredential(agent.id);
      onDeleted?.(agent);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete agent");
    } finally {
      setIsDeleting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="w-full max-w-2xl rounded-xl border bg-card p-6 shadow-xl space-y-5 animate-in fade-in zoom-in-95 duration-150 my-auto">
        <div className="flex items-center justify-between border-b pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
              {isEditing ? <Bot className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                {isEditing ? "Edit Agent" : "Add Agent"}
              </h3>
              <p className="text-xs text-muted-foreground">
                {isEditing
                  ? "Update model, role, project assignment, or your API key"
                  : "Use the default agent or create one with your own provider key"}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-8 w-8 text-muted-foreground"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">
              {error}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className={LABEL_CLASS} htmlFor="agent-name">
                Agent Name *
              </label>
              <input
                id="agent-name"
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="e.g. Refactor Scout"
                required
                className={INPUT_CLASS}
              />
            </div>

            <div className="space-y-1.5">
              <label className={LABEL_CLASS} htmlFor="agent-slug">
                URL Slug *
              </label>
              <input
                id="agent-slug"
                type="text"
                value={slug}
                disabled={isEditing}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(e.target.value);
                }}
                placeholder="refactor-scout"
                required
                className={`${INPUT_CLASS} font-mono disabled:opacity-60`}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="agent-description">
              Description
            </label>
            <textarea
              id="agent-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this agent is responsible for..."
              rows={2}
              className={INPUT_CLASS}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className={LABEL_CLASS} htmlFor="agent-role">
                Role
              </label>
              <select
                id="agent-role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className={INPUT_CLASS}
              >
                {roleOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className={LABEL_CLASS} htmlFor="agent-project">
                Project Assignment
              </label>
              <select
                id="agent-project"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className={INPUT_CLASS}
              >
                <option value="">Organization-wide (all projects)</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className={LABEL_CLASS} htmlFor="agent-provider">
                Provider
              </label>
              <select id="agent-provider" value={provider} onChange={(e) => {
                const next = e.target.value as AgentProvider | "default";
                setProvider(next);
                setModel(next === "default" ? defaults.model : PROVIDER_MODELS[next][0] || "");
                setApiKey("");
                setBaseUrl(next === "openai-compatible" ? (agent && agent.model_provider === next ? getCredential(agent.id)?.baseUrl || "" : "") : PROVIDER_URLS[next as AgentProvider] || "");
                setStoredKeyMask(next === agent?.model_provider ? (agent ? (getCredential(agent.id) ? maskApiKey(getCredential(agent.id)!.apiKey) : null) : null) : null);
                setVerify({ status: "idle" });
              }} className={INPUT_CLASS}>
                <option value="default">Default Gemini agent {defaults.default_agent_available ? "" : "(not configured)"}</option>
                <option value="gemini">My Gemini key</option>
                <option value="openai">My OpenAI key</option>
                <option value="anthropic">My Anthropic key</option>
                <option value="openai-compatible">Other OpenAI-compatible API</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className={LABEL_CLASS} htmlFor="agent-model">
                Model
              </label>
              <input
                id="agent-model"
                type="text"
                list={modelListId}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={provider === "default"}
                required
                className={`${INPUT_CLASS} font-mono`}
              />
              <datalist id={modelListId}>
                {modelOptions.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>
          </div>

          {provider === "openai-compatible" && <div className="space-y-1.5"><label className={LABEL_CLASS} htmlFor="agent-base-url">API base URL</label><input id="agent-base-url" type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://provider.example/v1" className={INPUT_CLASS} required /><p className="text-[11px] text-muted-foreground">The browser sends your key directly to this endpoint. It must allow browser requests.</p></div>}

          {provider === "default" && <p className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">The default agent uses {defaults.model} with the developer&apos;s Gemini key. No personal API key is needed.</p>}

          {/* Bring-your-own-key: the secret lives in this browser only. */}
          {provider !== "default" && <div className="rounded-md border border-border/70 bg-muted/20 p-4 space-y-3">
            <div className="flex items-start gap-2">
              <KeyRound className="w-4 h-4 text-primary mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-xs font-semibold text-foreground">
                  <label htmlFor="agent-api-key">
                    Your {provider} API Key {!isEditing && <span className="text-destructive">*</span>}
                  </label>
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Stored in this browser only and used to call {provider} directly. It is never sent
                  to or stored by the Agent Space server.
                </p>
              </div>
              {!keysEnabled && (
                <Badge variant="destructive" className="shrink-0">
                  Disabled by admin
                </Badge>
              )}
            </div>

            {storedKeyMask && !apiKey && (
              <div className="flex items-center justify-between gap-3 rounded-none border border-emerald-500/30 bg-emerald-500/5 px-3 py-2">
                <span className="flex items-center gap-2 font-mono text-[11px] text-emerald-400">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  {storedKeyMask}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleRemoveKey}
                  className="gap-1.5 text-[11px] text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-3 h-3" />
                  Remove
                </Button>
              </div>
            )}

            {keysEnabled && (
              <>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <input
                      id="agent-api-key"
                      type={showKey ? "text" : "password"}
                      value={apiKey}
                      onChange={(e) => {
                        setApiKey(e.target.value);
                        setVerify({ status: "idle" });
                      }}
                      placeholder={storedKeyMask ? "Enter a new key to replace" : "Paste your provider API key"}
                      autoComplete="off"
                      spellCheck={false}
                      className={`${INPUT_CLASS} font-mono pr-10`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((prev) => !prev)}
                      aria-label={showKey ? "Hide API key" : "Show API key"}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {provider === "gemini" && <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleVerify}
                    disabled={verify.status === "checking" || !apiKey.trim()}
                    className="shrink-0 gap-1.5"
                  >
                    {verify.status === "checking" ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <ShieldCheck className="w-3.5 h-3.5" />
                    )}
                    <span>Verify</span>
                  </Button>}
                </div>

                {provider !== "gemini" && <p className="text-[11px] text-muted-foreground">This key is checked by the provider on the first run.</p>}

                {verify.status === "ok" && (
                  <p className="text-[11px] text-emerald-400">{verify.message}</p>
                )}
                {verify.status === "error" && (
                  <p className="text-[11px] text-destructive">{verify.message}</p>
                )}
              </>
            )}
          </div>}

          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="agent-capabilities">
              Capabilities
            </label>
            <input
              id="agent-capabilities"
              type="text"
              value={capabilities}
              onChange={(e) => setCapabilities(e.target.value)}
              placeholder="code_writing, git_ops, testing"
              className={`${INPUT_CLASS} font-mono`}
            />
          </div>

          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="agent-system-prompt">
              System Prompt
            </label>
            <textarea
              id="agent-system-prompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Instructions prepended to every request this agent sends to Gemini..."
              rows={3}
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex items-center justify-between gap-3 pt-2">
            {isEditing && onDeleted ? (
              <Button
                type="button"
                variant="ghost"
                onClick={handleDelete}
                disabled={isDeleting || isSubmitting}
                className="gap-2 text-destructive hover:text-destructive"
              >
                <Trash2 className="w-4 h-4" />
                <span>{isDeleting ? "Deleting..." : "Delete Agent"}</span>
              </Button>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-3">
              <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting} className="gap-2">
                {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{isSubmitting ? "Saving..." : isEditing ? "Save Changes" : "Create Agent"}</span>
              </Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
