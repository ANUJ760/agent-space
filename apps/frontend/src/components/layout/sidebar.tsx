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
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";

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
  const { user } = useAuth();
  const items = user?.role === "ORG_ADMIN" || user?.role === "SYSTEM_ADMIN"
    ? [...navItems, { title: "Admin", href: "/admin", icon: Shield }]
    : navItems;

  return (
    <aside className="w-60 border-r border-border/70 bg-card/90 backdrop-blur-md flex flex-col h-screen fixed left-0 top-0 z-30">
      {/* Brand logo & platform title */}
      <div className="h-11 flex items-center px-4 border-b border-border/70 gap-2.5">
        <div className="w-6 h-6 rounded-full border border-primary/50 bg-primary/20 text-primary flex items-center justify-center font-bold text-xs shrink-0">
          A
        </div>
        <div className="flex flex-col">
          <span className="font-bold text-xs leading-none tracking-tight text-foreground">
            Agent Space
          </span>
          <span className="text-[9px] text-muted-foreground font-mono mt-0.5">Autonomous Workspace</span>
        </div>
      </div>

      {/* Main navigation with circular minimalistic icons and sharp buttons */}
      <div className="flex-1 overflow-y-auto py-3 px-2">
        <div className="px-2 mb-1.5 text-[10px] font-mono font-semibold text-muted-foreground/80 uppercase tracking-widest">
          Workspace
        </div>
        <nav className="space-y-0.5">
          {items.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname?.startsWith(`${item.href}/`);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 px-2.5 py-1.5 rounded-none text-xs font-medium transition-all",
                  isActive
                    ? "bg-accent/80 text-foreground border-l-2 border-primary font-semibold"
                    : "text-muted-foreground hover:bg-muted/40 hover:text-foreground border-l-2 border-transparent"
                )}
              >
                <div
                  className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center transition-colors shrink-0",
                    isActive
                      ? "border border-primary/60 bg-primary/10 text-primary"
                      : "border border-border/60 text-muted-foreground"
                  )}
                >
                  <Icon className="w-2.5 h-2.5" />
                </div>
                <span>{item.title}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer status / environment */}
      <div className="p-3 border-t border-border/70 text-[11px] text-muted-foreground flex items-center justify-between bg-background/40">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-mono text-[10px] tracking-tight">System Operational</span>
        </div>
        <span className="font-mono text-[9px] border border-border/60 bg-muted/40 px-1 py-0.2 rounded-none">
          v0.1.0
        </span>
      </div>
    </aside>
  );
}
