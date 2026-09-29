"use client";

import React, { useState } from "react";

export interface PendingHumanRequest {
  id: string;
  request_type: "APPROVAL" | "DECISION" | "HELP" | "TAKEOVER";
  prompt: string;
  options?: string[];
  context?: Record<string, unknown>;
  status: "PENDING" | "RESOLVED" | "CANCELLED";
}

interface HumanRequestModalProps {
  taskId: string;
  request: PendingHumanRequest;
  onRespond: (action: string, feedback?: string, selectedOption?: string) => Promise<void>;
  onClose: () => void;
}

export function HumanRequestModal({
  taskId,
  request,
  onRespond,
  onClose,
}: HumanRequestModalProps) {
  const [selectedOption, setSelectedOption] = useState<string>(request.options?.[0] || "");
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (action: string) => {
    setSubmitting(true);
    try {
      await onRespond(action, feedback, selectedOption);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  const getBadgeStyle = () => {
    switch (request.request_type) {
      case "APPROVAL":
        return "bg-amber-900/60 text-amber-300 border-amber-700";
      case "DECISION":
        return "bg-indigo-900/60 text-indigo-300 border-indigo-700";
      case "HELP":
        return "bg-blue-900/60 text-blue-300 border-blue-700";
      case "TAKEOVER":
        return "bg-rose-900/60 text-rose-300 border-rose-700";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-2xl max-w-lg w-full overflow-hidden text-slate-200">
        {/* Header */}
        <div className="px-5 py-4 bg-slate-800/80 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <span className={`px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider rounded border ${getBadgeStyle()}`}>
              {request.request_type} REQUIRED
            </span>
            <span className="text-xs text-slate-400 font-mono">Task #{taskId.slice(0, 8)}</span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          <div className="space-y-1.5">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Agent Question / Request</div>
            <p className="text-sm text-slate-100 font-medium leading-relaxed bg-slate-950 p-3 rounded-lg border border-slate-800">
              {request.prompt}
            </p>
          </div>

          {/* Options for DECISION */}
          {request.request_type === "DECISION" && request.options && request.options.length > 0 && (
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Choose Option</label>
              <div className="space-y-1.5">
                {request.options.map((opt, i) => (
                  <label
                    key={i}
                    className={`flex items-center space-x-2.5 p-2.5 rounded-lg border text-sm cursor-pointer transition-colors ${
                      selectedOption === opt
                        ? "bg-indigo-950/60 border-indigo-600 text-indigo-200"
                        : "bg-slate-800/50 border-slate-700 hover:bg-slate-800 text-slate-300"
                    }`}
                  >
                    <input
                      type="radio"
                      name="decision-option"
                      value={opt}
                      checked={selectedOption === opt}
                      onChange={() => setSelectedOption(opt)}
                      className="text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>{opt}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Feedback textarea */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              {request.request_type === "HELP" ? "Instructions / Solution" : "Notes & Feedback (Optional)"}
            </label>
            <textarea
              rows={3}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Provide context or guidance for the agent..."
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none resize-none"
            />
          </div>
        </div>

        {/* Footer Actions */}
        <div className="px-5 py-3.5 bg-slate-800/60 border-t border-slate-700 flex justify-end space-x-2.5">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded text-slate-400 hover:text-white transition-colors"
          >
            Dismiss
          </button>

          {request.request_type === "APPROVAL" ? (
            <>
              <button
                disabled={submitting}
                onClick={() => handleSubmit("REJECT")}
                className="px-3.5 py-1.5 text-xs font-medium bg-rose-700 hover:bg-rose-600 text-white rounded transition-colors disabled:opacity-50"
              >
                Reject
              </button>
              <button
                disabled={submitting}
                onClick={() => handleSubmit("APPROVE")}
                className="px-3.5 py-1.5 text-xs font-medium bg-emerald-700 hover:bg-emerald-600 text-white rounded transition-colors disabled:opacity-50"
              >
                Approve
              </button>
            </>
          ) : request.request_type === "TAKEOVER" ? (
            <button
              disabled={submitting}
                onClick={() => handleSubmit("TAKEOVER")}
                className="px-4 py-1.5 text-xs font-medium bg-rose-700 hover:bg-rose-600 text-white rounded transition-colors disabled:opacity-50"
              >
                Take Over Task
              </button>
          ) : (
            <button
              disabled={submitting}
              onClick={() => handleSubmit(request.request_type === "DECISION" ? "CHOSEN" : "ANSWER")}
              className="px-4 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded transition-colors disabled:opacity-50"
            >
              Submit Response
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
