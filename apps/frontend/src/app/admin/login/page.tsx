"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { AuthThreeAnimation } from "@/components/canvas/AuthThreeAnimation";
import {
  Shield,
  AlertCircle,
  Eye,
  EyeOff,
  User,
  Lock,
  ArrowLeft,
  KeyRound,
} from "lucide-react";

export default function AdminLoginPage() {
  const { adminLogin, isLoading, isAuthenticated, user } = useAuth();
  const router = useRouter();

  // If already authenticated as admin, redirect to admin console
  useEffect(() => {
    if (isAuthenticated) {
      if (user?.role === "ORG_ADMIN" || user?.role === "SYSTEM_ADMIN") {
        router.push("/admin");
      } else {
        router.push("/");
      }
    }
  }, [isAuthenticated, user, router]);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Administrator username is required");
      return;
    }
    if (!password) {
      setError("Password is required");
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

  return (
    <div className="relative min-h-screen flex items-center justify-center p-6 sm:p-12 overflow-hidden">
      <div className="w-full max-w-xl space-y-8 relative z-10">
        {/* Curved Admin Card with Generous Space */}
        <div className="rounded-[32px] border border-amber-500/20 bg-card/80 backdrop-blur-2xl shadow-2xl ring-1 ring-amber-500/10 p-8 sm:p-12 space-y-8 transition-all">
          {/* Header & 3D Three.js Animation */}
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="relative p-1">
              <AuthThreeAnimation mode="admin" size={130} />
            </div>

            <div className="space-y-1">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-mono tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <Shield className="w-3.5 h-3.5" />
                <span>PRIVILEGED GATEWAY</span>
              </div>
              <h1 className="text-3xl font-extrabold tracking-tight text-foreground pt-1">
                Admin Portal
              </h1>
            </div>
          </div>

          {/* Minimal Error Display */}
          {error && (
            <div className="flex items-center gap-3 p-4 rounded-2xl bg-destructive/10 text-destructive text-xs border border-destructive/20 animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <div className="flex-1 font-medium">{error}</div>
            </div>
          )}

          {/* Admin Login Form — Strictly NO signup option */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-5">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                  <User className="w-3.5 h-3.5 text-amber-400" />
                  <span>Admin Username</span>
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                  className="w-full px-4 py-3.5 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500/50 transition-all font-mono placeholder:text-muted-foreground/50"
                  placeholder="admin"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                  <Lock className="w-3.5 h-3.5 text-amber-400" />
                  <span>Admin Password</span>
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="w-full px-4 py-3.5 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500/50 transition-all pr-12 placeholder:text-muted-foreground/50"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3.5 px-6 rounded-2xl bg-amber-500 text-black font-bold text-sm hover:bg-amber-400 active:scale-[0.99] transition-all shadow-lg flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <KeyRound className="w-4 h-4" />
              <span>{isLoading ? "Verifying..." : "Authenticate"}</span>
            </button>
          </form>

          {/* Return Navigation */}
          <div className="pt-6 border-t border-border/40 flex items-center justify-center text-xs text-muted-foreground">
            <Link
              href="/login"
              className="text-muted-foreground hover:text-foreground transition-colors flex items-center gap-2"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to standard member sign in</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
