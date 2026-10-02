"use client";

import { AlertCircle } from "lucide-react";

export function AuthErrorAlert({ title, message }: { title: string; message: string }) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="auth-error-enter flex items-start gap-3 rounded-2xl border border-rose-400/40 bg-rose-950/70 px-4 py-3.5 text-rose-100 shadow-[0_12px_30px_-18px_rgba(244,63,94,0.65)]"
    >
      <span className="auth-error-icon mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-rose-400/15 text-rose-300">
        <AlertCircle className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold leading-5">{title}</p>
        <p className="mt-0.5 text-sm leading-5 text-rose-200/90">{message}</p>
      </div>
    </div>
  );
}
