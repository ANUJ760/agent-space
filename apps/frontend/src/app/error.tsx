"use client";

import React, { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { AlertTriangle, RotateCcw } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log client error to monitoring or console
    console.error("Application error boundary triggered:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className="w-16 h-16 rounded-full bg-destructive/10 text-destructive flex items-center justify-center mb-6">
        <AlertTriangle className="w-8 h-8" />
      </div>
      <h2 className="text-2xl font-bold tracking-tight text-foreground">
        Something went wrong
      </h2>
      <p className="text-muted-foreground mt-2 max-w-md text-sm">
        An unexpected error occurred while rendering the page. You can try
        reloading or returning to the dashboard.
      </p>
      {error.digest && (
        <p className="mt-2 text-xs font-mono text-muted-foreground bg-muted px-2 py-1 rounded">
          Error Digest: {error.digest}
        </p>
      )}
      <div className="flex items-center gap-3 mt-6">
        <Button onClick={() => reset()} className="gap-2">
          <RotateCcw className="w-4 h-4" />
          <span>Try again</span>
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            window.location.href = "/";
          }}
        >
          Go to Dashboard
        </Button>
      </div>
    </div>
  );
}
