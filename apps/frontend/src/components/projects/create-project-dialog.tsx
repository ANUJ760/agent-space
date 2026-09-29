"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus, X, FolderKanban } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { Project, ProjectCreate } from "@/types/api";

interface CreateProjectDialogProps {
  onProjectCreated: (project: Project) => void;
}

export function CreateProjectDialog({ onProjectCreated }: CreateProjectDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleNameChange = (val: string) => {
    setName(val);
    // Auto-generate slug from name if user hasn't typed a custom slug
    const generatedSlug = val
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    setSlug(generatedSlug);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !slug.trim()) {
      setError("Project name and slug are required.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const payload: ProjectCreate = {
        name: name.trim(),
        slug: slug.trim(),
        description: description.trim() || undefined,
      };

      const created = await apiFetch<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      onProjectCreated(created);
      setIsOpen(false);
      setName("");
      setSlug("");
      setDescription("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <Button onClick={() => setIsOpen(true)} className="gap-2">
        <Plus className="w-4 h-4" />
        <span>New Project</span>
      </Button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-xl border bg-card p-6 shadow-xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                  <FolderKanban className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-foreground">
                    Create New Project
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Define an isolated collaborative workspace for tasks and agents
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsOpen(false)}
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

              <div className="space-y-1.5 text-left">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Project Name *
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => handleNameChange(e.target.value)}
                  placeholder="e.g. Autonomous Payment Gateway"
                  required
                  className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="space-y-1.5 text-left">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  URL Slug *
                </label>
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="e.g. payment-gateway"
                  required
                  className="w-full px-3 py-2 text-sm rounded-md border bg-background font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="space-y-1.5 text-left">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Short summary of project objectives, codebase references, or scope..."
                  rows={3}
                  className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsOpen(false)}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting} className="gap-2">
                  <span>{isSubmitting ? "Creating..." : "Create Project"}</span>
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
