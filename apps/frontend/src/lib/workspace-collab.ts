import { HocuspocusProvider } from "@hocuspocus/provider";
import * as Y from "yjs";

export const COLLAB_URL = process.env.NEXT_PUBLIC_COLLAB_URL || "ws://localhost:1234";

export function openWorkspaceDocument(projectId: string, path: string) {
  const token = localStorage.getItem("agentspace_token") || "";
  const document = new Y.Doc();
  const provider = new HocuspocusProvider({
    url: COLLAB_URL,
    name: `${projectId}/${encodeURIComponent(path)}`,
    document,
    token,
  });
  return { document, provider, text: document.getText("content") };
}

export async function applyWorkspaceFile(projectId: string, path: string, content: string, expectedContent?: string) {
  const { document, provider, text } = openWorkspaceDocument(projectId, path);
  try {
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Could not sync ${path}`)), 12000);
      provider.on("synced", () => { clearTimeout(timer); resolve(); });
      provider.on("authenticationFailed", () => { clearTimeout(timer); reject(new Error("Workspace access denied")); });
    });
    if (expectedContent !== undefined && text.toString() !== expectedContent) {
      throw new Error(`${path} changed while the agent was working. Review and retry the task.`);
    }
    document.transact(() => {
      text.delete(0, text.length);
      text.insert(0, content);
    });
    // Give the provider a chance to flush the update before disconnecting.
    await new Promise((resolve) => setTimeout(resolve, 1500));
  } finally {
    provider.destroy();
    document.destroy();
  }
}
