"use client";

import React from "react";

export interface ProjectProgressData {
  project_id: string;
  total_progress_pct: number;
  total_tasks: number;
  completed_tasks: number;
  active_tasks: number;
  blocked_tasks: number;
  todo_tasks: number;
  agent_activity_count?: number;
}

interface ProjectProgressWidgetProps {
  progress: ProjectProgressData;
}

export function ProjectProgressWidget({ progress }: ProjectProgressWidgetProps) {
  const pct = Math.min(100, Math.max(0, Math.round(progress.total_progress_pct)));

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 text-slate-200 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">Project Progress</h3>
          <p className="text-xs text-slate-400">Weighted task completion rate</p>
        </div>
        <div className="text-2xl font-bold font-mono text-indigo-400">
          {pct}%
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden">
        <div
          className="bg-gradient-to-r from-indigo-500 to-emerald-400 h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Breakdown counters */}
      <div className="grid grid-cols-4 gap-2 pt-1 text-center font-mono">
        <div className="p-2 rounded bg-slate-800/40 border border-slate-800">
          <div className="text-[10px] text-slate-400 uppercase font-sans">Done</div>
          <div className="text-sm font-bold text-emerald-400">{progress.completed_tasks}</div>
        </div>
        <div className="p-2 rounded bg-slate-800/40 border border-slate-800">
          <div className="text-[10px] text-slate-400 uppercase font-sans">Active</div>
          <div className="text-sm font-bold text-sky-400">{progress.active_tasks}</div>
        </div>
        <div className="p-2 rounded bg-slate-800/40 border border-slate-800">
          <div className="text-[10px] text-slate-400 uppercase font-sans">Blocked</div>
          <div className="text-sm font-bold text-rose-400">{progress.blocked_tasks}</div>
        </div>
        <div className="p-2 rounded bg-slate-800/40 border border-slate-800">
          <div className="text-[10px] text-slate-400 uppercase font-sans">Total</div>
          <div className="text-sm font-bold text-slate-300">{progress.total_tasks}</div>
        </div>
      </div>
    </div>
  );
}
