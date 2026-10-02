"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw as ResetIcon,
  Eye,
  Lock,
  GitCommit,
} from "lucide-react";
import { CreateTaskDialog } from "@/components/tasks/create-task-dialog";
import { apiFetch } from "@/lib/api-client";
import { getCredential } from "@/lib/agent-credentials";
import { runAssignedTask } from "@/lib/task-agent-runner";
import { fetchAgentModelDefaults } from "@/lib/agent-model-defaults";
import { subscribeToProjectTasks } from "@/lib/project-events";
import { Task, Project, Agent, ProjectMember } from "@/types/api";

const KANBAN_COLUMNS: Array<{
  status: Task["status"];
  title: string;
  dotColor: string;
  borderColor: string;
}> = [
  { status: "TODO", title: "To Do", dotColor: "bg-slate-400", borderColor: "border-slate-200" },
  { status: "CLAIMED", title: "Claimed", dotColor: "bg-amber-400", borderColor: "border-amber-200" },
  { status: "IN_PROGRESS", title: "In Progress", dotColor: "bg-blue-500", borderColor: "border-blue-200" },
  { status: "BLOCKED", title: "Blocked", dotColor: "bg-rose-500", borderColor: "border-rose-200" },
  { status: "REVIEW", title: "Review", dotColor: "bg-purple-500", borderColor: "border-purple-200" },
  { status: "DONE", title: "Done", dotColor: "bg-emerald-500", borderColor: "border-emerald-200" },
];

