/**
 * Typed API Client for Agent Space Backend.
 *
 * Automatically attaches:
 * - Authorization: Bearer <token>
 * - Idempotency-Key on mutating requests (POST, PUT, PATCH, DELETE)
 * - Content-Type: application/json
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("agentspace_token")
      : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Generate Idempotency-Key for mutating HTTP verbs if not explicitly set
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers["Idempotency-Key"]) {
    headers["Idempotency-Key"] =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `idemp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }

  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("agentspace_token");
    localStorage.removeItem("agentspace_user");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (res.status === 403 && typeof window !== "undefined") {
    window.location.href = "/unauthorized";
    throw new Error("Forbidden");
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(
      errorData?.message || errorData?.detail || `API Request failed with status ${res.status}`
    );
  }

  if (res.status === 204) {
    return null as T;
  }

  return (await res.json()) as T;
}
