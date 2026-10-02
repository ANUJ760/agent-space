import type { Task } from "@/types/api";

type ProjectEvent = {
  event: string;
  payload?: Task | { id: string };
};

function eventUrl(projectId: string, token: string): string {
  const configured = process.env.NEXT_PUBLIC_API_URL || "";
  const base = configured
    ? configured.replace(/^http/, "ws").replace(/\/$/, "")
    : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
  return `${base}/api/v1/ws/projects/${projectId}?token=${encodeURIComponent(token)}`;
}

export function subscribeToProjectTasks(
  projectId: string,
  onTask: (task: Task) => void,
  onDelete?: (taskId: string) => void,
): () => void {
  let stopped = false;
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let heartbeat: ReturnType<typeof setInterval> | null = null;

  const connect = () => {
    const token = localStorage.getItem("agentspace_token");
    if (stopped || !token) return;
    socket = new WebSocket(eventUrl(projectId, token));
    socket.onopen = () => {
      heartbeat = setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: "ping" }));
      }, 25000);
    };
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as ProjectEvent;
        if (event.event === "task.snapshot" && event.payload && "status" in event.payload) {
          onTask(event.payload as Task);
        } else if (event.event === "task.deleted" && event.payload && "id" in event.payload) {
          onDelete?.(event.payload.id);
        }
      } catch { /* Ignore malformed or unrelated events. */ }
    };
    socket.onclose = () => {
      if (heartbeat) clearInterval(heartbeat);
      heartbeat = null;
      if (!stopped) retry = setTimeout(connect, 1500);
    };
  };

  connect();
  return () => {
    stopped = true;
    if (retry) clearTimeout(retry);
    if (heartbeat) clearInterval(heartbeat);
    socket?.close();
  };
}
