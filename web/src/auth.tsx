import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  chatRequiresLogin: boolean;
  refresh: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [chatRequiresLogin, setChatRequiresLogin] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api<{ user: User | null; chat_requires_login: boolean }>("/api/auth/me");
      setUser(data.user);
      setChatRequiresLogin(data.chat_requires_login);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signIn = async (email: string, password: string) => {
    const data = await api<{ user: User }>("/api/auth/login", { method: "POST", json: { email, password } });
    setUser(data.user);
    return data.user;
  };

  const signOut = async () => {
    await api("/api/auth/logout", { method: "POST" });
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, chatRequiresLogin, refresh, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}
