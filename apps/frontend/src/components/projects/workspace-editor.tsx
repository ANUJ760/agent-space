"use client";

import { useEffect, useRef, useState } from "react";
import { EditorView, keymap, lineNumbers, highlightActiveLine } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { javascript } from "@codemirror/lang-javascript";
import { yCollab } from "y-codemirror.next";
import { openWorkspaceDocument } from "@/lib/workspace-collab";

const colors = ["#38bdf8", "#a78bfa", "#f472b6", "#fbbf24", "#34d399"];

export function WorkspaceEditor({ projectId, path }: { projectId: string; path: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Connecting...");
  const [people, setPeople] = useState<Array<{ name: string; color: string }>>([]);

  useEffect(() => {
    if (!host.current) return;
    const { document, provider, text } = openWorkspaceDocument(projectId, path);
    const awareness = provider.awareness!;
    const stored = localStorage.getItem("agentspace_user");
    let name = "Collaborator";
    try { name = JSON.parse(stored || "{}").display_name || JSON.parse(stored || "{}").username || name; } catch { /* anonymous label */ }
    const color = colors[Math.abs([...name].reduce((sum, char) => sum + char.charCodeAt(0), 0)) % colors.length];
    awareness.setLocalStateField("user", { name, color });
    const updatePeople = () => {
      setPeople(Array.from(awareness.getStates().values())
        .map((state) => state.user as { name?: string; color?: string } | undefined)
        .filter((user): user is { name: string; color: string } => !!user?.name && !!user?.color));
    };
    awareness.on("change", updatePeople);
    provider.on("synced", () => setStatus("Live · saved automatically"));
    provider.on("disconnect", () => setStatus("Disconnected · reconnecting"));
    provider.on("authenticationFailed", () => setStatus("Access denied"));
    const view = new EditorView({
      state: EditorState.create({
        extensions: [
          lineNumbers(), highlightActiveLine(), history(), keymap.of([...defaultKeymap, ...historyKeymap]),
          path.endsWith(".md") ? markdown() : javascript(),
          yCollab(text, awareness),
          EditorView.lineWrapping,
          EditorView.theme({
            "&": { minHeight: "450px", background: "transparent", color: "inherit", fontSize: "13px" },
            ".cm-content": { fontFamily: "monospace", padding: "12px" },
            ".cm-gutters": { background: "transparent", color: "#888", borderRight: "1px solid #5553" },
            ".cm-scroller": { overflow: "auto" },
          }),
        ],
      }),
      parent: host.current,
    });
    return () => {
      view.destroy();
      awareness.off("change", updatePeople);
      provider.destroy();
      document.destroy();
    };
  }, [projectId, path]);

  return <div className="space-y-2">
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
      <span>{status}</span>
      <div className="flex gap-2">{people.map((person, index) => <span key={`${person.name}-${index}`} style={{ color: person.color }}>● {person.name}</span>)}</div>
    </div>
    <div ref={host} className="overflow-hidden border border-border/80 bg-card" />
  </div>;
}