export default function ProjectKanbanPage() {
  const params = useParams();
  const projectId = params?.projectId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [selectedWorkers, setSelectedWorkers] = useState<Record<string, string>>({});
  const [runningTaskId, setRunningTaskId] = useState<string | null>(null);
  const [plannerAvailable, setPlannerAvailable] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [transitioningTaskId, setTransitioningTaskId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!projectId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [proj, taskList, agentList, memberList, defaults] = await Promise.all([
        apiFetch<Project>(`/api/v1/projects/${projectId}`),
        apiFetch<Task[]>(`/api/v1/projects/${projectId}/tasks`),
        apiFetch<Agent[]>(`/api/v1/projects/${projectId}/agents`),
        apiFetch<ProjectMember[]>(`/api/v1/projects/${projectId}/members`),
        fetchAgentModelDefaults(true),
      ]);
      setProject(proj);
      setTasks(taskList || []);
      setAgents(agentList || []);
      setMembers(memberList || []);
      setPlannerAvailable(Boolean(defaults.default_agent_available));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project tasks");
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
      try { setTasks(await apiFetch<Task[]>(`/api/v1/projects/${projectId}/tasks`)); } catch { /* Keep the last visible state. */ }
    }, 30000);
    return () => { unsubscribe(); window.clearInterval(timer); };
  }, [projectId]);

  const handleAssignAndRun = async (task: Task) => {
    if (!project) return;
    const currentValue = task.assigned_agent_id ? `AGENT:${task.assigned_agent_id}` : task.assigned_user_id ? `HUMAN:${task.assigned_user_id}` : "";
    const workerValue = selectedWorkers[task.id] || currentValue;
    const [assigneeType, assigneeId] = workerValue.split(":");
    if (!assigneeId || !["AGENT", "HUMAN"].includes(assigneeType)) { setActionError("Choose an agent or human for this task."); return; }
    const agent = assigneeType === "AGENT" ? agents.find((entry) => entry.id === assigneeId) : undefined;
    if (assigneeType === "AGENT" && !agent) { setActionError("The selected agent is unavailable."); return; }
    if (agent && !plannerAvailable) { setActionError("Set DEFAULT_GEMINI_API_KEY to enable planner coordination."); return; }
    if (agent && agent.model_provider !== "default" && !getCredential(agent.id)) { setActionError(`Attach ${agent.name}'s API key on the Agents page in this browser.`); return; }
    setRunningTaskId(task.id);
    setActionError(null);
    try {
      const isReassignment = Boolean(task.assigned_agent_id || task.assigned_user_id || task.status !== "TODO");
      const assigned = await apiFetch<Task>(`/api/v1/tasks/${task.id}/assign`, {
        method: "POST",
        body: JSON.stringify({ assignee_type: assigneeType, assignee_id: assigneeId, allow_takeover: isReassignment }),
      });
      if (!agent) { await fetchData(); return; }
      if (agent.model_provider === "default") {
        await fetchData();
        return;
      }
      await runAssignedTask(project, assigned, agent);
      await fetchData();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Agent task failed";
      setActionError(message);
      try { await apiFetch(`/api/v1/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ error_message: message.slice(0, 2048), result: { stage: "Needs attention" } }) }); } catch { /* Surface the original error. */ }
      await fetchData();
    } finally { setRunningTaskId(null); }
  };

  const handleRelease = async (task: Task) => {
    setTransitioningTaskId(task.id);
    setActionError(null);
    try {
      const updated = await apiFetch<Task>(`/api/v1/tasks/${task.id}/release`, { method: "POST" });
      setSelectedWorkers((current) => ({ ...current, [task.id]: "" }));
      setTasks((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Could not release task"); }
    finally { setTransitioningTaskId(null); }
  };

  const handleTakeover = async (task: Task) => {
    setTransitioningTaskId(task.id);
    setActionError(null);
    try {
      const updated = await apiFetch<Task>(`/api/v1/tasks/${task.id}/takeover`, {
        method: "POST",
        body: JSON.stringify({ expected_version: task.version, reason: "Human takeover from task board" }),
      });
      setSelectedWorkers((current) => ({ ...current, [task.id]: `HUMAN:${updated.assigned_user_id}` }));
      setTasks((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Could not take over task"); }
    finally { setTransitioningTaskId(null); }
  };

  const handlePlan = async () => {
    setActionError(null);
    try {
      await apiFetch(`/api/v1/projects/${projectId}/plan`, { method: "POST" });
      await fetchData();
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Planner failed"); }
  };

  const handleUseDefault = async () => {
    setActionError(null);
    try {
      const created = await apiFetch<Agent>(`/api/v1/projects/${projectId}/agents`, {
        method: "POST",
        body: JSON.stringify({ name: "Default Gemini Agent", slug: `default-gemini-${projectId.replace(/-/g, "").slice(0, 12)}`, role: "DEVELOPER", model_provider: "default", model: (await fetchAgentModelDefaults()).model, system_prompt: "Work on assigned project tasks and write complete files for review." }),
      });
      setAgents((old) => [...old, created]);
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Could not add default agent"); }
  };

  // Execute state machine transition respecting server-side validation & optimistic locking
  const handleTransition = async (task: Task, nextStatus: Task["status"]) => {
    setTransitioningTaskId(task.id);
    setActionError(null);
    try {
      const updated = await apiFetch<Task>(`/api/v1/tasks/${task.id}/transition`, {
        method: "POST",
        body: JSON.stringify({
          status: nextStatus,
          expected_version: task.version,
          reason: `Transitioned via Kanban to ${nextStatus}`,
        }),
      });

      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to transition task status"
      );
    } finally {
      setTransitioningTaskId(null);
    }
  };

  const priorityBadge = (priority: Task["priority"]) => {
    switch (priority) {
      case "CRITICAL":
        return <Badge variant="destructive" className="text-[10px]">CRITICAL</Badge>;
      case "HIGH":
        return <Badge className="bg-amber-500 hover:bg-amber-600 text-[10px]">HIGH</Badge>;
      case "MEDIUM":
        return <Badge variant="secondary" className="text-[10px]">MEDIUM</Badge>;
      default:
        return <Badge variant="outline" className="text-[10px]">LOW</Badge>;
    }
  };

  return (
    <div className="space-y-6 max-w-full mx-auto">
      {/* Top Bar Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link
              href={`/projects/${projectId}`}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Project Workspace</span>
            </Link>
            <span className="text-muted-foreground">/</span>
            <span className="text-xs font-semibold text-foreground">Kanban Board</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <span>{project?.name || "Project"} Tasks</span>
            <span className="text-sm font-normal font-mono text-muted-foreground">
              ({tasks.length} total)
            </span>
          </h1>
          <p className="text-xs text-muted-foreground">Assigned workers share the project files and checkpoints. User-key agents run in this browser; the default agent continues in the background.</p>
        </div>

        <div className="flex items-center gap-3">
          <Link href="/agents"><Button variant="outline" size="sm">Create agent</Button></Link>
          {plannerAvailable && !agents.some((agent) => agent.model_provider === "default") && <Button variant="outline" size="sm" onClick={handleUseDefault}>Use default agent</Button>}
          {tasks.length === 0 && <Button variant="outline" size="sm" onClick={handlePlan} disabled={!plannerAvailable}>Plan with default agent</Button>}
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            className="gap-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <CreateTaskDialog
            projectId={projectId}
            onTaskCreated={(newTask) => setTasks((prev) => [newTask, ...prev])}
          />
        </div>
      </div>

      {actionError && (
        <div className="p-3.5 rounded-lg bg-destructive/10 text-destructive text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{actionError}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActionError(null)}
            className="h-7 text-xs text-destructive"
          >
            Dismiss
          </Button>
        </div>
      )}

      {!plannerAvailable && <p className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-600">The planner is unavailable until the developer sets DEFAULT_GEMINI_API_KEY. You can still create tasks manually.</p>}

      {/* Kanban Board Columns Container */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 animate-pulse">
          {KANBAN_COLUMNS.map((col) => (
            <div
              key={col.status}
              className="h-[75vh] rounded-xl border bg-muted/20 p-4 space-y-3"
            />
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
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 items-start">
          {KANBAN_COLUMNS.map((col) => {
            const columnTasks = tasks.filter((t) => t.status === col.status);

            return (
              <div
                key={col.status}
                className="flex flex-col rounded-xl border bg-card/60 shadow-sm max-h-[80vh] overflow-hidden"
              >
                {/* Column Header */}
                <div className="p-3.5 border-b bg-card flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${col.dotColor}`} />
                    <span className="font-semibold text-xs text-foreground uppercase tracking-wider">
                      {col.title}
                    </span>
                  </div>
                  <Badge variant="secondary" className="font-mono text-xs px-2 py-0">
                    {columnTasks.length}
                  </Badge>
                </div>

                {/* Column Cards Container */}
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {columnTasks.length === 0 ? (
                    <div className="h-32 border-2 border-dashed rounded-lg flex items-center justify-center text-xs text-muted-foreground/60 italic">
                      Empty
                    </div>
                  ) : (
                    columnTasks.map((task) => {
                      const isTransitioning = transitioningTaskId === task.id;
                      const assignedValue = task.assigned_agent_id ? `AGENT:${task.assigned_agent_id}` : task.assigned_user_id ? `HUMAN:${task.assigned_user_id}` : "";
                      const workerValue = selectedWorkers[task.id] ?? assignedValue;
                      const [workerType, workerId] = workerValue.split(":");
                      const selectedAgent = workerType === "AGENT" ? agents.find((agent) => agent.id === workerId) : undefined;
                      const assignmentChanged = workerValue !== assignedValue;
                      const defaultAgentIsRunning = selectedAgent?.model_provider === "default" && task.status !== "TODO" && !assignmentChanged;
                      const humanAssignmentUnchanged = workerType === "HUMAN" && Boolean(assignedValue) && !assignmentChanged;

                      return (
                        <Card
                          key={task.id}
                          className="shadow-sm hover:shadow-md transition-shadow bg-card border"
                        >
                          <CardHeader className="p-3.5 pb-2 space-y-2">
                            <div className="flex items-start justify-between gap-1.5">
                              <CardTitle className="text-xs font-semibold leading-snug text-foreground">
                                {task.title}
                              </CardTitle>
                              {priorityBadge(task.priority)}
                            </div>

                            {task.description && (
                              <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                                {task.description}
                              </p>
                            )}
                          </CardHeader>

                          <CardContent className="p-3.5 pt-0 space-y-2.5">
                            {task.result?.stage && <p className="text-[11px] text-primary">{task.result.stage}{task.result.files?.length ? ` · ${task.result.files.join(", ")}` : ""}</p>}
                            {task.result?.summary && <p className="text-[11px] text-muted-foreground">{task.result.summary}</p>}
                            {task.error_message && <p className="text-[11px] text-destructive">{task.error_message}</p>}
                            {!(["DONE", "CANCELLED"].includes(task.status)) && <div className="space-y-1.5">
                              <select aria-label={`Worker for ${task.title}`} className="w-full rounded border bg-background p-1.5 text-[11px]" value={workerValue} onChange={(event) => setSelectedWorkers((old) => ({ ...old, [task.id]: event.target.value }))}>
                                <option value="">Assign a worker</option>
                                <optgroup label="Agents">
                                  {agents.map((agent) => <option key={agent.id} value={`AGENT:${agent.id}`}>{agent.name} · {agent.model_provider}</option>)}
                                </optgroup>
                                <optgroup label="Humans">
                                  {members.map((member) => <option key={member.user_id} value={`HUMAN:${member.user_id}`}>{member.user?.username || member.user?.email || `User ${member.user_id.slice(0, 8)}`}</option>)}
                                </optgroup>
                              </select>
                              <div className="flex gap-1">
                                <Button size="sm" className="h-7 flex-1 text-[11px]" disabled={defaultAgentIsRunning || humanAssignmentUnchanged || runningTaskId === task.id || !workerId || (workerType === "AGENT" && !plannerAvailable)} onClick={() => handleAssignAndRun(task)}>{defaultAgentIsRunning ? "Running in background…" : humanAssignmentUnchanged ? "Assigned to human" : runningTaskId === task.id ? "Starting…" : assignedValue ? assignmentChanged ? workerType === "AGENT" ? "Reassign and start" : "Reassign human" : "Restart agent" : workerType === "AGENT" ? "Assign and start" : "Assign human"}</Button>
                                {assignedValue && <Button variant="outline" size="sm" className="h-7 px-2 text-[10px]" disabled={isTransitioning} onClick={() => handleRelease(task)}>Release</Button>}
                              </div>
                              {task.assigned_agent_id && task.status !== "TODO" && <Button variant="outline" size="sm" className="h-7 w-full text-[10px]" disabled={isTransitioning} onClick={() => handleTakeover(task)}>Take over as me</Button>}
                            </div>}
                            {/* Worker Assignment & Dependencies */}
                            <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground pt-1 border-t">
                              {task.assigned_agent_id ? (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-primary/10 text-primary font-mono">
                                  <span>{agents.find((agent) => agent.id === task.assigned_agent_id)?.name || "agent"}</span>
                                </span>
                              ) : task.assigned_user_id ? (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-muted font-mono">
                                  <span>{members.find((member) => member.user_id === task.assigned_user_id)?.user?.username || `User ${task.assigned_user_id.slice(0, 8)}`}</span>
                                </span>
                              ) : (
                                <span className="text-muted-foreground/60 italic">
                                  Unassigned
                                </span>
                              )}

                              <span className="inline-flex items-center gap-0.5 text-muted-foreground font-mono ml-auto">
                                <GitCommit className="w-3 h-3" />
                                <span>v{task.version}</span>
                              </span>
                            </div>

                            {/* State Machine Transition Actions */}
                            <div className="flex items-center gap-1 pt-1.5 border-t">
                              {task.status === "TODO" && (
                                <>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-6 text-[10px] px-2 gap-1 flex-1"
                                    onClick={() => handleTransition(task, "CLAIMED")}
                                    disabled={isTransitioning}
                                  >
                                    <Lock className="w-2.5 h-2.5" />
                                    <span>Claim</span>
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-6 text-[10px] px-1 text-rose-500 hover:text-rose-600"
                                    onClick={() => handleTransition(task, "BLOCKED")}
                                    disabled={isTransitioning}
                                    title="Block"
                                  >
                                    Block
                                  </Button>
                                </>
                              )}

                              {task.status === "CLAIMED" && (
                                <>
                                  <Button
                                    size="sm"
                                    className="h-6 text-[10px] px-2 gap-1 flex-1"
                                    onClick={() => handleTransition(task, "IN_PROGRESS")}
                                    disabled={isTransitioning}
                                  >
                                    <Play className="w-2.5 h-2.5" />
                                    <span>Start</span>
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-6 text-[10px] px-1.5"
                                    onClick={() => handleRelease(task)}
                                    disabled={isTransitioning}
                                    title="Release"
                                  >
                                    <ResetIcon className="w-2.5 h-2.5" />
                                  </Button>
                                </>
                              )}

                              {task.status === "IN_PROGRESS" && (
                                <>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-6 text-[10px] px-2 gap-1 flex-1"
                                    onClick={() => handleTransition(task, "REVIEW")}
                                    disabled={isTransitioning}
                                  >
                                    <Eye className="w-2.5 h-2.5" />
                                    <span>Submit Review</span>
                                  </Button>
                                  <Button
                                    size="sm"
                                    className="h-6 text-[10px] px-2 gap-1 bg-emerald-600 hover:bg-emerald-700"
                                    onClick={() => handleTransition(task, "DONE")}
                                    disabled={isTransitioning}
                                  >
                                    <CheckCircle2 className="w-2.5 h-2.5" />
                                    <span>Done</span>
                                  </Button>
                                </>
                              )}

                              {task.status === "BLOCKED" && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="h-6 text-[10px] px-2 gap-1 flex-1"
                                  onClick={() => handleTransition(task, "TODO")}
                                  disabled={isTransitioning}
                                >
                                  <ResetIcon className="w-2.5 h-2.5" />
                                  <span>Unblock (Backlog)</span>
                                </Button>
                              )}

                              {task.status === "REVIEW" && (
                                <>
                                  <Button
                                    size="sm"
                                    className="h-6 text-[10px] px-2 gap-1 flex-1 bg-emerald-600 hover:bg-emerald-700"
                                    onClick={() => handleTransition(task, "DONE")}
                                    disabled={isTransitioning}
                                  >
                                    <CheckCircle2 className="w-2.5 h-2.5" />
                                    <span>Approve</span>
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-6 text-[10px] px-1.5 text-amber-600"
                                    onClick={() => handleTransition(task, "IN_PROGRESS")}
                                    disabled={isTransitioning}
                                  >
                                    Changes
                                  </Button>
                                </>
                              )}

                              {task.status === "DONE" && (
                                <span className="text-[10px] text-emerald-600 flex items-center gap-1 font-medium mx-auto py-0.5">
                                  <CheckCircle2 className="w-3 h-3" />
                                  <span>Completed</span>
                                </span>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
