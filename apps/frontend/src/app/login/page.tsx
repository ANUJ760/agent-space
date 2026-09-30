"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Shield,
  KeyRound,
  LogIn,
  AlertCircle,
  Building2,
  UserCheck,
  UserPlus,
  Lock,
  Crown,
  Wrench,
  Code,
  Eye,
} from "lucide-react";

type AuthMode = "signin" | "admin" | "signup";

export default function LoginPage() {
  const { login, adminLogin, signup, isLoading } = useAuth();
  const [mode, setMode] = useState<AuthMode>("signin");

  // Sign in state
  const [username, setUsername] = useState("admin_a");
  const [password, setPassword] = useState("password123");

  // Sign up state
  const [signupUsername, setSignupUsername] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [signupOrg, setSignupOrg] = useState("");
  const [signupRole, setSignupRole] = useState("ORG_ADMIN");

  const [error, setError] = useState<string | null>(null);

  // Quick Persona Presets for instant testing
  const personas = [
    {
      name: "Org Admin",
      username: "admin_a",
      role: "ORG_ADMIN",
      icon: Crown,
      color: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
      description: "Full platform & tenant authority",
    },
    {
      name: "Project Lead",
      username: "lead_dev",
      role: "PROJECT_OWNER",
      icon: Wrench,
      color: "border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-400",
      description: "Project management & task workflows",
    },
    {
      name: "Developer",
      username: "alice_coder",
      role: "MEMBER",
      icon: Code,
      color: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
      description: "Code generation, PRs & task execution",
    },
    {
      name: "Auditor",
      username: "auditor_bob",
      role: "VIEWER",
      icon: Eye,
      color: "border-purple-500/40 bg-purple-500/10 text-purple-600 dark:text-purple-400",
      description: "Read-only audit & observability",
    },
  ];

  const handleSelectPersona = (p: typeof personas[0]) => {
    setUsername(p.username);
    setPassword("password123");
    setError(null);
  };

  const handleStandardLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Please enter a username or email");
      return;
    }
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to authenticate session");
    }
  };

  const handleAdminLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Please enter administrator username or email");
      return;
    }
    setError(null);
    try {
      await adminLogin(username.trim(), password);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Access denied. Administrator privileges required."
      );
    }
  };

  const handleSignupSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!signupUsername.trim() || !signupEmail.trim()) {
      setError("Username and email are required");
      return;
    }
    setError(null);
    try {
      await signup({
        username: signupUsername.trim(),
        email: signupEmail.trim(),
        password: signupPassword.trim() || undefined,
        organizationName: signupOrg.trim() || undefined,
        role: signupRole,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-muted/20">
      <div className="w-full max-w-lg space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-primary text-primary-foreground font-black text-xl shadow-lg shadow-primary/20">
            A
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-foreground">
            Agent Space
          </h1>
          <p className="text-sm text-muted-foreground">
            Autonomous AI & Human Software Engineering Collaboration
          </p>
        </div>

        {/* Mode Navigation Tabs */}
        <div className="grid grid-cols-3 p-1 rounded-xl bg-muted border text-xs font-semibold">
          <button
            type="button"
            onClick={() => {
              setMode("signin");
              setError(null);
            }}
            className={`py-2 px-3 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              mode === "signin"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Sign In</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setMode("admin");
              setError(null);
            }}
            className={`py-2 px-3 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              mode === "admin"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Shield className="w-3.5 h-3.5 text-primary" />
            <span>Admin Portal</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setMode("signup");
              setError(null);
            }}
            className={`py-2 px-3 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              mode === "signup"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Sign Up</span>
          </button>
        </div>

        {/* Main Card */}
        <Card className="shadow-xl border">
          {error && (
            <div className="mx-6 mt-6 flex items-start gap-3 p-3 rounded-lg bg-destructive/10 text-destructive text-sm border border-destructive/20">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
              <div className="flex-1 font-medium">{error}</div>
            </div>
          )}

          {/* 1. STANDARD SIGN IN */}
          {mode === "signin" && (
            <form onSubmit={handleStandardLogin}>
              <CardHeader className="space-y-1">
                <CardTitle className="text-xl font-bold">Sign In to Your Workspace</CardTitle>
                <CardDescription>
                  Access your organization's projects, agents, and active tasks.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                {/* Quick Persona Selector */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                    <span>Quick Select Persona (RBAC)</span>
                    <span className="text-[10px] text-muted-foreground lowercase">1-click dev switch</span>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {personas.map((p) => {
                      const Icon = p.icon;
                      const isSelected = username === p.username;
                      return (
                        <button
                          key={p.role}
                          type="button"
                          onClick={() => handleSelectPersona(p)}
                          className={`flex items-start gap-2.5 p-2.5 rounded-lg border text-left transition-all ${
                            isSelected
                              ? "border-primary bg-primary/5 ring-1 ring-primary"
                              : "hover:bg-muted/50"
                          }`}
                        >
                          <div className={`p-1.5 rounded-md border ${p.color}`}>
                            <Icon className="w-3.5 h-3.5" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="text-xs font-semibold leading-none">{p.name}</div>
                            <div className="text-[10px] text-muted-foreground font-mono mt-1 truncate">
                              {p.role}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Username / Email
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="developer@agentspace.local"
                  />
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="••••••••"
                  />
                </div>
              </CardContent>

              <CardFooter className="flex flex-col gap-3">
                <Button type="submit" className="w-full gap-2" disabled={isLoading}>
                  <LogIn className="w-4 h-4" />
                  <span>{isLoading ? "Authenticating..." : "Sign In to Agent Space"}</span>
                </Button>
              </CardFooter>
            </form>
          )}

          {/* 2. PROTECTED ADMIN LOGIN */}
          {mode === "admin" && (
            <form onSubmit={handleAdminLogin}>
              <CardHeader className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary gap-1 py-1">
                    <Shield className="w-3.5 h-3.5" />
                    <span>Protected Endpoint</span>
                  </Badge>
                </div>
                <CardTitle className="text-xl font-bold mt-2">Administrator Access</CardTitle>
                <CardDescription>
                  Requires verified <span className="font-semibold text-foreground">ORG_ADMIN</span> or <span className="font-semibold text-foreground">SYSTEM_ADMIN</span> credentials.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                <div className="p-3 rounded-lg border bg-amber-500/5 border-amber-500/20 text-xs text-amber-700 dark:text-amber-400 space-y-1">
                  <div className="font-semibold flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" />
                    <span>Protected Admin Route: /api/v1/auth/admin/login</span>
                  </div>
                  <p>
                    Non-admin accounts will be rejected by the backend RBAC security layer with HTTP 403 Forbidden.
                  </p>
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Admin Username / Email
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="admin_a"
                  />
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Admin Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="••••••••"
                  />
                </div>
              </CardContent>

              <CardFooter className="flex flex-col gap-3">
                <Button type="submit" className="w-full gap-2 bg-primary text-primary-foreground" disabled={isLoading}>
                  <Shield className="w-4 h-4" />
                  <span>{isLoading ? "Verifying Admin Credentials..." : "Authenticate as Administrator"}</span>
                </Button>
              </CardFooter>
            </form>
          )}

          {/* 3. SIGN UP / NEW WORKSPACE */}
          {mode === "signup" && (
            <form onSubmit={handleSignupSubmit}>
              <CardHeader className="space-y-1">
                <CardTitle className="text-xl font-bold">Create Account & Workspace</CardTitle>
                <CardDescription>
                  Register a new collaborative workspace for your engineering team.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5 text-left">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Username
                    </label>
                    <input
                      type="text"
                      value={signupUsername}
                      onChange={(e) => setSignupUsername(e.target.value)}
                      required
                      className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="e.g. dev_sarah"
                    />
                  </div>

                  <div className="space-y-1.5 text-left">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Organization Name
                    </label>
                    <input
                      type="text"
                      value={signupOrg}
                      onChange={(e) => setSignupOrg(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="Acme Engineering"
                    />
                  </div>
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Corporate Email
                  </label>
                  <input
                    type="email"
                    value={signupEmail}
                    onChange={(e) => setSignupEmail(e.target.value)}
                    required
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="sarah@acme.com"
                  />
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Assigned RBAC Role
                  </label>
                  <select
                    value={signupRole}
                    onChange={(e) => setSignupRole(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    <option value="ORG_ADMIN">ORG_ADMIN — Full Organization Control</option>
                    <option value="PROJECT_OWNER">PROJECT_OWNER — Project Architect & Lead</option>
                    <option value="MEMBER">MEMBER — Core Developer</option>
                    <option value="VIEWER">VIEWER — Observer & Auditor</option>
                  </select>
                </div>

                <div className="space-y-1.5 text-left">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Password
                  </label>
                  <input
                    type="password"
                    value={signupPassword}
                    onChange={(e) => setSignupPassword(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="••••••••"
                  />
                </div>
              </CardContent>

              <CardFooter className="flex flex-col gap-3">
                <Button type="submit" className="w-full gap-2" disabled={isLoading}>
                  <UserPlus className="w-4 h-4" />
                  <span>{isLoading ? "Creating Workspace..." : "Register & Open Agent Space"}</span>
                </Button>
              </CardFooter>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}
