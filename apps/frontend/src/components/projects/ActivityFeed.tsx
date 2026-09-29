"use client";

import React from "react";

export interface ActivityFeedItemData {
  id: string;
  project_id: string;
  task_id?: string | null;
  agent_id?: string | null;
  agent_name: string;
  agent_role: string;
  action: string;
  summary: string;
  timestamp: string;
}

interface ActivityFeedProps {
  items: ActivityFeedItemData[];
  loading?: boolean;
}

export function ActivityFeed({ items, loading }: ActivityFeedProps) {
  if (loading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse flex items-start space-x-3 bg-slate-800/40 p-3 rounded-lg border border-slate-800">
            <div className="w-8 h-8 rounded-full bg-slate-700" />
            <div className="flex-1 space-y-2">
              <div className="h-3 w-1/3 bg-slate-700 rounded" />
              <div className="h-4 w-2/3 bg-slate-700 rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500 text-sm">
        No recent agent activities in this project.
      </div>
    );
  }

  const getActionColor = (action: string) => {
    switch (action) {
      case "READ_FILE":
        return "text-sky-400 bg-sky-950/40 border-sky-800/50";
      case "RUN_TESTS":
        return "text-amber-400 bg-amber-950/40 border-amber-800/50";
      case "GIT_COMMIT":
        return "text-emerald-400 bg-emerald-950/40 border-emerald-800/50";
      case "REVIEW":
        return "text-purple-400 bg-purple-950/40 border-purple-800/50";
      case "HUMAN_INPUT":
        return "text-rose-400 bg-rose-950/40 border-rose-800/50";
      default:
        return "text-slate-300 bg-slate-800/50 border-slate-700";
    }
  };

  return (
    <div className="divide-y divide-slate-800/60 max-h-[600px] overflow-y-auto">
      {items.map((item) => (
        <div key={item.id} className="p-3.5 hover:bg-slate-800/30 transition-colors flex items-start space-x-3">
          {/* Avatar / Icon */}
          <div className="w-7 h-7 rounded-lg bg-indigo-950/80 border border-indigo-700/50 flex items-center justify-center text-xs font-bold text-indigo-300 shrink-0">
            {item.agent_name.slice(0, 1).toUpperCase()}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-200 truncate">{item.agent_name}</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                {item.agent_role}
              </span>
              <span className="text-[10px] text-slate-500 ml-auto shrink-0">
                {new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </span>
            </div>

            {/* Safe Summary */}
            <div className="mt-1 flex items-center space-x-2">
              <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded border ${getActionColor(item.action)}`}>
                {item.action}
              </span>
              <span className="text-xs text-slate-300 font-medium truncate">{item.summary}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
