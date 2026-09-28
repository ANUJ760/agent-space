import React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FolderKanban,
  CheckSquare,
  Bot,
  Activity,
  Plus,
  ArrowUpRight,
} from "lucide-react";

export default function HomePage() {
  const stats = [
    {
      title: "Active Projects",
      value: "12",
      change: "+2 this month",
      icon: FolderKanban,
    },
    {
      title: "Active Agents",
      value: "8",
      change: "All systems online",
      icon: Bot,
    },
    {
      title: "In-Progress Tasks",
      value: "24",
      change: "4 waiting review",
      icon: CheckSquare,
    },
    {
      title: "Platform Health",
      value: "99.9%",
      change: "PostgreSQL & Redis UP",
      icon: Activity,
    },
  ];

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Workspace Overview
          </h1>
          <p className="text-muted-foreground mt-1">
            Autonomous software engineering orchestration and human-agent collaboration.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm">
            View Audit Log
          </Button>
          <Button size="sm" className="gap-2">
            <Plus className="w-4 h-4" />
            <span>New Task</span>
          </Button>
        </div>
      </div>

      {/* Metrics Overview Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.title}>
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {stat.title}
                </CardTitle>
                <Icon className="w-4 h-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">
                  {stat.value}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {stat.change}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Main Workspace Panels */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
        {/* Active Projects Shell */}
        <Card className="col-span-4">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Recent Projects</CardTitle>
              <CardDescription>
                Collaborative repositories and workspace branches
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" className="gap-1 text-xs">
              <span>View all</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[
                {
                  name: "Agent Space Backend",
                  slug: "agent-space-backend",
                  tasks: "18 tasks",
                  status: "ACTIVE",
                },
                {
                  name: "Frontend Next.js Shell",
                  slug: "agent-space-frontend",
                  tasks: "6 tasks",
                  status: "ACTIVE",
                },
                {
                  name: "AI Autonomous Planner",
                  slug: "agent-space-planner",
                  tasks: "12 tasks",
                  status: "ACTIVE",
                },
              ].map((project) => (
                <div
                  key={project.slug}
                  className="flex items-center justify-between p-3.5 rounded-lg border bg-card/50 hover:bg-muted/30 transition-colors"
                >
                  <div className="space-y-1">
                    <p className="text-sm font-medium leading-none text-foreground">
                      {project.name}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {project.slug} • {project.tasks}
                    </p>
                  </div>
                  <Badge variant="secondary">{project.status}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Autonomous Agents Status Shell */}
        <Card className="col-span-3">
          <CardHeader>
            <CardTitle>Autonomous Agents</CardTitle>
            <CardDescription>Active autonomous worker agents</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[
                { name: "Code Reviewer", role: "REVIEWER", status: "ONLINE" },
                { name: "Test Engineer", role: "TESTER", status: "ONLINE" },
                { name: "Architecture Scout", role: "ARCHITECT", status: "IDLE" },
              ].map((agent) => (
                <div
                  key={agent.name}
                  className="flex items-center justify-between p-3 rounded-lg border bg-card/50"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                      <Bot className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-foreground">
                        {agent.name}
                      </div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {agent.role}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        agent.status === "ONLINE"
                          ? "bg-emerald-500"
                          : "bg-amber-500"
                      }`}
                    />
                    <span className="text-xs font-medium text-muted-foreground">
                      {agent.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
