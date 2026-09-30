"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
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
  CheckSquare,
  Bot,
  Activity,
  ArrowUpRight,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { ProtectedRoute } from "@/components/auth/protected-route";
import { apiFetch } from "@/lib/api-client";
import { Project } from "@/types/api";

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiFetch<Project[]>("/api/v1/projects");
      setProjects(data || []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to connect to Agent Space API"
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleProjectCreated = (newProject: Project) => {
    setProjects((prev) => [newProject, ...prev]);
  };

  const activeProjectsCount = projects.filter(
    (p) => p.status === "ACTIVE"
  ).length;

  return (
    <ProtectedRoute>
      <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Workspace Dashboard
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Autonomous software engineering orchestration and human-agent collaboration.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchProjects}
            className="gap-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <CreateProjectDialog onProjectCreated={handleProjectCreated} />
        </div>
      </div>

      {/* Metrics Overview Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Projects
            </CardTitle>
            <FolderKanban className="w-4 h-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">
              {isLoading ? "..." : projects.length}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {activeProjectsCount} active in organization
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Autonomous Agents
            </CardTitle>
            <Bot className="w-4 h-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">Active</div>
            <p className="text-xs text-muted-foreground mt-1">
              Model gateway & worker registry online
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Execution Engine
            </CardTitle>
            <CheckSquare className="w-4 h-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">Ready</div>
            <p className="text-xs text-muted-foreground mt-1">
              DAG dependencies & atomic locks enabled
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Platform Health
            </CardTitle>
            <Activity className="w-4 h-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block animate-pulse" />
              <span>Operational</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              Platform Services Operational
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Workspace Panels */}
      <div className="grid gap-6 md:grid-cols-7">
        {/* Real Projects List */}
        <Card className="col-span-4 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Organization Projects</CardTitle>
              <CardDescription>
                Collaborative repositories and task workspaces
              </CardDescription>
            </div>
            <Link href="/projects">
              <Button variant="ghost" size="sm" className="gap-1 text-xs">
                <span>View all</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3 animate-pulse">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-16 rounded-lg border bg-muted/40 p-3.5"
                  />
                ))}
              </div>
            ) : error ? (
              <div className="p-6 text-center space-y-3">
                <p className="text-sm text-destructive font-medium">{error}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={fetchProjects}
                  className="gap-2"
                >
                  <RotateCcw className="w-4 h-4" />
                  <span>Retry Connection</span>
                </Button>
              </div>
            ) : projects.length === 0 ? (
              <div className="p-8 text-center space-y-3 border-2 border-dashed rounded-lg">
                <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center mx-auto">
                  <Sparkles className="w-5 h-5" />
                </div>
                <h4 className="text-sm font-semibold text-foreground">
                  No projects created yet
                </h4>
                <p className="text-xs text-muted-foreground max-w-xs mx-auto">
                  Create your first collaborative software project to register
                  tasks and autonomous agents.
                </p>
                <CreateProjectDialog onProjectCreated={handleProjectCreated} />
              </div>
            ) : (
              <div className="space-y-3">
                {projects.map((project) => (
                  <Link
                    key={project.id}
                    href={`/projects/${project.id}`}
                    className="flex items-center justify-between p-3.5 rounded-lg border bg-card hover:bg-muted/40 transition-colors group"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                          {project.name}
                        </span>
                        <Badge variant="outline" className="text-[10px] font-mono">
                          {project.status}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground font-mono">
                        slug: {project.slug}
                      </p>
                      {project.description && (
                        <p className="text-xs text-muted-foreground line-clamp-1">
                          {project.description}
                        </p>
                      )}
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors shrink-0" />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Workspace Summary & Capability Matrix */}
        <Card className="col-span-3 shadow-sm">
          <CardHeader>
            <CardTitle>Autonomous Capabilities</CardTitle>
            <CardDescription>
              Installed platform capabilities and worker runtimes
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              {
                title: "DAG Task Dependencies",
                desc: "Cycle-free topological prerequisite resolution",
                badge: "Active",
              },
              {
                title: "Atomic Row Locks",
                desc: "Atomic session lock & race-free takeover",
                badge: "Active",
              },
              {
                title: "Request Idempotency",
                desc: "Safe retries on mutation and creation endpoints",
                badge: "Active",
              },
              {
                title: "Transactional Outbox",
                desc: "Same-transaction domain event recording",
                badge: "Active",
              },
            ].map((cap) => (
              <div
                key={cap.title}
                className="flex items-start justify-between p-3 rounded-lg border bg-card/60"
              >
                <div className="space-y-0.5">
                  <div className="text-sm font-medium text-foreground">
                    {cap.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {cap.desc}
                  </div>
                </div>
                <Badge variant="secondary" className="text-[10px]">
                  {cap.badge}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
    </ProtectedRoute>
  );
}
