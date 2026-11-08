import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { api, setCurrentStore, type Store } from "@/src/api";

const KEY = "pgs_store_id";
type Ctx = { storeId: string; store: Store | null; stores: Store[]; ready: boolean; chosen: boolean; choose: (id: string) => Promise<void> };
const StoreCtx = createContext<Ctx | null>(null);

/** Which official branch the buyer shops from. Persisted; defaults to PGS Sidoarjo. */
export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [storeId, setStoreId] = useState("pgs-official");
  const [stores, setStores] = useState<Store[]>([]);
  const [ready, setReady] = useState(false);
  const [chosen, setChosen] = useState(false);

  useEffect(() => {
    (async () => {
      const saved = await AsyncStorage.getItem(KEY).catch(() => null);
      if (saved) { setCurrentStore(saved); setStoreId(saved); setChosen(true); }
      setReady(true);
      api.officialStores().then(setStores).catch(() => {});
    })();
  }, []);

  const choose = useCallback(async (id: string) => {
    setCurrentStore(id);
    setStoreId(id);
    setChosen(true);
    await AsyncStorage.setItem(KEY, id).catch(() => {});
  }, []);

  return (
    <StoreCtx.Provider value={{ storeId, store: stores.find((s) => s.store_id === storeId) ?? null, stores, ready, chosen, choose }}>
      {children}
    </StoreCtx.Provider>
  );
}

export function useStore(): Ctx {
  const v = useContext(StoreCtx);
  if (!v) throw new Error("useStore outside StoreProvider");
  return v;
}
