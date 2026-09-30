"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { AuthTokenResponse } from "@/types/api";

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  role: string;
  displayName?: string | null;
  organizationId?: string;
  organizationName?: string;
}

export interface SignupParams {
  username: string;
  email: string;
  password?: string;
  displayName?: string;
  organizationName?: string;
  role?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password?: string, role?: string) => Promise<void>;
  adminLogin: (username: string, password?: string) => Promise<void>;
  signup: (params: SignupParams) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = "agentspace_token";
const USER_KEY = "agentspace_user";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  // Load session from localStorage on initial mount
  useEffect(() => {
    try {
      const storedToken = localStorage.getItem(TOKEN_KEY);
      const storedUser = localStorage.getItem(USER_KEY);
      if (storedToken && storedUser) {
        setToken(storedToken);
        setUser(JSON.parse(storedUser));
      } else {
        // No session stored — require user to sign in or register
        setToken(null);
        setUser(null);
      }
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(
    async (username: string, password?: string, role?: string) => {
      setIsLoading(true);
      try {
        const response = await apiFetch<AuthTokenResponse>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({
            username: username.trim(),
            password: password?.trim() || undefined,
            role: role || undefined,
          }),
        });

        const authenticatedUser: AuthUser = {
          id: response.user.id,
          username: response.user.username,
          email: response.user.email,
          role: response.user.role,
          displayName: response.user.display_name,
          organizationId: response.user.organization?.id,
          organizationName: response.user.organization?.name,
        };

        setToken(response.access_token);
        setUser(authenticatedUser);
        localStorage.setItem(TOKEN_KEY, response.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(authenticatedUser));
        router.push("/");
      } catch (err) {
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const adminLogin = useCallback(
    async (username: string, password?: string) => {
      setIsLoading(true);
      try {
        const response = await apiFetch<AuthTokenResponse>("/api/v1/auth/admin/login", {
          method: "POST",
          body: JSON.stringify({
            username: username.trim(),
            password: password?.trim() || undefined,
          }),
        });

        const authenticatedUser: AuthUser = {
          id: response.user.id,
          username: response.user.username,
          email: response.user.email,
          role: response.user.role,
          displayName: response.user.display_name,
          organizationId: response.user.organization?.id,
          organizationName: response.user.organization?.name,
        };

        setToken(response.access_token);
        setUser(authenticatedUser);
        localStorage.setItem(TOKEN_KEY, response.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(authenticatedUser));
        router.push("/");
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const signup = useCallback(
    async (params: SignupParams) => {
      setIsLoading(true);
      try {
        const response = await apiFetch<AuthTokenResponse>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({
            username: params.username.trim(),
            email: params.email.trim(),
            password: params.password?.trim() || undefined,
            display_name: params.displayName?.trim() || params.username.trim(),
            organization_name: params.organizationName?.trim() || undefined,
          }),
        });

        const authenticatedUser: AuthUser = {
          id: response.user.id,
          username: response.user.username,
          email: response.user.email,
          role: response.user.role,
          displayName: response.user.display_name,
          organizationId: response.user.organization?.id,
          organizationName: response.user.organization?.name,
        };

        setToken(response.access_token);
        setUser(authenticatedUser);
        localStorage.setItem(TOKEN_KEY, response.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(authenticatedUser));
        router.push("/");
      } catch (err) {
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        login,
        adminLogin,
        signup,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
