import { ApiRequestError } from "@/lib/api-client";

type AuthFlow = "signin" | "signup" | "admin";

export function authErrorMessage(error: unknown, flow: AuthFlow): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      if (flow === "signup") return "Account creation was not authorized. Please try again.";
      return flow === "admin"
        ? "Incorrect administrator username or password. Please try again."
        : "Incorrect username or password. Please try again.";
    }
    if (error.status === 403) {
      if (flow === "signup") return "Account creation is unavailable for this request.";
      return flow === "admin"
        ? "This account does not have administrator access."
        : "This account requires the administrator sign-in page.";
    }
    if (error.status === 422) {
      return "Please check your details and try again.";
    }
    if (error.status >= 500) {
      return "The service is unavailable right now. Please try again shortly.";
    }
    return error.message;
  }
  if (error instanceof TypeError) {
    return "Could not connect to the server. Please try again.";
  }
  return flow === "signup"
    ? "Account creation failed. Please try again."
    : "Sign in failed. Please try again.";
}
