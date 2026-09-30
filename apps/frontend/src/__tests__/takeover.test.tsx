import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import {
  HumanRequestModal,
  PendingHumanRequest,
} from "@/components/tasks/HumanRequestModal";

describe("Human Request & Takeover Modal", () => {
  it("renders TAKEOVER request properly and handles human takeover submission", async () => {
    const mockOnRespond = vi.fn().mockResolvedValue(undefined);
    const mockOnClose = vi.fn();

    const takeoverRequest: PendingHumanRequest = {
      id: "req-takeover-1",
      request_type: "TAKEOVER",
      prompt: "Coding agent stuck in iterative build loop. Human intervention required.",
      status: "PENDING",
    };

    render(
      <HumanRequestModal
        taskId="task-12345678-abcd"
        request={takeoverRequest}
        onRespond={mockOnRespond}
        onClose={mockOnClose}
      />
    );

    // Header & badge
    expect(screen.getByText("TAKEOVER REQUIRED")).toBeInTheDocument();
    expect(screen.getByText("Task #task-123")).toBeInTheDocument();
    expect(
      screen.getByText("Coding agent stuck in iterative build loop. Human intervention required.")
    ).toBeInTheDocument();

    // Fill in guidance/feedback
    const textarea = screen.getByPlaceholderText(/Provide context or guidance/i);
    fireEvent.change(textarea, {
      target: { value: "Reverting invalid commit and taking manual control" },
    });

    // Submit takeover
    const takeoverBtn = screen.getByRole("button", { name: "Take Over Task" });
    fireEvent.click(takeoverBtn);

    await waitFor(() => {
      expect(mockOnRespond).toHaveBeenCalledWith(
        "TAKEOVER",
        "Reverting invalid commit and taking manual control",
        ""
      );
      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });
  });

  it("renders APPROVAL request and supports Approve and Reject actions", async () => {
    const mockOnRespond = vi.fn().mockResolvedValue(undefined);
    const mockOnClose = vi.fn();

    const approvalRequest: PendingHumanRequest = {
      id: "req-approval-1",
      request_type: "APPROVAL",
      prompt: "Agent is requesting permission to execute database migration on production.",
      status: "PENDING",
    };

    const { rerender } = render(
      <HumanRequestModal
        taskId="task-99887766"
        request={approvalRequest}
        onRespond={mockOnRespond}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText("APPROVAL REQUIRED")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Agent is requesting permission to execute database migration on production."
      )
    ).toBeInTheDocument();

    // Test Approve
    const approveBtn = screen.getByRole("button", { name: "Approve" });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(mockOnRespond).toHaveBeenCalledWith("APPROVE", "", "");
      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    // Test Reject on clean mount
    mockOnRespond.mockClear();
    mockOnClose.mockClear();

    rerender(
      <HumanRequestModal
        taskId="task-99887766"
        request={approvalRequest}
        onRespond={mockOnRespond}
        onClose={mockOnClose}
      />
    );

    const rejectBtn = screen.getByRole("button", { name: "Reject" });
    fireEvent.click(rejectBtn);

    await waitFor(() => {
      expect(mockOnRespond).toHaveBeenCalledWith("REJECT", "", "");
      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });
  });

  it("renders DECISION request with multi-choice options and submits selected choice", async () => {
    const mockOnRespond = vi.fn().mockResolvedValue(undefined);
    const mockOnClose = vi.fn();

    const decisionRequest: PendingHumanRequest = {
      id: "req-decision-1",
      request_type: "DECISION",
      prompt: "Which database adapter should be selected for the high-concurrency event stream?",
      options: ["PostgreSQL Row-Locking", "Redis Stream Consumer Groups", "NATS JetStream"],
      status: "PENDING",
    };

    render(
      <HumanRequestModal
        taskId="task-33445566"
        request={decisionRequest}
        onRespond={mockOnRespond}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText("DECISION REQUIRED")).toBeInTheDocument();
    expect(screen.getByText("NATS JetStream")).toBeInTheDocument();

    // Select third option
    const radioOption = screen.getByLabelText("NATS JetStream");
    fireEvent.click(radioOption);

    const submitBtn = screen.getByRole("button", { name: "Submit Response" });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockOnRespond).toHaveBeenCalledWith("CHOSEN", "", "NATS JetStream");
      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });
  });

  it("closes modal on cancel / dismiss button click without submitting", () => {
    const mockOnRespond = vi.fn();
    const mockOnClose = vi.fn();

    const helpRequest: PendingHumanRequest = {
      id: "req-help-1",
      request_type: "HELP",
      prompt: "Need API credentials for third-party mock service.",
      status: "PENDING",
    };

    render(
      <HumanRequestModal
        taskId="task-55667788"
        request={helpRequest}
        onRespond={mockOnRespond}
        onClose={mockOnClose}
      />
    );

    const dismissBtn = screen.getByRole("button", { name: "Dismiss" });
    fireEvent.click(dismissBtn);

    expect(mockOnClose).toHaveBeenCalledTimes(1);
    expect(mockOnRespond).not.toHaveBeenCalled();
  });
});
