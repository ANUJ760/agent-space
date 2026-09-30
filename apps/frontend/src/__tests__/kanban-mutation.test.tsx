import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ProjectKanbanPage from "@/app/projects/[projectId]/tasks/page";
import { apiFetch } from "@/lib/api-client";
import { Task, Project } from "@/types/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "proj-101" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api-client", () => ({
  apiFetch: vi.fn(),
}));

// Mock CreateTaskDialog to avoid sub-modal complexities
vi.mock("@/components/tasks/create-task-dialog", () => ({
  CreateTaskDialog: ({ onTaskCreated }: { onTaskCreated: (task: Task) => void }) => (
    <button
      data-testid="mock-create-task"
      onClick={() =>
        onTaskCreated({
          id: "task-new-created",
          project_id: "proj-101",
          organization_id: "org-1",
          title: "Newly Created Task",
          description: "Task from mock dialog",
          status: "TODO",
          priority: "HIGH",
          assigned_agent_id: null,
          assigned_user_id: null,
          version: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
      }
    >
      New Task
    </button>
  ),
}));

describe("Kanban Board & Task Mutation", () => {
  const mockProject: Project = {
    id: "proj-101",
    organization_id: "org-1",
    name: "Autonomous Platform",
    slug: "autonomous-platform",
    description: "Core autonomous platform",
    status: "ACTIVE",
    created_by_id: null,
    created_at: "2026-09-30T00:00:00Z",
    updated_at: "2026-09-30T00:00:00Z",
  };

  const mockTasks: Task[] = [
    {
      id: "task-1",
      project_id: "proj-101",
      organization_id: "org-1",
      title: "Design DB Schema",
      description: "Postgres schema for agents",
      status: "TODO",
      priority: "CRITICAL",
      assigned_agent_id: null,
      assigned_user_id: null,
      version: 1,
      created_at: "2026-09-30T01:00:00Z",
      updated_at: "2026-09-30T01:00:00Z",
    },
    {
      id: "task-2",
      project_id: "proj-101",
      organization_id: "org-1",
      title: "Implement Auth Flow",
      description: "JWT & OAuth2 integration",
      status: "CLAIMED",
      priority: "HIGH",
      version: 2,
      assigned_agent_id: "agent-coding-1",
      assigned_user_id: null,
      created_at: "2026-09-30T02:00:00Z",
      updated_at: "2026-09-30T02:00:00Z",
    },
    {
      id: "task-3",
      project_id: "proj-101",
      organization_id: "org-1",
      title: "Build API Gateway",
      description: "FastAPI routing layer",
      status: "IN_PROGRESS",
      priority: "MEDIUM",
      version: 3,
      assigned_agent_id: null,
      assigned_user_id: "user-dev-1",
      created_at: "2026-09-30T03:00:00Z",
      updated_at: "2026-09-30T03:00:00Z",
    },
    {
      id: "task-4",
      project_id: "proj-101",
      organization_id: "org-1",
      title: "Database Lock Issue",
      description: "Deadlock resolution needed",
      status: "BLOCKED",
      priority: "LOW",
      assigned_agent_id: null,
      assigned_user_id: null,
      version: 1,
      created_at: "2026-09-30T04:00:00Z",
      updated_at: "2026-09-30T04:00:00Z",
    },
    {
      id: "task-5",
      project_id: "proj-101",
      organization_id: "org-1",
      title: "Code Review PR #42",
      description: "Review agent changes",
      status: "REVIEW",
      priority: "HIGH",
      assigned_agent_id: null,
      assigned_user_id: null,
      version: 4,
      created_at: "2026-09-30T05:00:00Z",
      updated_at: "2026-09-30T05:00:00Z",
    },
    {
      id: "task-6",
      project_id: "proj-101",
      organization_id: "org-1",
      title: "Deploy Prometheus",
      description: "Monitoring stack deployed",
      status: "DONE",
      priority: "MEDIUM",
      assigned_agent_id: null,
      assigned_user_id: null,
      version: 5,
      created_at: "2026-09-30T06:00:00Z",
      updated_at: "2026-09-30T06:00:00Z",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (apiFetch as unknown as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/v1/projects/proj-101") {
        return Promise.resolve(mockProject);
      }
      if (url === "/api/v1/projects/proj-101/tasks") {
        return Promise.resolve([...mockTasks]);
      }
      return Promise.reject(new Error(`Unhandled mock URL: ${url}`));
    });
  });

  it("renders all 6 Kanban columns and task cards correctly", async () => {
    render(<ProjectKanbanPage />);

    // Wait for project data to load
    await waitFor(() => {
      expect(screen.getByText("Autonomous Platform Tasks")).toBeInTheDocument();
    });

    // Check Kanban columns
    expect(screen.getByText("To Do")).toBeInTheDocument();
    expect(screen.getByText("Claimed")).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getAllByText("Done").length).toBeGreaterThanOrEqual(1);

    // Check task titles
    expect(screen.getByText("Design DB Schema")).toBeInTheDocument();
    expect(screen.getByText("Implement Auth Flow")).toBeInTheDocument();
    expect(screen.getByText("Build API Gateway")).toBeInTheDocument();
    expect(screen.getByText("Database Lock Issue")).toBeInTheDocument();
    expect(screen.getByText("Code Review PR #42")).toBeInTheDocument();
    expect(screen.getByText("Deploy Prometheus")).toBeInTheDocument();

    // Priority badges
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getAllByText("HIGH").length).toBeGreaterThanOrEqual(1);

    // Version indicators
    expect(screen.getAllByText("v1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("v2").length).toBeGreaterThanOrEqual(1);
  });

  it("handles task state mutation with optimistic lock expected_version", async () => {
    render(<ProjectKanbanPage />);

    await waitFor(() => {
      expect(screen.getByText("Design DB Schema")).toBeInTheDocument();
    });

    const updatedTask: Task = {
      ...mockTasks[0],
      status: "CLAIMED",
      version: 2,
    };

    (apiFetch as unknown as ReturnType<typeof vi.fn>).mockImplementation((url: string, options?: RequestInit) => {
      if (url === "/api/v1/tasks/task-1/transition") {
        const body = JSON.parse(options?.body as string);
        expect(body.status).toBe("CLAIMED");
        expect(body.expected_version).toBe(1);
        return Promise.resolve(updatedTask);
      }
      return Promise.reject(new Error("Unexpected endpoint"));
    });

    // Find and click the 'Claim' button for task-1
    const claimButton = screen.getByRole("button", { name: /Claim/i });
    fireEvent.click(claimButton);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        "/api/v1/tasks/task-1/transition",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            status: "CLAIMED",
            expected_version: 1,
            reason: "Transitioned via Kanban to CLAIMED",
          }),
        })
      );
    });
  });

  it("handles optimistic locking conflict error and displays error banner", async () => {
    render(<ProjectKanbanPage />);

    await waitFor(() => {
      expect(screen.getByText("Design DB Schema")).toBeInTheDocument();
    });

    // Mock transition failure with conflict
    (apiFetch as unknown as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/v1/tasks/task-1/transition") {
        return Promise.reject(new Error("Conflict: Task version mismatch (expected v1, found v2)"));
      }
      return Promise.reject(new Error("Unexpected endpoint"));
    });

    const claimButton = screen.getByRole("button", { name: /Claim/i });
    fireEvent.click(claimButton);

    await waitFor(() => {
      expect(
        screen.getByText("Conflict: Task version mismatch (expected v1, found v2)")
      ).toBeInTheDocument();
    });

    // Test error dismiss button
    const dismissButton = screen.getByRole("button", { name: /Dismiss/i });
    fireEvent.click(dismissButton);

    expect(
      screen.queryByText("Conflict: Task version mismatch (expected v1, found v2)")
    ).not.toBeInTheDocument();
  });

  it("dynamically appends newly created tasks from dialog into board state", async () => {
    render(<ProjectKanbanPage />);

    await waitFor(() => {
      expect(screen.getByText("Design DB Schema")).toBeInTheDocument();
    });

    const createTaskMockBtn = screen.getByTestId("mock-create-task");
    fireEvent.click(createTaskMockBtn);

    await waitFor(() => {
      expect(screen.getByText("Newly Created Task")).toBeInTheDocument();
    });
  });
});
