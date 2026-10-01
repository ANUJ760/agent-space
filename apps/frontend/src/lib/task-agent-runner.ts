import { apiFetch } from "@/lib/api-client";
import { getCredential } from "@/lib/agent-credentials";
import { generateAgentText } from "@/lib/agent-provider";
import { applyWorkspaceFile } from "@/lib/workspace-collab";
import type { Agent, Project, Task } from "@/types/api";

type FileEntry = { path: string; size: number };
type ProposedFile = { path: string; content: string };

function parseJson(raw: string): Record<string, unknown> {
  const parsed = JSON.parse(raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, ""));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Agent returned invalid JSON");
  return parsed as Record<string, unknown>;
}

async function updateProgress(task: Task, stage: string, extra: Record<string, unknown> = {}): Promise<void> {
  await apiFetch(`/api/v1/tasks/${task.id}`, {
    method: "PATCH",
    body: JSON.stringify({ result: { stage, ...extra }, error_message: "" }),
  });
}

async function assertAssignment(task: Task, agent: Agent): Promise<void> {
  const current = await apiFetch<Task>(`/api/v1/tasks/${task.id}`);
  if (current.assigned_agent_id !== agent.id || current.status !== "IN_PROGRESS") {
    throw new Error("A collaborator changed this task while the agent was working. Agent edits were stopped.");
  }
}

export async function runAssignedTask(project: Project, task: Task, agent: Agent): Promise<void> {
  const credential = agent.model_provider === "default" ? null : getCredential(agent.id);
  if (agent.model_provider !== "default" && (!credential || credential.provider !== agent.model_provider)) {
    throw new Error(`Add this ${agent.model_provider} agent's API key in this browser before assigning work.`);
  }
  if (task.status === "CLAIMED") {
    await apiFetch(`/api/v1/tasks/${task.id}/transition`, { method: "POST", body: JSON.stringify({ status: "IN_PROGRESS", reason: "Agent started in browser" }) });
  }
  await updateProgress(task, "Planner selecting files");
  const listing = await apiFetch<FileEntry[]>(`/api/v1/projects/${project.id}/workspace/files`);
  const paths = listing.map((entry) => entry.path);
  const suggested = Array.isArray(task.context?.suggested_files) ? task.context.suggested_files : [];
  const planPrompt = `You are the project planner. Coordinate a worker on this task. Choose specific relative file paths to create or edit. Return JSON only: {"instructions":"...","files":["relative/path"]}.\nProject: ${project.name}\nTask: ${task.title}\nDescription: ${task.description || ""}\nSuggested files: ${suggested.join(", ")}\nExisting files: ${paths.join(", ")}`;
  const planText = (await apiFetch<{ text: string }>("/api/v1/agents/default/generate", { method: "POST", body: JSON.stringify({ prompt: planPrompt, max_tokens: 1024 }) })).text;
  const plan = parseJson(planText);
  const selected = Array.isArray(plan.files) ? plan.files.filter((path): path is string => typeof path === "string").slice(0, 12) : [];
  if (!selected.length) throw new Error("Planner did not select any files");
  await updateProgress(task, "Agent writing files", { files: selected });

  const snapshots = new Map<string, string>();
  let context = `Project: ${project.name}\nProject brief: ${project.description || ""}\nTask: ${task.title}\nTask description: ${task.description || ""}\nPlanner instructions: ${String(plan.instructions || "")}\nFiles assigned: ${selected.join(", ")}\n`;
  let budget = 60000;
  for (const path of selected) {
    const listed = listing.find((file) => file.path === path);
    if (!listed || listed.size > 20000 || listed.size > budget) continue;
    const file = await apiFetch<{ content: string }>(`/api/v1/projects/${project.id}/workspace/file?path=${encodeURIComponent(path)}`);
    snapshots.set(path, file.content);
    context += `\n--- ${path} ---\n${file.content}\n`;
    budget -= listed.size;
  }
  context += '\nReturn JSON only: {"summary":"what changed","files":[{"path":"relative/path","content":"complete new UTF-8 file content"}]}. Change only assigned files. Do not return shell commands.\n';
  const raw = agent.model_provider === "default"
    ? (await apiFetch<{ text: string }>("/api/v1/agents/default/generate", { method: "POST", body: JSON.stringify({ prompt: context, system_prompt: agent.system_prompt, max_tokens: 16384 }) })).text
    : await generateAgentText({ provider: credential!.provider, apiKey: credential!.apiKey, baseUrl: credential!.baseUrl, model: agent.model, systemPrompt: agent.system_prompt, prompt: context, maxTokens: 16384 });
  const result = parseJson(raw);
  const files = result.files;
  if (!Array.isArray(files) || !files.length || !files.every((file): file is ProposedFile => Boolean(file) && typeof file.path === "string" && typeof file.content === "string" && selected.includes(file.path))) {
    throw new Error("Agent did not return valid changes to the assigned files");
  }
  await assertAssignment(task, agent);
  await updateProgress(task, "Applying shared edits", { files: files.map((file) => file.path) });
  for (const file of files) {
    await assertAssignment(task, agent);
    if (snapshots.has(file.path)) {
      const current = await apiFetch<{ content: string }>(`/api/v1/projects/${project.id}/workspace/file?path=${encodeURIComponent(file.path)}`);
      if (current.content !== snapshots.get(file.path)) throw new Error(`${file.path} changed while the agent was working. Review and retry the task.`);
    } else {
      await apiFetch(`/api/v1/projects/${project.id}/workspace/files`, { method: "POST", body: JSON.stringify({ path: file.path, content: "" }) });
    }
    await applyWorkspaceFile(project.id, file.path, file.content, snapshots.get(file.path) ?? "");
  }
  await apiFetch(`/api/v1/projects/${project.id}/workspace/checkpoints`, { method: "POST", body: JSON.stringify({ message: `Agent task: ${task.title}` }) });
  await updateProgress(task, "Ready for review", { summary: String(result.summary || "Changes applied"), files: files.map((file) => file.path) });
  await apiFetch(`/api/v1/tasks/${task.id}/transition`, { method: "POST", body: JSON.stringify({ status: "REVIEW", reason: "Agent changes applied to shared workspace" }) });
}
