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

type ApiFetchOptions = RequestInit & {
  redirectOnAuthError?: boolean;
};

export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { redirectOnAuthError = true, ...fetchOptions } = options;
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("agentspace_token")
      : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Generate Idempotency-Key for mutating HTTP verbs if not explicitly set
  const method = (fetchOptions.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers["Idempotency-Key"]) {
    headers["Idempotency-Key"] =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `idemp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }

  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;

  const res = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  if (redirectOnAuthError && res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("agentspace_token");
    localStorage.removeItem("agentspace_user");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (redirectOnAuthError && res.status === 403 && typeof window !== "undefined") {
    window.location.href = "/unauthorized";
    throw new Error("Forbidden");
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = typeof errorData?.message === "string"
      ? errorData.message
      : typeof errorData?.detail === "string"
        ? errorData.detail
        : `Request failed with status ${res.status}`;
    throw new ApiRequestError(
      message,
      res.status
    );
  }

  if (res.status === 204) {
    return null as T;
  }

  return (await res.json()) as T;
}
