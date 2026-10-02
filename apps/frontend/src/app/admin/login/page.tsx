"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { AuthThreeAnimation } from "@/components/canvas/AuthThreeAnimation";
import { AuthErrorAlert } from "@/components/auth/auth-error-alert";
import { authErrorMessage } from "@/lib/auth-error-message";
import {
  Shield,
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
      setError(authErrorMessage(err, "admin"));
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center p-6 sm:p-12 overflow-hidden bg-background">
      <div className="w-full max-w-xl space-y-8 relative z-10">
        {/* High-Contrast Curved Admin Card */}
        <div className="rounded-[32px] border border-amber-500/35 bg-zinc-950/90 backdrop-blur-2xl shadow-[0_0_60px_-15px_rgba(245,158,11,0.22)] ring-1 ring-amber-500/20 p-8 sm:p-12 space-y-8 transition-all">
          {/* Header & 3D Three.js Animation */}
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="relative p-1 filter drop-shadow-[0_0_16px_rgba(251,191,36,0.35)]">
              <AuthThreeAnimation mode="admin" size={140} />
            </div>

            <div className="space-y-1.5">
              <div className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full text-[11px] font-mono font-bold tracking-widest bg-amber-500/15 text-amber-300 border border-amber-400/50 shadow-sm">
                <Shield className="w-3.5 h-3.5 text-amber-400" />
                <span>PRIVILEGED GATEWAY</span>
              </div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white drop-shadow-sm pt-1">
                Admin Portal
              </h1>
            </div>
          </div>

          {/* Form errors stay on this screen. */}
          {error && (
            <AuthErrorAlert title="Admin sign in unsuccessful" message={error} />
          )}

          {/* Admin Login Form — Strictly NO signup option */}
          <form onSubmit={handleSubmit} onChange={() => setError(null)} className="space-y-6">
            <div className="space-y-5">
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                  <User className="w-3.5 h-3.5 text-amber-400" />
                  <span>Admin Username</span>
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                  className="w-full px-4 py-3.5 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-amber-400 hover:border-zinc-500 transition-all font-mono shadow-inner"
                  placeholder="admin"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                  <Lock className="w-3.5 h-3.5 text-amber-400" />
                  <span>Admin Password</span>
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="w-full px-4 py-3.5 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-amber-400 hover:border-zinc-500 transition-all pr-12 shadow-inner"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4 text-amber-400" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-amber-400 via-amber-500 to-amber-600 hover:from-amber-300 hover:to-amber-500 text-zinc-950 font-black text-sm tracking-wide shadow-[0_0_25px_rgba(245,158,11,0.35)] hover:shadow-[0_0_35px_rgba(245,158,11,0.5)] active:scale-[0.99] transition-all flex items-center justify-center gap-2.5 disabled:opacity-50"
            >
              <KeyRound className="w-4 h-4" />
              <span>{isLoading ? "Verifying..." : "Authenticate Privileges"}</span>
            </button>
          </form>

          {/* Return Navigation */}
          <div className="pt-6 border-t border-zinc-800 flex items-center justify-center text-xs">
            <Link
              href="/login"
              className="text-zinc-400 hover:text-white transition-colors flex items-center gap-2 font-medium"
            >
              <ArrowLeft className="w-3.5 h-3.5 text-amber-400" />
              <span>Back to standard member sign in</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
