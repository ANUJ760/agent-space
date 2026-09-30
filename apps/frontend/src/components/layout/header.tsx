"use client";

import React from "react";
import { Search, Bell, Building2, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function Header() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <header className="h-11 border-b border-border/70 bg-background/80 backdrop-blur-md sticky top-0 z-20 flex items-center justify-between px-5">
      {/* Organization context / Switcher shell */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-none border border-border/70 bg-card/60 text-xs font-medium text-foreground shadow-none">
          <div className="w-5 h-5 rounded-full border border-primary/40 bg-primary/10 flex items-center justify-center text-primary shrink-0">
            <Building2 className="w-3 h-3" />
          </div>
          <span className="font-semibold tracking-tight">{user?.organizationName || "Agent Space Workspace"}</span>
        </div>
      </div>

      {/* Global search placeholder */}
      <div className="w-80 max-w-sm hidden md:flex items-center relative">
        <div className="w-4 h-4 rounded-full flex items-center justify-center absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground">
          <Search className="w-3 h-3" />
        </div>
        <input
          type="text"
          placeholder="Search workspace, agents, tasks..."
          className="w-full pl-8 pr-3 py-1 text-xs rounded-none border border-border/60 bg-muted/30 focus:bg-background focus:outline-none focus:ring-1 focus:ring-primary/40 placeholder:text-muted-foreground/60 transition-colors"
        />
      </div>

      {/* User profile & actions with circular minimalistic icons */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          title="Notifications"
          className="w-7 h-7 rounded-full border border-border/60 hover:border-primary/50 bg-background/40 hover:bg-accent/40 flex items-center justify-center transition-colors relative"
        >
          <Bell className="w-3 h-3 text-muted-foreground" />
          <span className="w-1.5 h-1.5 rounded-full bg-primary absolute top-1.5 right-1.5" />
        </button>

        {/* User avatar & logout */}
        {isAuthenticated && user && (
          <div className="flex items-center gap-2 pl-2 border-l border-border/60">
            <div className="w-7 h-7 rounded-full border border-primary/50 bg-primary/10 text-primary font-mono font-bold flex items-center justify-center text-[10px] shadow-sm">
              {user.username.substring(0, 2).toUpperCase()}
            </div>
            <div className="hidden lg:flex flex-col text-left pr-1">
              <span className="text-[11px] font-semibold text-foreground leading-none">
                {user.displayName || user.username}
              </span>
              <span className="text-[9px] text-muted-foreground font-mono leading-tight">
                {user.role}
              </span>
            </div>
            <button
              type="button"
              onClick={logout}
              title="Sign Out"
              className="w-7 h-7 rounded-full border border-border/60 hover:border-destructive/60 hover:bg-destructive/10 text-muted-foreground hover:text-destructive flex items-center justify-center transition-colors"
            >
              <LogOut className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
