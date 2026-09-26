"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  apiFetch,
  setSessionRefresher,
  type ApiOptions,
  type AuthResponse,
  type User,
} from "@/lib/api";

type AuthContextValue = {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (u: User) => void;
  api: <T>(path: string, init?: ApiOptions) => Promise<T>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (): Promise<string | null> => {
    try {
      const data = await apiFetch<AuthResponse>("/auth/refresh", {
        method: "POST",
      });
      setToken(data.accessToken);
      setUser(data.user);
      return data.accessToken;
    } catch {
      setToken(null);
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Silent session restore on mount + register refresher for apiFetch retries.
  useEffect(() => {
    setSessionRefresher(refresh);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- session bootstrap: setState lands post-await in refresh()'s finally, not synchronously here
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiFetch<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.accessToken);
    setUser(data.user);
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      await apiFetch("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, fullName }),
      });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    const t = token;
    setToken(null);
    setUser(null);
    try {
      await apiFetch("/auth/logout", { method: "POST", token: t });
    } catch {
      // Local state is already cleared; ignore server errors on logout.
    }
  }, [token]);

  const api = useCallback(
    <T,>(path: string, init: ApiOptions = {}) =>
      apiFetch<T>(path, { ...init, token }),
    [token],
  );

  const value = useMemo(
    () => ({ user, token, loading, login, register, logout, setUser, api }),
    [user, token, loading, login, register, logout, api],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
