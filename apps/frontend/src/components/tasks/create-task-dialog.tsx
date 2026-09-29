"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus, X, CheckSquare } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { Task, TaskCreate } from "@/types/api";

interface CreateTaskDialogProps {
  projectId: string;
  onTaskCreated: (task: Task) => void;
}

export function CreateTaskDialog({ projectId, onTaskCreated }: CreateTaskDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<"LOW" | "MEDIUM" | "HIGH" | "CRITICAL">("MEDIUM");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Task title is required.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const payload: TaskCreate = {
        title: title.trim(),
        description: description.trim() || undefined,
        priority,
      };

      const created = await apiFetch<Task>(`/api/v1/projects/${projectId}/tasks`, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      onTaskCreated(created);
      setIsOpen(false);
      setTitle("");
      setDescription("");
      setPriority("MEDIUM");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <Button onClick={() => setIsOpen(true)} className="gap-2 shadow-sm">
        <Plus className="w-4 h-4" />
        <span>New Task</span>
      </Button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-xl border bg-card p-6 shadow-xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                  <CheckSquare className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-foreground">
                    Create Project Task
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Add a task to the project backlog for human or autonomous agent execution
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
                  Task Title *
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Implement OIDC token refresh in auth service"
                  required
                  className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="space-y-1.5 text-left">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Priority
                </label>
                <select
                  value={priority}
                  onChange={(e) =>
                    setPriority(e.target.value as "LOW" | "MEDIUM" | "HIGH" | "CRITICAL")
                  }
                  className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="CRITICAL">Critical</option>
                </select>
              </div>

              <div className="space-y-1.5 text-left">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Description & Context
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Detailed task description, acceptance criteria, or prompt instructions..."
                  rows={4}
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
                  <span>{isSubmitting ? "Creating..." : "Create Task"}</span>
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
