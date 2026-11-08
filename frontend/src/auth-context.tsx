import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, getToken, setToken, type User } from "./api";
import { cleanWebUrl, extractSessionId, initialWebSessionId, startGoogleLogin } from "./google-auth";
import * as Linking from "expo-linking";
import { Platform } from "react-native";

type State = { user: User | null; loading: boolean };
type AuthCtx = State & {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  loginWithGoogle: () => Promise<boolean>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>({ user: null, loading: true });
  const used = useRef(new Set<string>());

  const exchange = useCallback(async (sid: string | null): Promise<boolean> => {
    if (!sid || used.current.has(sid)) return false;
    used.current.add(sid);
    try {
      const r = await api.googleSession(sid);
      await setToken(r.token);
      setState({ user: r.user, loading: false });
      cleanWebUrl();
      return true;
    } catch {
      return false;
    }
  }, []);

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

  useEffect(() => {
    (async () => {
      // A Google redirect wins over any stored session.
      if (await exchange(initialWebSessionId)) return;
      if (Platform.OS !== "web" && (await exchange(extractSessionId(await Linking.getInitialURL())))) return;
      await refresh();
    })();
    if (Platform.OS === "web") return;
    const sub = Linking.addEventListener("url", ({ url }) => { void exchange(extractSessionId(url)); });
    return () => sub.remove();
  }, [refresh, exchange]);

  const loginWithGoogle = async () => exchange(await startGoogleLogin());

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

  return <Ctx.Provider value={{ ...state, login, register, loginWithGoogle, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
