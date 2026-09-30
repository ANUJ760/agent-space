"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api-client";
import { UserProfile } from "@/types/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Shield,
  Building2,
  Users,
  KeyRound,
  CheckCircle2,
  Lock,
  ArrowRight,
  LogOut,
  FolderGit2,
} from "lucide-react";

export default function AdminDashboardPage() {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const router = useRouter();
  const [adminProfile, setAdminProfile] = useState<UserProfile | null>(null);
  const [isVerifying, setIsVerifying] = useState(true);
  const [verificationError, setVerificationError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/admin/login");
      return;
    }

    if (isAuthenticated) {
      // Query the protected admin session endpoint
      apiFetch<UserProfile>("/api/v1/auth/admin/session")
        .then((data) => {
          setAdminProfile(data);
          setIsVerifying(false);
        })
        .catch((err) => {
          setVerificationError(err instanceof Error ? err.message : "Administrator verification failed");
          setIsVerifying(false);
        });
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading || isVerifying) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/20">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <p className="text-xs text-muted-foreground font-mono">Verifying Administrator Privileges...</p>
        </div>
      </div>
    );
  }

  if (verificationError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4 bg-muted/20">
        <Card className="max-w-md w-full border-destructive/30">
          <CardHeader>
            <CardTitle className="text-lg text-destructive flex items-center gap-2">
              <Shield className="w-5 h-5" />
              <span>Access Denied</span>
            </CardTitle>
            <CardDescription>{verificationError}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Your account lacks authorized administrator credentials (ORG_ADMIN or SYSTEM_ADMIN).
            </p>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                logout();
                router.push("/admin/login");
              }}
            >
              Sign In with Admin Credentials
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/10 p-6 space-y-6">
      {/* Top Admin Navigation Header */}
      <div className="flex items-center justify-between pb-4 border-b">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center font-bold shadow-md">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight">Enterprise Admin Console</h1>
              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30 text-[10px] font-mono">
                {adminProfile?.role || "ADMIN"}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Organization & Tenant Authority • {adminProfile?.organization?.name || "Acme Corporation"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Link href="/">
            <Button variant="outline" size="sm" className="gap-1.5 text-xs">
              <FolderGit2 className="w-3.5 h-3.5" />
              <span>Open Workspaces</span>
            </Button>
          </Link>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              logout();
              router.push("/admin/login");
            }}
            className="text-xs text-muted-foreground hover:text-destructive gap-1.5"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out</span>
          </Button>
        </div>
      </div>

      {/* Admin Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Administrator Profile
            </CardTitle>
            <Shield className="w-4 h-4 text-primary" />
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-lg font-bold">{adminProfile?.display_name || adminProfile?.username}</div>
            <div className="text-xs font-mono text-muted-foreground">{adminProfile?.email}</div>
            <div className="pt-2">
              <Badge variant="secondary" className="text-[10px]">
                Audited Session Active
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Organization Boundary
            </CardTitle>
            <Building2 className="w-4 h-4 text-primary" />
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-lg font-bold">{adminProfile?.organization?.name || "Primary Tenant"}</div>
            <div className="text-xs font-mono text-muted-foreground">
              Slug: {adminProfile?.organization?.slug || "acme-corp"}
            </div>
            <div className="pt-2">
              <span className="text-xs text-emerald-500 font-semibold flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Active Tenant
              </span>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Security Policy
            </CardTitle>
            <Lock className="w-4 h-4 text-primary" />
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-lg font-bold">Strict RBAC</div>
            <div className="text-xs text-muted-foreground">Protected admin endpoint access verified</div>
            <div className="pt-2">
              <Badge variant="outline" className="text-[10px] font-mono text-emerald-600 border-emerald-500/30">
                OIDC Cryptographic Token
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Administrative Operations</CardTitle>
          <CardDescription>
            Privileged controls for member management, security policies, and workspace allocations.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="p-3.5 rounded-lg border bg-card/60 flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="text-sm font-semibold">User Role Governance</div>
              <div className="text-xs text-muted-foreground">
                Audit and assign roles (PROJECT_OWNER, MEMBER, VIEWER) to team accounts.
              </div>
            </div>
            <Link href="/projects">
              <Button size="sm" variant="outline" className="text-xs gap-1">
                <span>View Projects</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </Link>
          </div>

          <div className="p-3.5 rounded-lg border bg-card/60 flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="text-sm font-semibold">Protected Security Verification</div>
              <div className="text-xs text-muted-foreground font-mono">
                Endpoint: GET /api/v1/auth/admin/session (Verified HTTP 200 OK)
              </div>
            </div>
            <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 text-xs">
              Verified
            </Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
