import React from 'react';

export interface OperatorTelemetry {
  system_health: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY';
  active_workflows: number;
  agent_health: {
    available: number;
    busy: number;
    offline: number;
    success_rate_percent: number;
    active_connections?: number;
  };
  queue_depth: {
    agent_tasks: number;
    nats_events: number;
    outbox_pending: number;
  };
  failed_tasks: number;
  sandbox_failures: number;
  api_errors: number;
  model_latency_p95_ms: number;
  database_health: 'UP' | 'DOWN';
}

interface OperatorDashboardProps {
  telemetry: OperatorTelemetry;
}

export const OperatorDashboard: React.FC<OperatorDashboardProps> = ({ telemetry }) => {
  const isHealthy = telemetry.system_health === 'HEALTHY' && telemetry.database_health === 'UP';

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-white shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-6">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-slate-100">System Operator Dashboard</h2>
          <p className="text-xs text-slate-400 mt-1">Single-pane operational health & platform telemetry</p>
        </div>
        <div className="flex items-center space-x-2">
          <span
            className={`inline-block w-3 h-3 rounded-full ${
              isHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
            }`}
          />
          <span className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            {telemetry.system_health}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 1. Database Health */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Database Health</span>
          <div className="flex items-center justify-between mt-2">
            <span className="text-2xl font-bold text-slate-100">{telemetry.database_health}</span>
            <span className={`px-2 py-0.5 text-xs font-semibold rounded ${
              telemetry.database_health === 'UP' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
            }`}>
              PostgreSQL
            </span>
          </div>
        </div>

        {/* 2. Active Workflows */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Active Workflows</span>
          <div className="flex items-center justify-between mt-2">
            <span className="text-2xl font-bold text-slate-100">{telemetry.active_workflows}</span>
            <span className="px-2 py-0.5 text-xs font-semibold rounded bg-sky-500/20 text-sky-400">
              Temporal
            </span>
          </div>
        </div>

        {/* 3. Agent Health */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Agent Success Rate</span>
          <div className="flex items-center justify-between mt-2">
            <span className="text-2xl font-bold text-slate-100">{telemetry.agent_health.success_rate_percent}%</span>
            <span className="text-xs text-slate-400">
              {telemetry.agent_health.available} Avail / {telemetry.agent_health.busy} Busy
            </span>
          </div>
        </div>

        {/* 4. Queue Depth */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Queue Depth</span>
          <div className="flex items-center justify-between mt-2">
            <span className="text-2xl font-bold text-slate-100">
              {telemetry.queue_depth.agent_tasks + telemetry.queue_depth.nats_events}
            </span>
            <span className="text-xs text-slate-400">NATS + Outbox</span>
          </div>
        </div>

        {/* 5. Failed Tasks */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Failed Tasks</span>
          <div className="flex items-center justify-between mt-2">
            <span className={`text-2xl font-bold ${telemetry.failed_tasks > 0 ? 'text-rose-400' : 'text-slate-100'}`}>
              {telemetry.failed_tasks}
            </span>
            <span className="text-xs text-slate-400">Past window</span>
          </div>
        </div>

        {/* 6. Sandbox Failures */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Sandbox Failures</span>
          <div className="flex items-center justify-between mt-2">
            <span className={`text-2xl font-bold ${telemetry.sandbox_failures > 0 ? 'text-amber-400' : 'text-slate-100'}`}>
              {telemetry.sandbox_failures}
            </span>
            <span className="text-xs text-slate-400">Containers</span>
          </div>
        </div>

        {/* 7. API Errors */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">API Errors</span>
          <div className="flex items-center justify-between mt-2">
            <span className={`text-2xl font-bold ${telemetry.api_errors > 0 ? 'text-rose-400' : 'text-slate-100'}`}>
              {telemetry.api_errors}
            </span>
            <span className="text-xs text-slate-400">4xx / 5xx</span>
          </div>
        </div>

        {/* 8. Model Latency */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Model Latency (p95)</span>
          <div className="flex items-center justify-between mt-2">
            <span className="text-2xl font-bold text-slate-100">{telemetry.model_latency_p95_ms}ms</span>
            <span className="text-xs text-slate-400">LLM Inference</span>
          </div>
        </div>

        {/* 9. Realtime WebSockets */}
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <span className="text-xs font-medium text-slate-400">Active Realtime Sockets</span>
          <div className="flex items-center justify-between mt-2">
            <span className="text-2xl font-bold text-slate-100">
              {telemetry.agent_health.active_connections ?? 0}
            </span>
            <span className="text-xs text-slate-400">Connected Clients</span>
          </div>
        </div>
      </div>
    </div>
  );
};
