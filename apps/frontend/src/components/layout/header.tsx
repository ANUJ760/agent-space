"use client";

import React from "react";
import { Search, Bell, Building2, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function Header() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <header className="h-16 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-20 flex items-center justify-between px-6">
      {/* Organization context / Switcher shell */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md border bg-card text-sm font-medium text-foreground">
          <Building2 className="w-4 h-4 text-muted-foreground" />
          <span>Default Organization</span>
        </div>
      </div>

      {/* Global search placeholder */}
      <div className="w-96 max-w-sm hidden md:flex items-center relative">
        <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          placeholder="Search tasks, agents, projects..."
          className="w-full pl-9 pr-4 py-1.5 text-sm rounded-md border bg-muted/40 focus:bg-background focus:outline-none focus:ring-1 focus:ring-ring transition-colors"
        />
      </div>

      {/* User profile & actions */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="w-4 h-4 text-muted-foreground" />
          <span className="w-2 h-2 rounded-full bg-primary absolute top-2 right-2" />
        </Button>

        {/* User avatar & logout */}
        {isAuthenticated && user && (
          <div className="flex items-center gap-3 pl-2 border-l">
            <div className="w-8 h-8 rounded-full bg-primary/10 text-primary font-semibold flex items-center justify-center text-xs">
              {user.username.substring(0, 2).toUpperCase()}
            </div>
            <div className="hidden lg:flex flex-col text-left">
              <span className="text-xs font-medium text-foreground">
                {user.username}
              </span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {user.role}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={logout}
              title="Sign Out"
              className="text-muted-foreground hover:text-destructive"
            >
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
