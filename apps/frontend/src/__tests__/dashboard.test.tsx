import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  OperatorDashboard,
  OperatorTelemetry,
} from "@/components/dashboard/OperatorDashboard";

describe("Operator Dashboard Component", () => {
  const healthyTelemetry: OperatorTelemetry = {
    system_health: "HEALTHY",
    active_workflows: 14,
    agent_health: {
      available: 8,
      busy: 4,
      offline: 0,
      success_rate_percent: 98.5,
      active_connections: 12,
    },
    queue_depth: {
      agent_tasks: 3,
      nats_events: 5,
      outbox_pending: 2,
    },
    failed_tasks: 0,
    sandbox_failures: 0,
    api_errors: 1,
    model_latency_p95_ms: 245,
    database_health: "UP",
  };

  const degradedTelemetry: OperatorTelemetry = {
    system_health: "DEGRADED",
    active_workflows: 32,
    agent_health: {
      available: 1,
      busy: 10,
      offline: 4,
      success_rate_percent: 74.2,
      active_connections: 15,
    },
    queue_depth: {
      agent_tasks: 120,
      nats_events: 80,
      outbox_pending: 45,
    },
    failed_tasks: 18,
    sandbox_failures: 5,
    api_errors: 42,
    model_latency_p95_ms: 1250,
    database_health: "DOWN",
  };

  it("renders healthy operational status and correct metrics", () => {
    const { container } = render(<OperatorDashboard telemetry={healthyTelemetry} />);

    // Header & health badges
    expect(screen.getByText("System Operator Dashboard")).toBeInTheDocument();
    expect(screen.getByText("HEALTHY")).toBeInTheDocument();
    expect(screen.getByText("Data Store")).toBeInTheDocument();
    expect(screen.getByText("UP")).toBeInTheDocument();

    // Active workflows
    expect(screen.getByText("Active Workflows")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("Workflow Engine")).toBeInTheDocument();

    // Agent success rate & availability
    expect(screen.getByText("Agent Success Rate")).toBeInTheDocument();
    expect(screen.getByText("98.5%")).toBeInTheDocument();
    expect(screen.getByText("8 Avail / 4 Busy")).toBeInTheDocument();

    // Queue depth (3 agent + 5 nats = 8)
    expect(screen.getByText("Queue Depth")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();

    // Latency
    expect(screen.getByText("Model Latency (p95)")).toBeInTheDocument();
    expect(screen.getByText(/245/)).toBeInTheDocument();

    // Pulse animation for healthy status
    const pulseDot = container.querySelector(".bg-emerald-500.animate-pulse");
    expect(pulseDot).not.toBeNull();
  });

  it("renders degraded/unhealthy status with danger indicators and failure metrics", () => {
    const { container } = render(<OperatorDashboard telemetry={degradedTelemetry} />);

    expect(screen.getByText("DEGRADED")).toBeInTheDocument();
    expect(screen.getByText("DOWN")).toBeInTheDocument();

    // Queue depth (120 + 80 = 200)
    expect(screen.getByText("200")).toBeInTheDocument();

    // Failed tasks and sandbox failures
    expect(screen.getByText("Failed Tasks")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("Sandbox Failures")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();

    // API errors
    expect(screen.getByText("API Errors")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();

    // Non-healthy status has rose-500 indicator and no pulse
    const roseDot = container.querySelector(".bg-rose-500");
    expect(roseDot).not.toBeNull();
    const pulseDot = container.querySelector(".animate-pulse");
    expect(pulseDot).toBeNull();
  });
});
