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
  ArrowRight,
  RotateCcw,
  Search,
} from "lucide-react";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { apiFetch } from "@/lib/api-client";
import { Project } from "@/types/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiFetch<Project[]>("/api/v1/projects");
      setProjects(data || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.slug.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Projects
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            All collaborative workspaces and agent assignments.
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
          <CreateProjectDialog
            onProjectCreated={(p) => setProjects((prev) => [p, ...prev])}
          />
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="relative max-w-md">
        <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Filter by name or slug..."
          className="w-full pl-9 pr-4 py-2 text-sm rounded-md border bg-card focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {/* Projects Grid */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-44 rounded-xl border bg-card/60 p-6 animate-pulse space-y-4"
            />
          ))}
        </div>
      ) : error ? (
        <Card>
          <CardContent className="p-8 text-center space-y-3">
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchProjects}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : filteredProjects.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="p-12 text-center space-y-4">
            <FolderKanban className="w-12 h-12 text-muted-foreground mx-auto" />
            <div>
              <h3 className="text-base font-semibold">No projects found</h3>
              <p className="text-xs text-muted-foreground mt-1">
                {searchTerm
                  ? "No projects match your filter query."
                  : "Create your first collaborative software workspace."}
              </p>
            </div>
            {!searchTerm && (
              <CreateProjectDialog
                onProjectCreated={(p) => setProjects((prev) => [p, ...prev])}
              />
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredProjects.map((project) => (
            <Card
              key={project.id}
              className="hover:shadow-md transition-shadow flex flex-col justify-between"
            >
              <CardHeader className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-lg font-bold leading-tight">
                    {project.name}
                  </CardTitle>
                  <Badge variant="outline" className="text-[10px] font-mono">
                    {project.status}
                  </Badge>
                </div>
                <CardDescription className="font-mono text-xs text-primary">
                  /{project.slug}
                </CardDescription>
                {project.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2 pt-1">
                    {project.description}
                  </p>
                )}
              </CardHeader>
              <CardContent className="pt-0">
                <div className="border-t pt-3 flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground">
                    Created {new Date(project.created_at).toLocaleDateString()}
                  </span>
                  <Link href={`/projects/${project.id}`}>
                    <Button variant="ghost" size="sm" className="gap-1.5 text-xs h-8">
                      <span>Open Workspace</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
