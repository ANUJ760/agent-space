"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getCredential } from "@/lib/agent-credentials";
import { generateContent } from "@/lib/gemini-client";
import { apiFetch } from "@/lib/api-client";
import { applyWorkspaceFile } from "@/lib/workspace-collab";
import type { Agent, Project } from "@/types/api";

interface RunAgentDialogProps {
  agent: Agent | null;
  project?: Project | null;
  initialPrompt?: string;
  onClose: () => void;
}

export function RunAgentDialog({ agent, project, initialPrompt = "", onClose }: RunAgentDialogProps) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [proposedFiles, setProposedFiles] = useState<Array<{ path: string; content: string }>>([]);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    setPrompt(initialPrompt);
    setOutput("");
    setError(null);
    setProposedFiles([]);
  }, [agent?.id, initialPrompt]);

  if (!agent) return null;

  const run = async () => {
    const credential = getCredential(agent.id);
    if (!credential) {
      setError("Add a Gemini API key for this agent on this browser first.");
      return;
    }
    if (agent.model_provider !== "gemini" || credential.provider !== "gemini") {
      setError("Browser runs currently support Gemini agents only.");
      return;
    }
    setRunning(true);
    setError(null);
    setOutput("");
    setProposedFiles([]);
    try {
      let context = project
        ? `Project: ${project.name}\nProject description: ${project.description || "None"}\n\n`
        : "";
      if (project) {
        const files = await apiFetch<Array<{ path: string; size: number }>>(`/api/v1/projects/${project.id}/workspace/files`);
        let budget = 40000;
        context += `Workspace files: ${files.map((file) => file.path).join(", ")}\n`;
        for (const file of files) {
          if (file.size > budget || file.size > 20000) continue;
          const entry = await apiFetch<{ content: string }>(`/api/v1/projects/${project.id}/workspace/file?path=${encodeURIComponent(file.path)}`);
          context += `\n--- ${file.path} ---\n${entry.content}\n`;
          budget -= file.size;
        }
        context += '\nReturn JSON only: {"summary":"what changed","files":[{"path":"relative/path","content":"complete new UTF-8 file content"}]}. Include only files you want to create or change. Do not return shell commands.\n';
      }
      const result = await generateContent({
        apiKey: credential.apiKey,
        baseUrl: credential.baseUrl,
        model: agent.model,
        systemPrompt: agent.system_prompt,
        prompt: `${context}\nRequest: ${prompt.trim()}`,
        maxTokens: 16384,
      });
      const raw = result.text || "Gemini returned no text. Try a different prompt.";
      if (project) {
        try {
          const parsed = JSON.parse(raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "")) as { summary?: string; files?: Array<{ path: string; content: string }> };
          if (Array.isArray(parsed.files) && parsed.files.every((file) => typeof file.path === "string" && typeof file.content === "string")) {
            setProposedFiles(parsed.files);
            setOutput(parsed.summary || "Proposed file changes");
          } else { setOutput(raw); }
        } catch { setOutput(raw); }
      } else { setOutput(raw); }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The agent could not complete the request.");
    } finally {
      setRunning(false);
    }
  };

  const applyChanges = async () => {
    if (!project) return;
    setApplying(true); setError(null);
    try {
      const existing = await apiFetch<Array<{ path: string }>>(`/api/v1/projects/${project.id}/workspace/files`);
      const existingPaths = new Set(existing.map((entry) => entry.path));
      for (const file of proposedFiles) {
        if (!existingPaths.has(file.path)) {
          await apiFetch(`/api/v1/projects/${project.id}/workspace/files`, { method: "POST", body: JSON.stringify({ path: file.path, content: "" }) });
          existingPaths.add(file.path);
        }
        await applyWorkspaceFile(project.id, file.path, file.content);
      }
      setOutput(`Applied ${proposedFiles.length} file change${proposedFiles.length === 1 ? "" : "s"} to the shared workspace.`);
      setProposedFiles([]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not apply file changes"); }
    finally { setApplying(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-label={`Run ${agent.name}`} className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border bg-card p-6 shadow-xl space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Run {agent.name}</h2>
            <p className="text-xs text-muted-foreground">{agent.model} · Runs in this browser with your API key. {project ? "Workspace file contents are sent to Gemini for this run. Review edits before applying." : "Keep this page open until it finishes."}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close run dialog"><X className="w-4 h-4" /></Button>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="agent-run-prompt" className="text-xs font-semibold">Request</label>
          <textarea id="agent-run-prompt" rows={5} value={prompt} onChange={(event) => setPrompt(event.target.value)} className="w-full rounded-md border bg-background p-3 text-sm" placeholder="Describe what you want this agent to do..." />
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button onClick={run} disabled={running || !prompt.trim()} className="gap-2">
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {running ? "Running..." : "Run in browser"}
        </Button>
        {output && (
          <div className="space-y-2 border-t pt-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Result</h3>
              <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(output)}>Copy</Button>
            </div>
            <pre className="whitespace-pre-wrap break-words rounded-md bg-muted/40 p-4 text-sm font-sans">{output}</pre>
            {proposedFiles.length > 0 && <div className="space-y-2"><p className="text-xs text-muted-foreground">Review these proposed files before applying. Other collaborators will see the edits immediately.</p>{proposedFiles.map((file) => <details key={file.path} className="border p-2 text-xs"><summary className="cursor-pointer font-mono">{file.path}</summary><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all p-2">{file.content}</pre></details>)}<Button onClick={applyChanges} disabled={applying}>{applying ? "Applying..." : `Apply ${proposedFiles.length} file changes`}</Button></div>}
          </div>
        )}
      </div>
    </div>
  );
}
