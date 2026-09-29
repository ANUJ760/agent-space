"use client";

import React, { useEffect, useState, useCallback } from "react";
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
} from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { Project, ProjectMember, Agent, Task } from "@/types/api";

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
  const [activeTab, setActiveTab] = useState<
    "overview" | "members" | "agents" | "activity" | "tasks"
  >("overview");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjectDetails = useCallback(async () => {
    if (!projectId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [projData, membersData, agentsData, tasksData, eventsData] =
        await Promise.all([
          apiFetch<Project>(`/api/v1/projects/${projectId}`),
          apiFetch<ProjectMember[]>(`/api/v1/projects/${projectId}/members`).catch(
            () => []
          ),
          apiFetch<Agent[]>(`/api/v1/projects/${projectId}/agents`).catch(
            () => []
          ),
          apiFetch<Task[]>(`/api/v1/projects/${projectId}/tasks`).catch(
            () => []
          ),
          apiFetch<AuditEvent[]>(
            `/api/v1/projects/${projectId}/audit-events`
          ).catch(() => []),
        ]);

      setProject(projData);
      setMembers(membersData || []);
      setAgents(agentsData || []);
      setTasks(tasksData || []);
      setAuditEvents(eventsData || []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load project details"
      );
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchProjectDetails();
  }, [fetchProjectDetails]);

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto space-y-6 animate-pulse">
        <div className="h-10 w-48 bg-muted rounded-md" />
        <div className="h-40 rounded-xl border bg-card/60 p-6" />
        <div className="h-96 rounded-xl border bg-card/60 p-6" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-7xl mx-auto py-12 text-center space-y-4">
        <div className="w-12 h-12 rounded-xl bg-destructive/10 text-destructive flex items-center justify-center mx-auto">
          <FolderKanban className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold">Project Not Found</h2>
        <p className="text-sm text-muted-foreground">{error || "The requested project does not exist."}</p>
        <Link href="/projects">
          <Button variant="outline" className="gap-2">
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Projects</span>
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Back button & quick breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href="/projects"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Projects</span>
        </Link>

        <Button
          variant="outline"
          size="sm"
          onClick={fetchProjectDetails}
          className="gap-2 text-xs"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {/* Project Header Card */}
      <div className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0 shadow-sm">
              <FolderKanban className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl font-bold tracking-tight text-foreground">
                  {project.name}
                </h1>
                <Badge variant="outline" className="text-xs font-mono">
                  {project.status}
                </Badge>
              </div>
              <p className="text-xs font-mono text-muted-foreground">
                slug: <span className="text-primary font-semibold">/{project.slug}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link href={`/projects/${project.id}/tasks`}>
              <Button size="sm" className="gap-2 shadow-sm">
                <CheckSquare className="w-4 h-4" />
                <span>Open Kanban Board</span>
              </Button>
            </Link>
          </div>
        </div>

        {project.description && (
          <p className="text-sm text-muted-foreground pt-1 border-t">
            {project.description}
          </p>
        )}

        {/* Quick stat ribbon */}
        <div className="flex flex-wrap items-center gap-6 pt-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Users className="w-4 h-4 text-primary" />
            <span>
              <strong className="text-foreground">{members.length}</strong> Team Members
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Bot className="w-4 h-4 text-primary" />
            <span>
              <strong className="text-foreground">{agents.length}</strong> Autonomous Agents
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckSquare className="w-4 h-4 text-primary" />
            <span>
              <strong className="text-foreground">{tasks.length}</strong> Tasks
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <span>
              Created {new Date(project.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b flex items-center gap-2">
        {[
          { key: "overview", label: "Overview", icon: Layers },
          { key: "tasks", label: `Tasks (${tasks.length})`, icon: CheckSquare },
          { key: "members", label: `Members (${members.length})`, icon: Users },
          { key: "agents", label: `Agents (${agents.length})`, icon: Bot },
          { key: "activity", label: `Audit Events (${auditEvents.length})`, icon: Activity },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as typeof activeTab)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                isActive
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Panels */}
      {activeTab === "overview" && (
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Workspace Information</CardTitle>
              <CardDescription>Metadata and configuration parameters</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex justify-between py-1.5 border-b">
                <span className="text-muted-foreground">Project ID</span>
                <span className="font-mono text-xs text-foreground">{project.id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b">
                <span className="text-muted-foreground">Organization ID</span>
                <span className="font-mono text-xs text-foreground">{project.organization_id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b">
                <span className="text-muted-foreground">Environment</span>
                <Badge variant="secondary" className="text-[10px]">PRODUCTION</Badge>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-muted-foreground">Isolated Git Workspace</span>
                <span className="font-mono text-xs text-emerald-600">Enabled</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent Audit Stream</CardTitle>
              <CardDescription>Transactional outbox event trail</CardDescription>
            </CardHeader>
            <CardContent>
              {auditEvents.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">No audit events recorded yet.</p>
              ) : (
                <div className="space-y-2.5">
                  {auditEvents.slice(0, 4).map((e) => (
                    <div
                      key={e.id}
                      className="flex items-center justify-between p-2.5 rounded-lg border bg-card/60 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-primary" />
                        <span className="font-mono font-semibold text-foreground">{e.event_type}</span>
                      </div>
                      <span className="text-muted-foreground">
                        {new Date(e.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "members" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Project Members</CardTitle>
              <CardDescription>Collaborators with authorized RBAC access</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {members.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No individual members assigned yet.
              </p>
            ) : (
              <div className="divide-y">
                {members.map((member) => (
                  <div
                    key={member.id}
                    className="flex items-center justify-between py-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs">
                        {member.role.substring(0, 2)}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-foreground">
                          User ID: <span className="font-mono text-xs">{member.user_id}</span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Role: {member.role}
                        </div>
                      </div>
                    </div>
                    <Badge variant="outline" className="text-xs font-mono">
                      {member.role}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "agents" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Autonomous Agents</CardTitle>
              <CardDescription>Registered AI workers assigned to this project</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {agents.length === 0 ? (
              <div className="text-center py-8 space-y-2 border-2 border-dashed rounded-lg">
                <Bot className="w-8 h-8 text-muted-foreground mx-auto" />
                <p className="text-sm font-medium text-foreground">No agents registered to this project</p>
                <p className="text-xs text-muted-foreground">
                  Organization-wide agents can still execute assigned tasks.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {agents.map((agent) => (
                  <div
                    key={agent.id}
                    className="p-4 rounded-xl border bg-card flex flex-col justify-between space-y-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-foreground">{agent.name}</span>
                        <Badge variant="secondary" className="text-[10px]">{agent.status}</Badge>
                      </div>
                      <p className="text-xs font-mono text-muted-foreground">/{agent.slug}</p>
                      <p className="text-xs text-muted-foreground">{agent.description || "Autonomous worker"}</p>
                    </div>
                    <div className="pt-2 border-t flex items-center justify-between text-xs text-muted-foreground">
                      <span className="font-mono">{agent.model}</span>
                      <span className="font-mono">{agent.role}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "activity" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Audit Trail & Outbox Stream</CardTitle>
            <CardDescription>Append-only domain events recorded in PostgreSQL transaction</CardDescription>
          </CardHeader>
          <CardContent>
            {auditEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No audit events recorded yet for this project.
              </p>
            ) : (
              <div className="space-y-3">
                {auditEvents.map((event) => (
                  <div
                    key={event.id}
                    className="p-3.5 rounded-lg border bg-card/60 flex items-start justify-between gap-4"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4 text-primary" />
                        <span className="font-semibold text-sm text-foreground">{event.event_type}</span>
                        <Badge variant="outline" className="text-[10px] font-mono">
                          {event.aggregate_type}
                        </Badge>
                      </div>
                      <pre className="text-[11px] bg-muted/60 p-2 rounded text-muted-foreground font-mono overflow-x-auto max-w-xl">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    </div>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                      {new Date(event.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "tasks" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Tasks Overview</CardTitle>
              <CardDescription>Tasks scheduled in this project</CardDescription>
            </div>
            <Link href={`/projects/${project.id}/tasks`}>
              <Button size="sm" className="gap-2">
                <CheckSquare className="w-4 h-4" />
                <span>Open Kanban Board</span>
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {tasks.length === 0 ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No tasks created in this project yet.
              </p>
            ) : (
              <div className="space-y-2">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    className="p-3 rounded-lg border bg-card flex items-center justify-between"
                  >
                    <div>
                      <div className="text-sm font-medium text-foreground">{task.title}</div>
                      <div className="text-xs text-muted-foreground font-mono">
                        priority: {task.priority}
                      </div>
                    </div>
                    <Badge variant="secondary" className="font-mono text-xs">
                      {task.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
