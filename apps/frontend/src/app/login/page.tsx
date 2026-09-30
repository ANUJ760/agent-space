"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { AuthThreeAnimation } from "@/components/canvas/AuthThreeAnimation";
import {
  Shield,
  LogIn,
  AlertCircle,
  UserPlus,
  Eye,
  EyeOff,
  User,
  Mail,
  Lock,
  Building2,
  ArrowRight,
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
        password: signupPassword.trim() || undefined,
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
    <div className="relative min-h-screen flex items-center justify-center p-6 sm:p-12 overflow-hidden">
      <div className="w-full max-w-xl space-y-8 relative z-10">
        {/* Main Curved Card with Generous Breathing Space */}
        <div className="rounded-[32px] border border-border/60 bg-card/75 backdrop-blur-2xl shadow-2xl ring-1 ring-white/10 p-8 sm:p-12 space-y-8 transition-all">
          {/* Header & Three.js 3D Interactive Animation */}
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="relative p-1">
              <AuthThreeAnimation mode={mode} size={130} />
            </div>

            <div className="space-y-1">
              <h1 className="text-3xl font-extrabold tracking-tight text-foreground">
                Agent Space
              </h1>
              <p className="text-xs font-mono tracking-wider uppercase text-muted-foreground">
                Autonomous Collaboration
              </p>
            </div>

            {/* Curved Pill Mode Switcher */}
            <div className="inline-flex p-1.5 rounded-full bg-secondary/50 border border-border/50 shadow-inner">
              <button
                type="button"
                onClick={() => {
                  setMode("signin");
                  setError(null);
                }}
                className={`py-2 px-6 rounded-full text-xs font-semibold transition-all flex items-center gap-2 ${
                  mode === "signin"
                    ? "bg-primary text-primary-foreground shadow-md"
                    : "text-muted-foreground hover:text-foreground"
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
                className={`py-2 px-6 rounded-full text-xs font-semibold transition-all flex items-center gap-2 ${
                  mode === "signup"
                    ? "bg-primary text-primary-foreground shadow-md"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" />
                <span>Sign Up</span>
              </button>
            </div>
          </div>

          {/* Minimal Error Message */}
          {error && (
            <div className="flex items-center gap-3 p-4 rounded-2xl bg-destructive/10 text-destructive text-xs border border-destructive/20 animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <div className="flex-1 font-medium">{error}</div>
            </div>
          )}

          {/* 1. SIGN IN FORM */}
          {mode === "signin" && (
            <form onSubmit={handleStandardLogin} className="space-y-6">
              <div className="space-y-5">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                    <User className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Username or Email</span>
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full px-4 py-3.5 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/50 transition-all placeholder:text-muted-foreground/50"
                    placeholder="Username or email"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                    <Lock className="w-3.5 h-3.5 text-violet-400" />
                    <span>Password</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="w-full px-4 py-3.5 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500/50 transition-all pr-12 placeholder:text-muted-foreground/50"
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
                className="w-full py-3.5 px-6 rounded-2xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 active:scale-[0.99] transition-all shadow-lg flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <LogIn className="w-4 h-4" />
                <span>{isLoading ? "Signing In..." : "Sign In"}</span>
              </button>
            </form>
          )}

          {/* 2. SIGN UP FORM */}
          {mode === "signup" && (
            <form onSubmit={handleSignupSubmit} className="space-y-6">
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider ml-1">
                      Full Name
                    </label>
                    <input
                      type="text"
                      value={signupFullName}
                      onChange={(e) => setSignupFullName(e.target.value)}
                      className="w-full px-4 py-3 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/50 transition-all placeholder:text-muted-foreground/50"
                      placeholder="Alex Morgan"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider ml-1">
                      Username
                    </label>
                    <input
                      type="text"
                      value={signupUsername}
                      onChange={(e) => setSignupUsername(e.target.value)}
                      required
                      className="w-full px-4 py-3 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/50 transition-all placeholder:text-muted-foreground/50"
                      placeholder="amorgan"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                    <Mail className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Email Address</span>
                  </label>
                  <input
                    type="email"
                    value={signupEmail}
                    onChange={(e) => setSignupEmail(e.target.value)}
                    required
                    className="w-full px-4 py-3 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/50 transition-all placeholder:text-muted-foreground/50"
                    placeholder="amorgan@company.com"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                      <Building2 className="w-3.5 h-3.5 text-violet-400" />
                      <span>Workspace</span>
                    </label>
                    <input
                      type="text"
                      value={signupOrg}
                      onChange={(e) => setSignupOrg(e.target.value)}
                      className="w-full px-4 py-3 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500/50 transition-all placeholder:text-muted-foreground/50"
                      placeholder="Acme Corp"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
                      <Lock className="w-3.5 h-3.5 text-violet-400" />
                      <span>Password</span>
                    </label>
                    <div className="relative">
                      <input
                        type={showSignupPassword ? "text" : "password"}
                        value={signupPassword}
                        onChange={(e) => setSignupPassword(e.target.value)}
                        className="w-full px-4 py-3 text-sm rounded-2xl border border-border/70 bg-background/60 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500/50 transition-all pr-12 placeholder:text-muted-foreground/50"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowSignupPassword(!showSignupPassword)}
                        className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {showSignupPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3.5 px-6 rounded-2xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 active:scale-[0.99] transition-all shadow-lg flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <UserPlus className="w-4 h-4" />
                <span>{isLoading ? "Creating Account..." : "Create Account"}</span>
              </button>
            </form>
          )}

          {/* Clean Footer Navigation */}
          <div className="pt-6 border-t border-border/40 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
            {mode === "signin" ? (
              <button
                type="button"
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
                className="hover:text-primary transition-colors flex items-center gap-1"
              >
                <span>Don&apos;t have an account?</span>
                <span className="font-semibold text-foreground underline underline-offset-4">Sign Up</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setMode("signin");
                  setError(null);
                }}
                className="hover:text-primary transition-colors flex items-center gap-1"
              >
                <span>Already registered?</span>
                <span className="font-semibold text-foreground underline underline-offset-4">Sign In</span>
              </button>
            )}

            <Link
              href="/admin/login"
              className="text-muted-foreground hover:text-primary transition-colors flex items-center gap-1.5 font-medium"
            >
              <Shield className="w-3.5 h-3.5 text-primary" />
              <span>Admin Portal</span>
              <ArrowRight className="w-3 h-3 ml-0.5" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
