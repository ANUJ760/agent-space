import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProtectedRoute } from "@/components/auth/protected-route";
import UnauthorizedPage from "@/app/unauthorized/page";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(),
  useParams: () => ({}),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: vi.fn(),
}));

describe("Authorization UI & Protected Route", () => {
  const mockPush = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useRouter as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      push: mockPush,
      replace: vi.fn(),
    });
  });

  it("renders spinner during auth initialization", () => {
    (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      user: null,
    });

    render(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>
    );

    expect(screen.getByText("Authenticating session...")).toBeInTheDocument();
    expect(screen.queryByText("Secret Content")).not.toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("redirects unauthenticated users to /login", () => {
    (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });

    render(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>
    );

    expect(mockPush).toHaveBeenCalledWith("/login");
    expect(screen.queryByText("Secret Content")).not.toBeInTheDocument();
  });

  it("redirects unauthorized roles to /unauthorized", () => {
    (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        id: "u-dev-1",
        email: "dev@company.com",
        name: "Developer",
        role: "MEMBER",
      },
    });

    render(
      <ProtectedRoute requiredRole="PROJECT_ADMIN">
        <div>Admin Panel</div>
      </ProtectedRoute>
    );

    expect(mockPush).toHaveBeenCalledWith("/unauthorized");
    expect(screen.queryByText("Admin Panel")).not.toBeInTheDocument();
  });

  it("allows access and renders content when role matches requiredRole", () => {
    (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        id: "u-admin-1",
        email: "admin@company.com",
        name: "Admin User",
        role: "PROJECT_ADMIN",
      },
    });

    render(
      <ProtectedRoute requiredRole="PROJECT_ADMIN">
        <div>Admin Panel</div>
      </ProtectedRoute>
    );

    expect(screen.getByText("Admin Panel")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("allows ORG_ADMIN access unconditionally across all protected views", () => {
    (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        id: "u-super-1",
        email: "super@company.com",
        name: "Super Admin",
        role: "ORG_ADMIN",
      },
    });

    render(
      <ProtectedRoute requiredRole="SECURITY_OPERATOR">
        <div>Security Settings</div>
      </ProtectedRoute>
    );

    expect(screen.getByText("Security Settings")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("renders 403 Unauthorized page with navigation links", () => {
    render(<UnauthorizedPage />);

    expect(screen.getByText("403 — Access Denied")).toBeInTheDocument();
    expect(screen.getByText(/do not have the required permissions/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to Dashboard/i })).toHaveAttribute(
      "href",
      "/"
    );
    expect(screen.getByRole("link", { name: /Switch Account/i })).toHaveAttribute(
      "href",
      "/login"
    );
  });
});
