"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FolderKanban,
  CheckSquare,
  Bot,
  Settings,
  LayoutDashboard,
  Users,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { title: "Dashboard", href: "/", icon: LayoutDashboard },
  { title: "Projects", href: "/projects", icon: FolderKanban },
  { title: "Tasks", href: "/tasks", icon: CheckSquare },
  { title: "Agents", href: "/agents", icon: Bot },
  { title: "Team", href: "/team", icon: Users },
  { title: "Audit Log", href: "/audit", icon: ShieldCheck },
  { title: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r bg-card flex flex-col h-screen fixed left-0 top-0 z-30">
      {/* Brand logo & platform title */}
      <div className="h-16 flex items-center px-6 border-b gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold text-lg shadow-sm">
          A
        </div>
        <div className="flex flex-col">
          <span className="font-semibold text-sm leading-tight text-foreground">
            Agent Space
          </span>
          <span className="text-xs text-muted-foreground">Autonomous Workspace</span>
        </div>
      </div>

      {/* Main navigation */}
      <div className="flex-1 overflow-y-auto py-4 px-3">
        <div className="px-3 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Workspace
        </div>
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname?.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.title}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer status / environment */}
      <div className="p-4 border-t text-xs text-muted-foreground flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Backend Connected</span>
        </div>
        <span className="font-mono text-[10px] bg-muted px-1.5 py-0.5 rounded">
          v0.1.0
        </span>
      </div>
    </aside>
  );
}
