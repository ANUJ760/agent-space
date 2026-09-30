"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { ProtectedRoute } from "@/components/auth/protected-route";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthPage =
    pathname === "/login" ||
    pathname === "/admin/login" ||
    pathname === "/unauthorized";

  if (isAuthPage) {
    return <main className="min-h-screen bg-background relative z-10">{children}</main>;
  }

  return (
    <ProtectedRoute>
      <div className="flex min-h-screen relative z-10">
        <Sidebar />
        <div className="flex-1 flex flex-col pl-60">
          <Header />
          <main className="flex-1 p-6 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
