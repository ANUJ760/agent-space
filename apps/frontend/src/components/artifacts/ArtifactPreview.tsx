"use client";

import React from "react";

export interface ArtifactPreviewData {
  artifact_id: string;
  artifact_type: "CODE" | "IMAGE" | "DOCUMENT" | "LOGS" | "TEST_RESULTS" | "DIFF" | "OTHER";
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256_hash: string;
  preview_content?: string | Record<string, unknown> | null;
  is_truncated?: boolean;
  presigned_url?: string | null;
  metadata_json?: Record<string, unknown>;
}

interface ArtifactPreviewProps {
  artifact: ArtifactPreviewData;
  onClose?: () => void;
}

export function ArtifactPreview({ artifact, onClose }: ArtifactPreviewProps) {
  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-lg overflow-hidden text-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-slate-800/80 border-b border-slate-700">
        <div className="flex items-center space-x-3">
          <span className="px-2 py-0.5 text-xs font-mono rounded bg-blue-900/60 text-blue-300 border border-blue-700">
            {artifact.artifact_type}
          </span>
          <span className="font-semibold text-sm truncate max-w-xs">{artifact.filename}</span>
          <span className="text-xs text-slate-400">({formatSize(artifact.size_bytes)})</span>
        </div>
        <div className="flex items-center space-x-2">
          {artifact.presigned_url && (
            <a
              href={artifact.presigned_url}
              download={artifact.filename}
              className="text-xs px-2.5 py-1 bg-slate-700 hover:bg-slate-600 rounded text-slate-200 transition-colors"
            >
              Download
            </a>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="text-xs px-2 py-1 text-slate-400 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Truncation notice */}
      {artifact.is_truncated && (
        <div className="bg-amber-950/60 border-b border-amber-800/50 px-4 py-1.5 text-xs text-amber-300 flex items-center justify-between">
          <span>⚠️ Preview truncated to protect performance. Download the full file to view complete contents.</span>
        </div>
      )}

      {/* Body preview */}
      <div className="flex-1 overflow-auto p-4 font-mono text-xs">
        {artifact.artifact_type === "IMAGE" ? (
          <div className="flex items-center justify-center p-6 bg-slate-950 rounded">
            {artifact.presigned_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={artifact.presigned_url}
                alt={artifact.filename}
                className="max-h-[500px] max-w-full rounded object-contain border border-slate-800"
              />
            ) : (
              <div className="text-slate-500">Image preview unavailable without signed URL</div>
            )}
          </div>
        ) : artifact.artifact_type === "DIFF" ? (
          <pre className="p-3 bg-slate-950 rounded overflow-x-auto text-slate-300">
            {String(artifact.preview_content || "")
              .split("\n")
              .map((line, idx) => {
                let color = "text-slate-300";
                if (line.startsWith("+") && !line.startsWith("+++")) color = "text-emerald-400 bg-emerald-950/30";
                else if (line.startsWith("-") && !line.startsWith("---")) color = "text-rose-400 bg-rose-950/30";
                else if (line.startsWith("@")) color = "text-cyan-400";
                return (
                  <div key={idx} className={`${color} px-1 leading-5 font-mono`}>
                    {line}
                  </div>
                );
              })}
          </pre>
        ) : artifact.artifact_type === "TEST_RESULTS" && typeof artifact.preview_content === "object" ? (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
              <div className="p-3 bg-slate-800/50 rounded border border-slate-700">
                <div className="text-slate-400 text-xs">Total</div>
                <div className="text-lg font-bold text-white">
                  {String((artifact.preview_content as any)?.total || 0)}
                </div>
              </div>
              <div className="p-3 bg-emerald-950/30 rounded border border-emerald-800/40">
                <div className="text-emerald-400 text-xs">Passed</div>
                <div className="text-lg font-bold text-emerald-300">
                  {String((artifact.preview_content as any)?.passed || 0)}
                </div>
              </div>
              <div className="p-3 bg-rose-950/30 rounded border border-rose-800/40">
                <div className="text-rose-400 text-xs">Failed</div>
                <div className="text-lg font-bold text-rose-300">
                  {String((artifact.preview_content as any)?.failed || 0)}
                </div>
              </div>
            </div>
            <pre className="p-3 bg-slate-950 rounded overflow-x-auto text-slate-300">
              {JSON.stringify(artifact.preview_content, null, 2)}
            </pre>
          </div>
        ) : artifact.artifact_type === "LOGS" ? (
          <pre className="p-3 bg-black rounded border border-slate-800 text-emerald-400 overflow-x-auto leading-relaxed">
            {String(artifact.preview_content || "")}
          </pre>
        ) : (
          <pre className="p-3 bg-slate-950 rounded border border-slate-800 text-slate-200 overflow-x-auto whitespace-pre-wrap">
            {String(artifact.preview_content || "")}
          </pre>
        )}
      </div>
    </div>
  );
}
