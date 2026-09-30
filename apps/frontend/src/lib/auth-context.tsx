"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { useRouter } from "next/navigation";

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  role: string;
  organizationId?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, token?: string) => Promise<void>;
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
        // Default local dev admin session for instant collaboration
        const devUser: AuthUser = {
          id: "dev-admin-id",
          username: "admin_a",
          email: "admin@agentspace.local",
          role: "ORG_ADMIN",
        };
        const devToken = "mock-dev-token";
        setToken(devToken);
        setUser(devUser);
        localStorage.setItem(TOKEN_KEY, devToken);
        localStorage.setItem(USER_KEY, JSON.stringify(devUser));
      }
    } catch {
      // Fallback
    } finally {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(
    async (username: string, customToken?: string) => {
      setIsLoading(true);
      try {
        const authToken = customToken || `dev-token-${username}-${Date.now()}`;
        const authenticatedUser: AuthUser = {
          id: `usr-${username}-${Date.now()}`,
          username,
          email: `${username}@agentspace.local`,
          role: "ORG_ADMIN",
        };

        setToken(authToken);
        setUser(authenticatedUser);
        localStorage.setItem(TOKEN_KEY, authToken);
        localStorage.setItem(USER_KEY, JSON.stringify(authenticatedUser));
        router.push("/");
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
