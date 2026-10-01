"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, FilePlus2, GitCommitHorizontal, Github, RefreshCw, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WorkspaceEditor } from "@/components/projects/workspace-editor";
import { RunAgentDialog } from "@/components/agents/run-agent-dialog";
import { apiFetch } from "@/lib/api-client";
import type { Agent, Project } from "@/types/api";

interface FileEntry { path: string; size: number }
interface Checkpoint { commit: string; message: string; date: string }

export default function ProjectFilesPage() {
  const projectId = useParams()?.projectId as string;
  const [project, setProject] = useState<Project | null>(null);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runningAgent, setRunningAgent] = useState<Agent | null>(null);
  const [newPath, setNewPath] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [gitToken, setGitToken] = useState("");
  const [gitUsername, setGitUsername] = useState("x-access-token");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const [p, f, c, a] = await Promise.all([
        apiFetch<Project>(`/api/v1/projects/${projectId}`),
        apiFetch<FileEntry[]>(`/api/v1/projects/${projectId}/workspace/files`),
        apiFetch<Checkpoint[]>(`/api/v1/projects/${projectId}/workspace/checkpoints`),
        apiFetch<Agent[]>(`/api/v1/projects/${projectId}/agents`),
      ]);
      setProject(p); setFiles(f); setCheckpoints(c); setAgents(a);
      setRepoUrl(p.repository_url || "");
      setSelected((current) => current && f.some((item) => item.path === current) ? current : f[0]?.path || null);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not load workspace"); }
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  const perform = async (action: () => Promise<void>, success: string) => {
    setBusy(true); setNotice("");
    try { await action(); setNotice(success); await refresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Operation failed"); }
    finally { setBusy(false); }
  };

  const createFile = () => perform(async () => {
    const path = newPath.trim();
    await apiFetch(`/api/v1/projects/${projectId}/workspace/files`, { method: "POST", body: JSON.stringify({ path }) });
    setSelected(path); setNewPath("");
  }, "File created. Everyone in the project can edit it live.");

  const checkpoint = () => perform(async () => {
    await apiFetch(`/api/v1/projects/${projectId}/workspace/checkpoints`, {
      method: "POST", body: JSON.stringify({ message: message.trim() || "Workspace checkpoint" }),
    });
    setMessage("");
  }, "Checkpoint saved.");

  const saveRemote = () => perform(async () => {
    await apiFetch(`/api/v1/projects/${projectId}`, {
      method: "PATCH", body: JSON.stringify({ repository_url: repoUrl.trim() || null }),
    });
  }, "Repository URL saved.");

  const push = () => perform(async () => {
    await apiFetch(`/api/v1/projects/${projectId}/workspace/push`, {
      method: "POST", body: JSON.stringify({ token: gitToken, username: gitUsername }),
    });
    setGitToken("");
  }, "Latest checkpoint pushed to Git.");

  return <div className="mx-auto max-w-7xl space-y-5 pb-12">
    <Link href={`/projects/${projectId}`} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /> Back to project</Link>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-2xl font-bold">{project?.name || "Project"} files</h1><p className="text-sm text-muted-foreground">Shared code and documents. Edits sync live and save automatically.</p></div>
      <Button variant="outline" onClick={refresh} disabled={busy}><RefreshCw className="mr-2 h-4 w-4" /> Refresh</Button>
    </div>
    {notice && <p role="status" className="border border-border bg-card p-3 text-sm">{notice}</p>}
    <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
      <aside className="space-y-4 border border-border/80 bg-card p-3">
        <h2 className="text-sm font-semibold">Files</h2>
        <div className="space-y-1">{files.map((file) => <button key={file.path} type="button" onClick={() => setSelected(file.path)} className={`block w-full truncate px-2 py-2 text-left text-xs font-mono hover:bg-muted ${selected === file.path ? "bg-primary/10 text-primary" : ""}`}>{file.path}</button>)}</div>
        <div className="space-y-2 border-t pt-3"><input aria-label="New file path" placeholder="src/index.ts" value={newPath} onChange={(e) => setNewPath(e.target.value)} className="w-full border bg-background px-2 py-2 text-xs" /><Button size="sm" variant="outline" onClick={createFile} disabled={busy || !newPath.trim()}><FilePlus2 className="mr-2 h-4 w-4" /> New file</Button></div>
        <div className="space-y-2 border-t pt-3"><h3 className="text-xs font-semibold">Run an agent</h3>{agents.map((agent) => <Button key={agent.id} size="sm" variant="ghost" className="w-full justify-start truncate" onClick={() => setRunningAgent(agent)}><Bot className="mr-2 h-4 w-4" />{agent.name}</Button>)}</div>
      </aside>
      <section className="min-w-0">{selected ? <><div className="border border-b-0 border-border/80 bg-card px-3 py-2 font-mono text-xs">{selected}</div><WorkspaceEditor key={selected} projectId={projectId} path={selected} /></> : <div className="border border-border/80 bg-card p-8 text-sm text-muted-foreground">Create a file to start collaborating.</div>}</section>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="space-y-3 border border-border/80 bg-card p-4"><h2 className="font-semibold">Git checkpoints</h2><p className="text-xs text-muted-foreground">Automatic checkpoint every 5 minutes when files change.</p><div className="flex gap-2"><input aria-label="Commit message" placeholder="What changed?" value={message} onChange={(e) => setMessage(e.target.value)} className="min-w-0 flex-1 border bg-background px-2 text-sm" /><Button onClick={checkpoint} disabled={busy}><GitCommitHorizontal className="mr-2 h-4 w-4" /> Checkpoint</Button></div><div className="space-y-2">{checkpoints.map((item) => <div key={item.commit} className="border-t pt-2 text-xs"><span className="font-mono text-primary">{item.commit.slice(0, 8)}</span> {item.message}<p className="text-muted-foreground">{new Date(item.date).toLocaleString()}</p></div>)}</div></section>
      <section className="space-y-3 border border-border/80 bg-card p-4"><h2 className="font-semibold">Push to Git</h2><p className="text-xs text-muted-foreground">Use an HTTPS repository on an allowed host. Your Git token is used once for the push and is not saved.</p><div className="flex gap-2"><input aria-label="Repository URL" placeholder="https://github.com/you/repo.git" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} className="min-w-0 flex-1 border bg-background px-2 text-xs" /><Button variant="outline" onClick={saveRemote} disabled={busy}>Save URL</Button></div><input aria-label="Git username" placeholder="Git username" value={gitUsername} onChange={(e) => setGitUsername(e.target.value)} className="w-full border bg-background px-2 py-2 text-sm" /><input aria-label="Git token" type="password" placeholder="Git personal access token" value={gitToken} onChange={(e) => setGitToken(e.target.value)} className="w-full border bg-background px-2 py-2 text-sm" /><Button onClick={push} disabled={busy || !gitToken || !project?.repository_url}><Github className="mr-2 h-4 w-4" /> Push checkpoint</Button></section>
    </div>
    <RunAgentDialog agent={runningAgent} project={project} onClose={() => { setRunningAgent(null); refresh(); }} />
  </div>;
}
