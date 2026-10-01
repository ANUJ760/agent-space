"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { AuthThreeAnimation } from "@/components/canvas/AuthThreeAnimation";
import {
  LogIn,
  AlertCircle,
  UserPlus,
  Eye,
  EyeOff,
  User,
  Mail,
  Lock,
  Building2,
} from "lucide-react";

type AuthMode = "signin" | "signup";

export default function LoginPage() {
  const { login, signup, isLoading, isAuthenticated } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("signin");

  useEffect(() => {
    if (isAuthenticated) {
      router.push("/");
    }
  }, [isAuthenticated, router]);

  // Sign in state
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Sign up state
  const [signupFullName, setSignupFullName] = useState("");
  const [signupUsername, setSignupUsername] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [signupOrg, setSignupOrg] = useState("");
  const [showSignupPassword, setShowSignupPassword] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const handleStandardLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError("Enter your username or email");
      return;
    }
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Invalid credentials. Please verify your details."
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
        displayName: signupFullName.trim() || undefined,
        username: signupUsername.trim(),
        email: signupEmail.trim(),
        password: signupPassword,
        organizationName: signupOrg.trim() || undefined,
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Account creation failed. Please check your information."
      );
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center p-6 sm:p-12 overflow-hidden bg-background">
      <div className="w-full max-w-xl space-y-8 relative z-10">
        {/* Main Curved Card with High Contrast & Subtle Electric Glow */}
        <div className="rounded-[32px] border border-cyan-500/25 bg-zinc-950/90 backdrop-blur-2xl shadow-[0_0_60px_-15px_rgba(6,182,212,0.22)] ring-1 ring-white/10 p-8 sm:p-12 space-y-8 transition-all">
          {/* Header & Three.js 3D Interactive Animation */}
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="relative p-1 filter drop-shadow-[0_0_16px_rgba(0,240,255,0.35)]">
              <AuthThreeAnimation mode={mode} size={140} />
            </div>

            <div className="space-y-1.5">
              <h1 className="text-3xl font-extrabold tracking-tight text-white drop-shadow-sm">
                Agent Space
              </h1>
              <p className="text-xs font-mono tracking-widest uppercase text-cyan-400 font-bold">
                Autonomous Collaboration
              </p>
            </div>

            {/* High-Contrast Curved Pill Mode Switcher */}
            <div className="inline-flex p-1.5 rounded-full bg-zinc-900 border border-zinc-700/80 shadow-inner">
              <button
                type="button"
                onClick={() => {
                  setMode("signin");
                  setError(null);
                }}
                className={`py-2 px-6 rounded-full text-xs font-bold transition-all flex items-center gap-2 ${
                  mode === "signin"
                    ? "bg-cyan-500 text-zinc-950 shadow-[0_0_18px_rgba(6,182,212,0.45)]"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
                className={`py-2 px-6 rounded-full text-xs font-bold transition-all flex items-center gap-2 ${
                  mode === "signup"
                    ? "bg-cyan-500 text-zinc-950 shadow-[0_0_18px_rgba(6,182,212,0.45)]"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" />
                <span>Sign Up</span>
              </button>
            </div>
          </div>

          {/* High-Contrast Error Alert */}
          {error && (
            <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-950/80 text-rose-200 text-xs font-medium border border-rose-500/60 shadow-lg shadow-rose-950/40 animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <div className="flex-1">{error}</div>
            </div>
          )}

          {/* 1. SIGN IN FORM */}
          {mode === "signin" && (
            <form onSubmit={handleStandardLogin} className="space-y-6">
              <div className="space-y-5">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                    <User className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Username or Email</span>
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full px-4 py-3.5 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-cyan-400 hover:border-zinc-500 transition-all shadow-inner"
                    placeholder="developer@company.com or username"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                    <Lock className="w-3.5 h-3.5 text-violet-400" />
                    <span>Password</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="w-full px-4 py-3.5 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-violet-400 hover:border-zinc-500 transition-all pr-12 shadow-inner"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4 text-violet-400" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-cyan-500 via-blue-500 to-violet-600 hover:from-cyan-400 hover:via-blue-400 hover:to-violet-500 text-white font-bold text-sm tracking-wide shadow-[0_0_25px_rgba(6,182,212,0.35)] hover:shadow-[0_0_35px_rgba(6,182,212,0.5)] active:scale-[0.99] transition-all flex items-center justify-center gap-2.5 disabled:opacity-50"
              >
                <LogIn className="w-4 h-4" />
                <span>{isLoading ? "Signing In..." : "Sign In to Workspace"}</span>
              </button>
            </form>
          )}

          {/* 2. SIGN UP FORM */}
          {mode === "signup" && (
            <form onSubmit={handleSignupSubmit} className="space-y-6">
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider ml-1">
                      Full Name
                    </label>
                    <input
                      type="text"
                      value={signupFullName}
                      onChange={(e) => setSignupFullName(e.target.value)}
                      className="w-full px-4 py-3 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-cyan-400 hover:border-zinc-500 transition-all shadow-inner"
                      placeholder="Alex Morgan"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider ml-1">
                      Username
                    </label>
                    <input
                      type="text"
                      value={signupUsername}
                      onChange={(e) => setSignupUsername(e.target.value)}
                      required
                      className="w-full px-4 py-3 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-cyan-400 hover:border-zinc-500 transition-all shadow-inner"
                      placeholder="amorgan"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                    <Mail className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Email Address</span>
                  </label>
                  <input
                    type="email"
                    value={signupEmail}
                    onChange={(e) => setSignupEmail(e.target.value)}
                    required
                    className="w-full px-4 py-3 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-cyan-400 hover:border-zinc-500 transition-all shadow-inner"
                    placeholder="amorgan@company.com"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                      <Building2 className="w-3.5 h-3.5 text-violet-400" />
                      <span>Workspace</span>
                    </label>
                    <input
                      type="text"
                      value={signupOrg}
                      onChange={(e) => setSignupOrg(e.target.value)}
                      className="w-full px-4 py-3 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-violet-400 hover:border-zinc-500 transition-all shadow-inner"
                      placeholder="Acme Corp"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2 ml-1">
                      <Lock className="w-3.5 h-3.5 text-violet-400" />
                      <span>Password</span>
                    </label>
                    <div className="relative">
                      <input
                        type={showSignupPassword ? "text" : "password"}
                        value={signupPassword}
                        onChange={(e) => setSignupPassword(e.target.value)}
                        required
                        minLength={8}
                        className="w-full px-4 py-3 text-sm font-medium rounded-2xl border border-zinc-700 bg-zinc-900/95 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-violet-400 hover:border-zinc-500 transition-all pr-12 shadow-inner"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowSignupPassword(!showSignupPassword)}
                        className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition-colors"
                      >
                        {showSignupPassword ? <EyeOff className="w-4 h-4 text-violet-400" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-cyan-500 via-blue-500 to-violet-600 hover:from-cyan-400 hover:via-blue-400 hover:to-violet-500 text-white font-bold text-sm tracking-wide shadow-[0_0_25px_rgba(6,182,212,0.35)] hover:shadow-[0_0_35px_rgba(6,182,212,0.5)] active:scale-[0.99] transition-all flex items-center justify-center gap-2.5 disabled:opacity-50"
              >
                <UserPlus className="w-4 h-4" />
                <span>{isLoading ? "Creating Workspace..." : "Create Account & Workspace"}</span>
              </button>
            </form>
          )}

          {/* High-Contrast Clean Footer Navigation */}
          <div className="pt-6 border-t border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
            {mode === "signin" ? (
              <button
                type="button"
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
                className="text-zinc-400 hover:text-white transition-colors flex items-center gap-1.5"
              >
                <span>Don&apos;t have an account?</span>
                <span className="font-bold text-cyan-400 hover:text-cyan-300 underline underline-offset-4">Sign Up</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setMode("signin");
                  setError(null);
                }}
                className="text-zinc-400 hover:text-white transition-colors flex items-center gap-1.5"
              >
                <span>Already registered?</span>
                <span className="font-bold text-cyan-400 hover:text-cyan-300 underline underline-offset-4">Sign In</span>
              </button>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
