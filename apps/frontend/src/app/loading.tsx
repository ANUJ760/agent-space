import React from "react";

export default function Loading() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-pulse">
      {/* Title skeleton */}
      <div className="space-y-2">
        <div className="h-8 w-64 bg-muted rounded-md" />
        <div className="h-4 w-96 bg-muted/60 rounded-md" />
      </div>

      {/* Cards grid skeleton */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-32 rounded-xl border bg-card/60 p-6 space-y-3">
            <div className="h-4 w-28 bg-muted rounded" />
            <div className="h-8 w-16 bg-muted rounded" />
          </div>
        ))}
      </div>

      {/* Panels skeleton */}
      <div className="grid gap-6 md:grid-cols-7">
        <div className="col-span-4 h-80 rounded-xl border bg-card/60 p-6 space-y-4">
          <div className="h-6 w-36 bg-muted rounded" />
          <div className="space-y-3">
            <div className="h-14 bg-muted/40 rounded-lg" />
            <div className="h-14 bg-muted/40 rounded-lg" />
            <div className="h-14 bg-muted/40 rounded-lg" />
          </div>
        </div>
        <div className="col-span-3 h-80 rounded-xl border bg-card/60 p-6 space-y-4">
          <div className="h-6 w-36 bg-muted rounded" />
          <div className="space-y-3">
            <div className="h-14 bg-muted/40 rounded-lg" />
            <div className="h-14 bg-muted/40 rounded-lg" />
            <div className="h-14 bg-muted/40 rounded-lg" />
          </div>
        </div>
      </div>
    </div>
  );
}
