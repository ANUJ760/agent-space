import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Loading from "@/app/loading";
import ErrorBoundary from "@/app/error";
import ProjectKanbanPage from "@/app/projects/[projectId]/tasks/page";
import { apiFetch } from "@/lib/api-client";
import { Project, Task } from "@/types/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "proj-err-1" }),
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

describe("Loading and Error States", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders global loading skeleton with animated pulse classes", () => {
    const { container } = render(<Loading />);
    const pulseContainer = container.querySelector(".animate-pulse");
    expect(pulseContainer).not.toBeNull();
  });

  it("renders error boundary with digest and triggers reset retry callback", () => {
    const mockReset = vi.fn();
    const testError = Object.assign(new Error("Database connection dropped unexpectedly"), {
      digest: "ERR_DB_1002",
    });

    render(<ErrorBoundary error={testError} reset={mockReset} />);

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Error Digest: ERR_DB_1002")).toBeInTheDocument();

    const tryAgainBtn = screen.getByRole("button", { name: /Try again/i });
    fireEvent.click(tryAgainBtn);

    expect(mockReset).toHaveBeenCalledTimes(1);
  });

  it("renders loading state in Kanban board while data is fetching", () => {
    // Return unresolved promise to keep loading state active
    (apiFetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));

    const { container } = render(<ProjectKanbanPage />);
    const skeleton = container.querySelector(".animate-pulse");
    expect(skeleton).not.toBeNull();
  });

  it("renders error state when API fails, and recovers successfully on Retry", async () => {
    let shouldFail = true;

    const mockProj: Project = {
      id: "proj-err-1",
      organization_id: "org-1",
      name: "Resilient Project",
      slug: "resilient-project",
      description: "Test description",
      status: "ACTIVE",
      created_by_id: null,
      created_at: "2026-09-30T00:00:00Z",
      updated_at: "2026-09-30T00:00:00Z",
    };

    const mockTasks: Task[] = [
      {
        id: "task-res-1",
        project_id: "proj-err-1",
        organization_id: "org-1",
        title: "Recovered Task",
        description: null,
        status: "TODO",
        priority: "LOW",
        assigned_agent_id: null,
        assigned_user_id: null,
        version: 1,
        created_at: "2026-09-30T00:00:00Z",
        updated_at: "2026-09-30T00:00:00Z",
      },
    ];

    (apiFetch as unknown as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (shouldFail) {
        return Promise.reject(new Error("Service Unavailable: 503 Backend Unreachable"));
      }
      if (url === "/api/v1/projects/proj-err-1") return Promise.resolve(mockProj);
      if (url === "/api/v1/projects/proj-err-1/tasks") return Promise.resolve(mockTasks);
      return Promise.reject(new Error("Unknown route"));
    });

    render(<ProjectKanbanPage />);

    // Wait for error card to appear
    await waitFor(() => {
      expect(
        screen.getByText("Service Unavailable: 503 Backend Unreachable")
      ).toBeInTheDocument();
    });

    // Fix backend health and click Retry
    shouldFail = false;
    const retryBtn = screen.getByRole("button", { name: /Retry/i });
    fireEvent.click(retryBtn);

    // Verify recovery
    await waitFor(() => {
      expect(screen.getByText("Resilient Project Tasks")).toBeInTheDocument();
      expect(screen.getByText("Recovered Task")).toBeInTheDocument();
    });
  });
});
