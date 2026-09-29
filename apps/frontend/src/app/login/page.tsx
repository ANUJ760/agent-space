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
import { Shield, KeyRound, LogIn, AlertCircle } from "lucide-react";

export default function LoginPage() {
  const { login, isLoading } = useAuth();
  const [username, setUsername] = useState("admin_a");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState<string | null>(null);

  const handleKeycloakLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Please enter a username");
      return;
    }
    setError(null);
    try {
      await login(username.trim());
    } catch {
      setError("Failed to authenticate session with Keycloak");
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center p-4">
      <Card className="w-full max-w-md shadow-lg border">
        <CardHeader className="text-center space-y-2">
          <div className="mx-auto w-12 h-12 rounded-xl bg-primary flex items-center justify-center text-primary-foreground shadow-md">
            <Shield className="w-6 h-6" />
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight">
            Sign in to Agent Space
          </CardTitle>
          <CardDescription>
            Enter your credentials or authenticate via Keycloak OIDC SSO
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleKeycloakLogin}>
          <CardContent className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1 text-left">
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

            <div className="space-y-1 text-left">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="••••••••"
              />
            </div>
          </CardContent>

          <CardFooter className="flex flex-col gap-3">
            <Button
              type="submit"
              className="w-full gap-2"
              disabled={isLoading}
            >
              <LogIn className="w-4 h-4" />
              <span>{isLoading ? "Signing In..." : "Sign In with Credentials"}</span>
            </Button>

            <div className="relative w-full my-1">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground font-medium">
                  Or Single Sign-On
                </span>
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              className="w-full gap-2 border-primary/30 hover:bg-primary/5"
              onClick={() => login("sso_user")}
            >
              <KeyRound className="w-4 h-4 text-primary" />
              <span>Log in with Keycloak OIDC</span>
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
