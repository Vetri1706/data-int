"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, auth, type AuthUser } from "@/lib/api";

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  signedOut: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
};
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const generation = useRef(0);
  const channel = useRef<BroadcastChannel | null>(null);

  const refresh = useCallback(async () => {
    const version = ++generation.current;
    try {
      const current = await auth.me();
      if (version === generation.current) { setUser(current); setError(null); }
    } catch (cause) {
      if (version !== generation.current) return;
      if (cause instanceof ApiError && cause.status === 401) {
        setUser(null); setError(null); queryClient.clear();
      } else {
        setError("We couldn’t check your session. Check your connection and try again.");
      }
    } finally {
      if (version === generation.current) setLoading(false);
    }
  }, [queryClient]);

  useEffect(() => {
    // Discard legacy browser-readable credentials. All new sessions use HttpOnly cookies.
    try { localStorage.removeItem("dv_token"); localStorage.removeItem("dv_user"); } catch { /* storage may be disabled */ }
    const timer = window.setTimeout(() => { void refresh(); }, 0);
    const requests = generation;
    const expire = () => {
      generation.current++; setUser(null); setError(null); setLoading(false); queryClient.clear();
    };
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    window.addEventListener("datavault:session-expired", expire);
    document.addEventListener("visibilitychange", visible);
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel("datavault-auth");
      channel.current.onmessage = (event) => { if (event.data === "logout") { setSignedOut(true); expire(); } else void refresh(); };
    }
    return () => {
      window.clearTimeout(timer);
      requests.current++;
      window.removeEventListener("datavault:session-expired", expire);
      document.removeEventListener("visibilitychange", visible);
      channel.current?.close();
    };
  }, [refresh, queryClient]);

  async function accept(result: { user: AuthUser }) {
    generation.current++; queryClient.clear(); setSignedOut(false); setUser(result.user); setError(null); setLoading(false);
    channel.current?.postMessage("login");
  }

  const value: AuthState = {
    user, loading, signedOut, error, refresh,
    signIn: async (email, password) => { await accept(await auth.login(email, password)); },
    signUp: async (email, password, name) => { await accept(await auth.register(email, password, name)); },
    signOut: async () => {
      try { await auth.logout(); }
      catch (cause) { if (!(cause instanceof ApiError && cause.status === 401)) throw cause; }
      generation.current++; queryClient.clear(); setSignedOut(true); setUser(null); setError(null); setLoading(false);
      channel.current?.postMessage("logout");
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth requires AuthProvider");
  return context;
}
