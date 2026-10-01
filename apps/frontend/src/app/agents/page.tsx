"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, KeyRound, Pencil, Plus, RotateCcw, Search, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AgentDialog } from "@/components/agents/agent-dialog";
import { RunAgentDialog } from "@/components/agents/run-agent-dialog";
import { apiFetch } from "@/lib/api-client";
import { listCredentials, maskApiKey, removeCredential } from "@/lib/agent-credentials";
import {
  AGENT_ROLES,
  fetchAgentModelDefaults,
  FALLBACK_AGENT_MODEL_DEFAULTS,
} from "@/lib/agent-model-defaults";
import type { Agent, AgentModelDefaults, Project } from "@/types/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [defaults, setDefaults] = useState<AgentModelDefaults>(FALLBACK_AGENT_MODEL_DEFAULTS);
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [runningAgent, setRunningAgent] = useState<Agent | null>(null);
  // Bumped whenever the browser vault changes so cards re-read stored keys.
  const [credentialVersion, setCredentialVersion] = useState(0);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [agentData, projectData, modelDefaults] = await Promise.all([
        apiFetch<Agent[]>("/api/v1/agents").catch(() => [] as Agent[]),
        apiFetch<Project[]>("/api/v1/projects").catch(() => [] as Project[]),
        fetchAgentModelDefaults(),
      ]);
      setAgents(agentData || []);
      setProjects(projectData || []);
      setDefaults(modelDefaults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const credentials = useMemo(() => listCredentials(), [credentialVersion]);

  const projectNames = useMemo(() => {
    const map: Record<string, string> = {};
    projects.forEach((project) => {
      map[project.id] = project.name;
    });
    return map;
  }, [projects]);

  const availableRoles = useMemo(() => {
    const roles = new Set<string>(AGENT_ROLES);
    agents.forEach((agent) => roles.add(agent.role));
    return Array.from(roles).sort();
  }, [agents]);

  const filteredAgents = agents.filter((agent) => {
    const matchesSearch =
      agent.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      agent.slug.toLowerCase().includes(searchTerm.toLowerCase()) ||
      agent.model.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRole = !roleFilter || agent.role === roleFilter;
    return matchesSearch && matchesRole;
  });

  const handleSaved = (saved: Agent, created: boolean) => {
    setAgents((prev) =>
      created ? [saved, ...prev] : prev.map((agent) => (agent.id === saved.id ? saved : agent))
    );
    setCredentialVersion((v) => v + 1);
  };

  const handleDeleted = (removed: Agent) => {
    setAgents((prev) => prev.filter((agent) => agent.id !== removed.id));
    setCredentialVersion((v) => v + 1);
  };

  const openCreate = () => {
    setEditingAgent(null);
    setDialogOpen(true);
  };

  const openEdit = (agent: Agent) => {
    setEditingAgent(agent);
    setDialogOpen(true);
  };

  const handleQuickDelete = async (agent: Agent) => {
    if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return;
    try {
      await apiFetch<null>(`/api/v1/agents/${agent.id}`, { method: "DELETE" });
      removeCredential(agent.id);
      handleDeleted(agent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete agent");
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Agents</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Register agents with your own API key and assign them to projects and roles.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={fetchData} className="gap-2">
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <Button onClick={openCreate} className="gap-2">
            <Plus className="w-4 h-4" />
            <span>Add Agent</span>
          </Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
        <div className="relative max-w-md flex-1">
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Filter by name, slug, or model..."
            className="w-full pl-9 pr-4 py-2 text-sm rounded-md border bg-card focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-md border bg-card focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All roles</option>
          {availableRoles.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-52 rounded-xl border bg-card/60 p-6 animate-pulse space-y-4" />
          ))}
        </div>
      ) : error ? (
        <Card>
          <CardContent className="p-8 text-center space-y-3">
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchData}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : filteredAgents.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="p-12 text-center space-y-4">
            <Bot className="w-12 h-12 text-muted-foreground mx-auto" />
            <div>
              <h3 className="text-base font-semibold">No agents found</h3>
              <p className="text-xs text-muted-foreground mt-1">
                {searchTerm || roleFilter
                  ? "No agents match your filters."
                  : "Add your first agent with your own API key."}
              </p>
            </div>
            {!searchTerm && !roleFilter && (
              <Button onClick={openCreate} className="gap-2">
                <Plus className="w-4 h-4" />
                <span>Add Agent</span>
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredAgents.map((agent) => {
            const credential = credentials[agent.id];
            return (
              <Card
                key={agent.id}
                className="hover:shadow-md transition-shadow flex flex-col justify-between"
              >
                <CardHeader className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-lg font-bold leading-tight flex items-center gap-2">
                      <Bot className="w-4 h-4 text-muted-foreground shrink-0" />
                      <span className="truncate">{agent.name}</span>
                    </CardTitle>
                    <Badge variant="outline" className="text-[10px] font-mono shrink-0">
                      {agent.role}
                    </Badge>
                  </div>
                  <CardDescription className="font-mono text-xs text-primary">
                    /{agent.slug}
                  </CardDescription>
                  {agent.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2 pt-1">
                      {agent.description}
                    </p>
                  )}
                </CardHeader>

                <CardContent className="pt-0 space-y-3">
                  <dl className="space-y-1.5 text-[11px]">
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">Model</dt>
                      <dd className="font-mono truncate" title={agent.model}>
                        {agent.model}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">Provider</dt>
                      <dd className="font-mono">{agent.model_provider}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">Project</dt>
                      <dd className="font-mono truncate">
                        {agent.project_id ? projectNames[agent.project_id] ?? "Assigned" : "Org-wide"}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">API Key</dt>
                      <dd
                        className={`flex items-center gap-1.5 font-mono ${
                          credential ? "text-emerald-400" : "text-amber-400"
                        }`}
                      >
                        <KeyRound className="w-3 h-3" />
                        {credential ? maskApiKey(credential.apiKey) : "Not set"}
                      </dd>
                    </div>
                  </dl>

                  <div className="border-t pt-3 flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">
                      Created {new Date(agent.created_at).toLocaleDateString()}
                    </span>
                    <div className="flex items-center gap-1">
                      {defaults.user_supplied_keys_enabled && agent.model_provider === "gemini" && (
                        <Button variant="outline" size="sm" onClick={() => setRunningAgent(agent)} className="gap-1.5 text-xs h-8">
                          <span>Run</span>
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEdit(agent)}
                        className="gap-1.5 text-xs h-8"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleQuickDelete(agent)}
                        aria-label={`Delete ${agent.name}`}
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <AgentDialog
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        projects={projects}
        defaults={defaults}
        agent={editingAgent}
        onSaved={handleSaved}
        onDeleted={handleDeleted}
      />
      <RunAgentDialog agent={runningAgent} project={projects.find((project) => project.id === runningAgent?.project_id)} onClose={() => setRunningAgent(null)} />
    </div>
  );
}
