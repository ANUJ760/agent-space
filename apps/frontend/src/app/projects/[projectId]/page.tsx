"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FolderKanban,
  Users,
  Bot,
  Activity,
  ArrowLeft,
  CheckSquare,
  Clock,
  RotateCcw,
  Shield,
  Layers,
  Sparkles,
  GitBranch,
  CheckCircle2,
  AlertCircle,
  Cpu,
  UserCheck,
  ChevronRight,
  Workflow,
  Code2,
  ExternalLink,
  KeyRound,
  Plus,
} from "lucide-react";
import { AgentDialog } from "@/components/agents/agent-dialog";
import { apiFetch } from "@/lib/api-client";
import { hasCredential } from "@/lib/agent-credentials";
import { subscribeToProjectTasks } from "@/lib/project-events";
import {
  fetchAgentModelDefaults,
  FALLBACK_AGENT_MODEL_DEFAULTS,
} from "@/lib/agent-model-defaults";
import { Project, ProjectMember, Agent, Task, AgentModelDefaults } from "@/types/api";

interface AuditEvent {
  id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export default function ProjectWorkspacePage() {
  const params = useParams();
  const projectId = params?.projectId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);

  // Strictly 3 tabs as requested:
  // 1. "collaborators": Humans and agents working on the project
  // 2. "progress": Middle tab showing ongoing progress with color-coded markers for agents & humans
  // 3. "tasks": Tasks & Kanban deliverables
  const [activeTab, setActiveTab] = useState<"collaborators" | "progress" | "tasks">("progress");

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskFilter, setTaskFilter] = useState<string>("ALL");

  // Agent onboarding: the user attaches their own provider key and picks a role.
  const [agentDialogOpen, setAgentDialogOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [modelDefaults, setModelDefaults] = useState<AgentModelDefaults>(
    FALLBACK_AGENT_MODEL_DEFAULTS
  );
  // Bumped whenever the browser vault changes so rows re-read stored keys.
  const [credentialVersion, setCredentialVersion] = useState(0);

  const fetchProjectDetails = useCallback(async () => {
    if (!projectId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [projData, membersData, agentsData, tasksData, eventsData, defaultsData] =
        await Promise.all([
          apiFetch<Project>(`/api/v1/projects/${projectId}`),
          apiFetch<ProjectMember[]>(`/api/v1/projects/${projectId}/members`).catch(() => []),
          apiFetch<Agent[]>(`/api/v1/projects/${projectId}/agents`).catch(() => []),
          apiFetch<Task[]>(`/api/v1/projects/${projectId}/tasks`).catch(() => []),
          apiFetch<AuditEvent[]>(`/api/v1/projects/${projectId}/audit-events`).catch(() => []),
          fetchAgentModelDefaults(true),
        ]);

      setProject(projData);
      setMembers(membersData || []);
      setAgents(agentsData || []);
      setTasks(tasksData || []);
      setAuditEvents(eventsData || []);
      setModelDefaults(defaultsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project details");
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchProjectDetails();
  }, [fetchProjectDetails]);

  useEffect(() => {
    if (!projectId) return;
    const unsubscribe = subscribeToProjectTasks(
      projectId,
      (updated) => setTasks((current) => current.some((task) => task.id === updated.id)
        ? current.map((task) => task.id === updated.id ? updated : task)
        : [...current, updated]),
      (taskId) => setTasks((current) => current.filter((task) => task.id !== taskId)),
    );
    const timer = window.setInterval(async () => {
      try {
        const [latestTasks, latestEvents] = await Promise.all([
          apiFetch<Task[]>(`/api/v1/projects/${projectId}/tasks`),
          apiFetch<AuditEvent[]>(`/api/v1/projects/${projectId}/audit-events`),
        ]);
        setTasks(latestTasks);
        setAuditEvents(latestEvents);
      } catch { /* Keep showing the last known project state. */ }
    }, 30000);
    return () => { unsubscribe(); window.clearInterval(timer); };
  }, [projectId]);

  const hasAgentKey = useMemo(() => {
    const map: Record<string, boolean> = {};
    agents.forEach((agent) => {
      map[agent.id] = hasCredential(agent.id);
    });
    return map;
  }, [agents, credentialVersion]);

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto space-y-4 animate-pulse">
        <div className="h-9 w-36 bg-muted/60 rounded-none" />
        <div className="h-36 rounded-none border border-border/80 bg-card p-5" />
        <div className="h-96 rounded-none border border-border/80 bg-card p-5" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-7xl mx-auto py-12 text-center space-y-4">
        <div className="w-10 h-10 rounded-full bg-destructive/10 text-destructive border border-destructive/30 flex items-center justify-center mx-auto">
          <FolderKanban className="w-5 h-5" />
        </div>
        <h2 className="text-xl font-bold tracking-tight">Project Not Found</h2>
        <p className="text-xs text-muted-foreground">{error || "The requested project does not exist."}</p>
        <Link href="/projects">
          <Button variant="outline" className="gap-2">
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Projects</span>
          </Button>
        </Link>
      </div>
    );
  }

  // Progress calculations
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter((t) => t.status === "DONE").length;
  const inProgressTasks = tasks.filter((t) => t.status === "IN_PROGRESS" || t.status === "REVIEW").length;
  const progressPercent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
  const agentName = (agentId?: string | null) =>
    agents.find((agent) => agent.id === agentId)?.name || "Unknown agent";
  const humanName = (userId?: string | null) => {
    const user = members.find((member) => member.user_id === userId)?.user;
    return user?.username || user?.email || "Unknown collaborator";
  };

  // Filter tasks for Tab 3
  const filteredTasks = tasks.filter((t) => {
    if (taskFilter === "ALL") return true;
    return t.status === taskFilter;
  });

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      {/* Top action bar & breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href="/projects"
          className="inline-flex items-center gap-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <div className="w-5 h-5 rounded-full border border-border/80 flex items-center justify-center">
            <ArrowLeft className="w-2.5 h-2.5" />
          </div>
          <span>Projects</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-foreground font-semibold">{project.slug}</span>
        </Link>

        <div className="flex items-center gap-2">
          <Link href={`/projects/${project.id}/files`}><Button variant="outline" size="sm" className="gap-1.5 text-xs rounded-none"><Code2 className="w-4 h-4" /> Open files</Button></Link>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchProjectDetails}
            className="gap-1.5 text-xs rounded-none border-border/70"
          >
            <div className="w-4 h-4 rounded-full flex items-center justify-center">
              <RotateCcw className="w-3 h-3" />
            </div>
            <span>Refresh</span>
          </Button>

          <Link href={`/projects/${project.id}/tasks`}>
            <Button size="sm" className="gap-1.5 text-xs rounded-none bg-primary text-primary-foreground">
              <div className="w-4 h-4 rounded-full flex items-center justify-center">
                <CheckSquare className="w-3 h-3" />
              </div>
              <span>Open Kanban Board</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Project Header Box (Sharp, sleek, dark) */}
      <div className="rounded-none border border-border/80 bg-card p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-full border border-primary/50 bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <FolderKanban className="w-5 h-5" />
            </div>
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-foreground">
                  {project.name}
                </h1>
                <Badge variant="outline" className="text-[10px] font-mono border-primary/40 bg-primary/5 text-primary">
                  {project.status}
                </Badge>
              </div>
              <p className="text-xs font-mono text-muted-foreground">
                repository: <span className="text-primary font-semibold">{project.repository_url || "Not connected yet"}</span>
              </p>
            </div>
          </div>

          {/* Quick Metrics Ribbon */}
          <div className="flex items-center gap-5 text-xs border-t md:border-t-0 md:border-l border-border/60 pt-3 md:pt-0 md:pl-5">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 flex items-center justify-center">
                <Users className="w-3 h-3" />
              </div>
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-mono">Humans</div>
                <div className="text-xs font-bold font-mono text-cyan-400">{members.length}</div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full border border-violet-500/40 bg-violet-500/10 text-violet-400 flex items-center justify-center">
                <Bot className="w-3 h-3" />
              </div>
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-mono">Agents</div>
                <div className="text-xs font-bold font-mono text-violet-400">{agents.length + (modelDefaults.default_agent_available ? 1 : 0)}</div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                <CheckSquare className="w-3 h-3" />
              </div>
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-mono">Progress</div>
                <div className="text-xs font-bold font-mono text-emerald-400">{progressPercent}%</div>
              </div>
            </div>
          </div>
        </div>

        {project.description && (
          <p className="text-xs text-muted-foreground pt-2 border-t border-border/60">
            {project.description}
          </p>
        )}
      </div>

      {/* Main 3 Divided Tabs as Requested:
          1. Collaborators (Humans & Agents)
          2. Ongoing Progress (Middle tab with color markers)
          3. Tasks & Deliverables */}
      <div className="grid grid-cols-3 border border-border/80 bg-card p-1 rounded-none text-xs font-medium">
        {/* Tab 1: Users Working on It (Humans + Agents) */}
        <button
          type="button"
          onClick={() => setActiveTab("collaborators")}
          className={`py-2 px-3 rounded-none transition-all flex items-center justify-center gap-2 ${
            activeTab === "collaborators"
              ? "bg-muted text-foreground border-b-2 border-primary font-bold shadow-sm"
              : "text-muted-foreground hover:text-foreground border-b-2 border-transparent"
          }`}
        >
          <div className="w-5 h-5 rounded-full border border-border/80 flex items-center justify-center">
            <Users className="w-2.5 h-2.5" />
          </div>
          <span>1. Collaborators ({members.length + agents.length + (modelDefaults.default_agent_available ? 1 : 0)})</span>
        </button>

        {/* Tab 2: Middle Tab — Ongoing Progress with Color-Coded Markers */}
        <button
          type="button"
          onClick={() => setActiveTab("progress")}
          className={`py-2 px-3 rounded-none transition-all flex items-center justify-center gap-2 ${
            activeTab === "progress"
              ? "bg-muted text-foreground border-b-2 border-primary font-bold shadow-sm"
              : "text-muted-foreground hover:text-foreground border-b-2 border-transparent"
          }`}
        >
          <div className="w-5 h-5 rounded-full border border-border/80 flex items-center justify-center">
            <Activity className="w-2.5 h-2.5 text-primary" />
          </div>
          <span>2. Ongoing Progress ({progressPercent}%)</span>
        </button>

        {/* Tab 3: Tasks & Deliverables */}
        <button
          type="button"
          onClick={() => setActiveTab("tasks")}
          className={`py-2 px-3 rounded-none transition-all flex items-center justify-center gap-2 ${
            activeTab === "tasks"
              ? "bg-muted text-foreground border-b-2 border-primary font-bold shadow-sm"
              : "text-muted-foreground hover:text-foreground border-b-2 border-transparent"
          }`}
        >
          <div className="w-5 h-5 rounded-full border border-border/80 flex items-center justify-center">
            <CheckSquare className="w-2.5 h-2.5" />
          </div>
          <span>3. Tasks & Deliverables ({tasks.length})</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: USERS WORKING ON IT (HUMANS & AGENTS INCLUDED) */}
      {/* ========================================================================= */}
      {activeTab === "collaborators" && (
        <div className="space-y-5 animate-tab-enter">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Human Engineers Panel */}
            <Card className="rounded-none border-border/80">
              <CardHeader className="flex flex-row items-center justify-between pb-3">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full border border-cyan-500/50 bg-cyan-500/10 text-cyan-400 flex items-center justify-center">
                      <Users className="w-3 h-3" />
                    </div>
                    <CardTitle className="text-sm font-bold tracking-tight">Human Engineers</CardTitle>
                  </div>
                  <CardDescription>Verified team members collaborating on this repository</CardDescription>
                </div>
                <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 font-mono text-[10px]">
                  {members.length} Active
                </Badge>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {members.length === 0 ? (
                  <div className="p-6 text-center text-xs text-muted-foreground border border-dashed border-border/60">
                    No human members assigned directly. System admins hold default access.
                  </div>
                ) : (
                  members.map((m) => (
                    <div
                      key={m.id}
                      className="p-3 rounded-none border border-border/70 bg-card/60 flex items-center justify-between gap-3 hover:border-cyan-500/40 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-full border border-cyan-500/60 bg-cyan-500/10 text-cyan-400 font-mono font-bold flex items-center justify-center text-xs shadow-sm">
                          {(m.user?.username || m.user_id.substring(0, 2)).toUpperCase()}
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            <span>{m.user?.username || `User ${m.user_id.substring(0, 8)}`}</span>
                            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" title="Human Engineer" />
                          </div>
                          <div className="text-[10px] text-muted-foreground font-mono">
                            {m.user?.email || "internal@agentspace.local"}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px] font-mono border-cyan-500/30 text-cyan-400">
                          {m.role}
                        </Badge>
                        <span className="text-[10px] text-muted-foreground font-mono">
                          {new Date(m.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Autonomous Agents Panel */}
            <Card className="rounded-none border-border/80">
              <CardHeader className="flex flex-row items-center justify-between pb-3">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full border border-violet-500/50 bg-violet-500/10 text-violet-400 flex items-center justify-center">
                      <Bot className="w-3 h-3" />
                    </div>
                    <CardTitle className="text-sm font-bold tracking-tight">Autonomous AI Agents</CardTitle>
                  </div>
                  <CardDescription>Specialized autonomous agents executing coding, research, and review</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="border-violet-500/40 text-violet-400 font-mono text-[10px]">
                    {agents.length + (modelDefaults.default_agent_available ? 1 : 0)} Standby / Active
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { setEditingAgent(null); setAgentDialogOpen(true); }}
                    className="gap-1.5 h-7 text-xs"
                  >
                    <Plus className="w-3 h-3" />
                    <span>Add Agent</span>
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {modelDefaults.default_agent_available && <div className="p-3 border border-violet-500/30 bg-violet-500/5 text-xs"><div className="font-semibold text-violet-300">Project Planner · {modelDefaults.model}</div><p className="text-muted-foreground mt-1">Breaks the brief into tasks and coordinates file assignments when a task starts.</p></div>}
                {agents.length === 0 ? (
                  <div className="p-6 text-center text-xs text-muted-foreground border border-dashed border-border/60 space-y-3">
                    <p>No worker agents assigned to this project yet.</p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => { setEditingAgent(null); setAgentDialogOpen(true); }}
                      className="gap-1.5"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Add Agent</span>
                    </Button>
                  </div>
                ) : (
                  agents.map((ag) => (
                    <div
                      key={ag.id}
                      className="p-3 rounded-none border border-border/70 bg-card/60 flex items-center justify-between gap-3 hover:border-violet-500/40 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-full border border-violet-500/60 bg-violet-500/10 text-violet-400 flex items-center justify-center text-xs shadow-sm">
                          <Bot className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            <span>{ag.name}</span>
                            <span className="w-1.5 h-1.5 rounded-full bg-violet-400" title="Autonomous Agent" />
                          </div>
                          <div className="text-[10px] text-muted-foreground font-mono">
                            model: <span className="text-foreground">{ag.model_provider === "default" ? modelDefaults.model : ag.model}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => { setEditingAgent(ag); setAgentDialogOpen(true); }}>Edit</Button>
                        {(ag.model_provider === "default" ? modelDefaults.default_agent_available : modelDefaults.user_supplied_keys_enabled) && <Link href={`/projects/${project.id}/tasks`}><Button variant="outline" size="sm" className="h-7 text-xs">Assign task</Button></Link>}
                        <Badge
                          variant="outline"
                          title={
                            hasAgentKey[ag.id]
                              ? "API key stored in this browser"
                              : ag.model_provider === "default" ? "Developer configured Gemini" : "No API key stored in this browser"
                          }
                          className={`text-[9px] font-mono gap-1 ${
                            hasAgentKey[ag.id]
                              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                              : "border-amber-500/40 bg-amber-500/10 text-amber-400"
                          }`}
                        >
                          <KeyRound className="w-2.5 h-2.5" />
                          {ag.model_provider === "default" ? "DEFAULT" : hasAgentKey[ag.id] ? "KEY SET" : "NO KEY"}
                        </Badge>
                        <Badge
                          variant="outline"
                          className={`text-[9px] font-mono ${
                            ag.status === "BUSY"
                              ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
                              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                          }`}
                        >
                          {ag.status || "IDLE"}
                        </Badge>
                        <Badge variant="secondary" className="text-[9px] font-mono">
                          {ag.capabilities?.[0] || ag.role || "WORKER"}
                        </Badge>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: MIDDLE TAB — ONGOING PROGRESS WITH AGENT & HUMAN MARKERS */}
      {/* ========================================================================= */}
      {activeTab === "progress" && (
        <div className="space-y-5 animate-tab-enter">
          {/* Progress Overview Banner */}
          <Card className="rounded-none border-border/80">
            <CardHeader className="pb-3">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <CardTitle className="text-sm font-bold flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full border border-primary/50 bg-primary/10 flex items-center justify-center text-primary">
                      <Activity className="w-3 h-3" />
                    </div>
                    <span>Sprint Milestone Execution Pipeline</span>
                  </CardTitle>
                  <CardDescription className="text-xs mt-0.5">
                    Live collaborative timeline marking contributions by Human Engineers and Autonomous Agents
                  </CardDescription>
                </div>

                {/* Marker Legend */}
                <div className="flex items-center gap-4 text-xs font-mono bg-muted/40 p-2 border border-border/60">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 border border-cyan-300 shadow-sm" />
                    <span className="text-[11px] text-cyan-300 font-semibold">Human Engineer</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-violet-400 border border-violet-300 shadow-sm" />
                    <span className="text-[11px] text-violet-300 font-semibold">Autonomous Agent</span>
                  </div>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              {/* Progress Bar with Dual Color Indicators */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs font-mono">
                  <span className="text-muted-foreground">Overall Completion Rate</span>
                  <span className="text-foreground font-bold">{completedTasks} / {totalTasks} Tasks ({progressPercent}%)</span>
                </div>
                <div className="w-full h-2 rounded-none bg-muted overflow-hidden border border-border/70 flex">
                  <div
                    style={{ width: `${progressPercent}%` }}
                    className="h-full bg-gradient-to-r from-cyan-500 via-primary to-violet-500 transition-all duration-500"
                  />
                </div>
              </div>

              {/* Progress Milestones Stream with Color-Coded Markers */}
              <div className="space-y-3 pt-2">
                <div className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">
                  Milestone Stage Sequence
                </div>

                {tasks.length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground border border-dashed border-border/60">
                    No tasks yet. Open the task board to generate a plan with the default agent or create a task manually.
                  </div>
                ) : (
                  <div className="relative border-l-2 border-border/60 ml-4 pl-6 space-y-6">
                    {tasks.map((task) => {
                      // Determine if task assigned to human or agent
                      const isAssignedToAgent = Boolean(task.assigned_agent_id);
                      const isAssignedToHuman = Boolean(task.assigned_user_id);
                      const isCompleted = task.status === "DONE";
                      const isInProgress = task.status === "IN_PROGRESS" || task.status === "REVIEW";

                      return (
                        <div key={task.id} className="relative group">
                          {/* Color-Coded Circular Marker on the timeline */}
                          <div
                            className={`absolute -left-[35px] top-1.5 w-6 h-6 rounded-full border-2 flex items-center justify-center text-[10px] font-bold shadow-md transition-transform group-hover:scale-110 ${
                              isAssignedToAgent
                                ? "border-violet-400 bg-violet-950 text-violet-300 ring-2 ring-violet-500/20"
                                : isAssignedToHuman ? "border-cyan-400 bg-cyan-950 text-cyan-300 ring-2 ring-cyan-500/20" : "border-border bg-muted text-muted-foreground"
                            }`}
                            title={isAssignedToAgent ? agentName(task.assigned_agent_id) : isAssignedToHuman ? humanName(task.assigned_user_id) : "Unassigned task"}
                          >
                            {isAssignedToAgent ? (
                              <Bot className="w-3 h-3 text-violet-300" />
                            ) : isAssignedToHuman ? (
                              <UserCheck className="w-3 h-3 text-cyan-300" />
                            ) : (
                              <CheckSquare className="w-3 h-3" />
                            )}
                          </div>

                          {/* Task Card in Pipeline */}
                          <div className="p-3.5 rounded-none border border-border/70 bg-card hover:border-border transition-all space-y-2">
                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                              <div className="space-y-0.5">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-bold text-foreground group-hover:text-primary transition-colors">
                                    {task.title}
                                  </span>
                                  <Badge
                                    variant="outline"
                                    className={`text-[9px] font-mono ${
                                      isCompleted
                                        ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                                        : isInProgress
                                        ? "border-amber-500/40 text-amber-400 bg-amber-500/10"
                                        : "border-border text-muted-foreground"
                                    }`}
                                  >
                                    {task.status}
                                  </Badge>
                                </div>
                                {task.description && (
                                  <p className="text-[11px] text-muted-foreground line-clamp-1">
                                    {task.description}
                                  </p>
                                )}
                                {task.result?.stage && <p className="text-[11px] text-primary">{task.result.stage}{task.result.files?.length ? ` · ${task.result.files.join(", ")}` : ""}</p>}
                                {task.result?.changes?.length ? (
                                  <div className="flex flex-wrap gap-1 pt-1">
                                    {task.result.changes.map((change) => (
                                      <span key={change.path} className="border border-border/70 bg-muted/40 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                                        {change.path} <span className="text-emerald-400">+{change.additions}</span> <span className="text-rose-400">-{change.deletions}</span>
                                      </span>
                                    ))}
                                  </div>
                                ) : null}
                              </div>

                              {/* Actor Marker Badge */}
                              <div className="flex items-center gap-2 shrink-0">
                                {isAssignedToAgent ? (
                                  <div className="flex items-center gap-1.5 px-2 py-0.5 border border-violet-500/30 bg-violet-500/10 text-violet-300 rounded-none text-[10px] font-mono font-medium">
                                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                                    <span>{agentName(task.assigned_agent_id)}</span>
                                  </div>
                                ) : task.assigned_user_id ? (
                                  <div className="flex items-center gap-1.5 px-2 py-0.5 border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 rounded-none text-[10px] font-mono font-medium">
                                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                                    <span>{humanName(task.assigned_user_id)}</span>
                                  </div>
                                ) : (
                                  <div className="px-2 py-0.5 border border-border text-muted-foreground text-[10px] font-mono">Unassigned</div>
                                )}
                                <span className="text-[10px] text-muted-foreground font-mono">
                                  Pri: {task.priority}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: TASKS & DELIVERABLES */}
      {/* ========================================================================= */}
      {activeTab === "tasks" && (
        <div className="space-y-4 animate-tab-enter">
          <Card className="rounded-none border-border/80">
            <CardHeader className="pb-3 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full border border-primary/50 bg-primary/10 flex items-center justify-center text-primary">
                    <CheckSquare className="w-3 h-3" />
                  </div>
                  <span>Project Task Roster & Deliverables</span>
                </CardTitle>
                <CardDescription className="text-xs">
                  Inspect task state machine, priority queues, and autonomous agent assignments
                </CardDescription>
              </div>

              {/* Status Filter Filters */}
              <div className="flex items-center gap-1.5 border border-border/70 p-1 bg-muted/40 text-xs">
                {["ALL", "TODO", "IN_PROGRESS", "REVIEW", "DONE"].map((st) => (
                  <button
                    key={st}
                    onClick={() => setTaskFilter(st)}
                    className={`px-2 py-0.5 rounded-none font-mono text-[10px] font-semibold transition-colors ${
                      taskFilter === st
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </CardHeader>

            <CardContent className="space-y-2.5">
              {filteredTasks.length === 0 ? (
                <div className="p-8 text-center text-xs text-muted-foreground border border-dashed border-border/60">
                  No tasks matching the selected filter ({taskFilter}).
                </div>
              ) : (
                filteredTasks.map((t) => (
                  <div
                    key={t.id}
                    className="p-3.5 rounded-none border border-border/70 bg-card hover:border-border transition-colors flex items-center justify-between gap-4"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-foreground truncate">{t.title}</span>
                        <Badge variant="outline" className="text-[9px] font-mono">
                          {t.status}
                        </Badge>
                        <Badge variant="secondary" className="text-[9px] font-mono">
                          {t.priority}
                        </Badge>
                      </div>
                      {t.description && (
                        <p className="text-[11px] text-muted-foreground line-clamp-1">{t.description}</p>
                      )}
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {t.assigned_agent_id ? (
                        <div className="flex items-center gap-1 text-[10px] font-mono text-violet-400 border border-violet-500/30 px-1.5 py-0.5 bg-violet-500/10">
                          <Bot className="w-3 h-3" />
                          <span>{agentName(t.assigned_agent_id)}</span>
                        </div>
                      ) : t.assigned_user_id ? (
                        <div className="flex items-center gap-1 text-[10px] font-mono text-cyan-400 border border-cyan-500/30 px-1.5 py-0.5 bg-cyan-500/10">
                          <Users className="w-3 h-3" />
                          <span>{humanName(t.assigned_user_id)}</span>
                        </div>
                      ) : (
                        <div className="text-[10px] font-mono text-muted-foreground border border-border px-1.5 py-0.5">Unassigned</div>
                      )}
                      <Link href={`/projects/${project.id}/tasks`}>
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs gap-1">
                          <span>Board</span>
                          <ChevronRight className="w-3 h-3" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <AgentDialog
        isOpen={agentDialogOpen}
        onClose={() => setAgentDialogOpen(false)}
        projects={project ? [project] : []}
        defaults={modelDefaults}
        agent={editingAgent}
        presetProjectId={projectId}
        onSaved={(saved, created) => {
          setAgents((prev) => {
            const next = created
              ? [saved, ...prev]
              : prev.map((agent) => (agent.id === saved.id ? saved : agent));
            return next.sort((a, b) => {
              // Keep project-scoped agents visible alongside org-wide ones.
              const aScoped = a.project_id === projectId ? 0 : 1;
              const bScoped = b.project_id === projectId ? 0 : 1;
              return aScoped - bScoped;
            });
          });
          setCredentialVersion((v) => v + 1);
        }}
        onDeleted={(removed) => {
          setAgents((prev) => prev.filter((agent) => agent.id !== removed.id));
          setCredentialVersion((v) => v + 1);
        }}
      />
    </div>
  );
}
