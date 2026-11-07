import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, type User } from "./api";

type State = { user: User | null; loading: boolean };
type AuthCtx = State & {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>({ user: null, loading: true });

  const refresh = useCallback(async () => {
    try {
      const token = await getToken();
      if (!token) return setState({ user: null, loading: false });
      const user = await api.me();
      setState({ user, loading: false });
    } catch {
      await setToken(null);
      setState({ user: null, loading: false });
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const login = async (email: string, password: string) => {
    const r = await api.login(email, password);
    await setToken(r.token);
    setState({ user: r.user, loading: false });
  };
  const register = async (email: string, password: string, name: string) => {
    const r = await api.register(email, password, name);
    await setToken(r.token);
    setState({ user: r.user, loading: false });
  };
  const logout = async () => {
    await setToken(null);
    setState({ user: null, loading: false });
  };

  return <Ctx.Provider value={{ ...state, login, register, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
