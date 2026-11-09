import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { api, setCurrentStore, type NearestStores, type Store } from "@/src/api";

const KEY = "pgs_store_id";
const MANUAL_KEY = "pgs_store_manual"; // buyer picked a branch by hand: GPS no longer switches it
type AutoPick = { store_id: string; name: string; distance_km: number; at: number };
type Ctx = {
  storeId: string; store: Store | null; stores: Store[]; ready: boolean; chosen: boolean; manual: boolean;
  choose: (id: string) => Promise<void>; followNearest: () => Promise<void>;
  distances: NearestStores["stores"] | null; autoPicked: AutoPick | null;
  autoPick: (lat: number, lng: number) => Promise<void>;
};
const StoreCtx = createContext<Ctx | null>(null);

/** Which official branch the buyer shops from. Persisted; follows the nearest branch (GPS) until the buyer picks one manually. */
export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [storeId, setStoreId] = useState("pgs-official");
  const [stores, setStores] = useState<Store[]>([]);
  const [ready, setReady] = useState(false);
  const [chosen, setChosen] = useState(false);
  const [manual, setManual] = useState(false);
  const [distances, setDistances] = useState<NearestStores["stores"] | null>(null);
  const [autoPicked, setAutoPicked] = useState<AutoPick | null>(null);
  const cur = useRef({ storeId: "pgs-official", manual: false, ready: false });
  const pending = useRef<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    (async () => {
      const [saved, man] = await Promise.all([AsyncStorage.getItem(KEY).catch(() => null), AsyncStorage.getItem(MANUAL_KEY).catch(() => null)]);
      if (saved) { setCurrentStore(saved); setStoreId(saved); setChosen(true); cur.current.storeId = saved; }
      if (man === "1" && saved) { setManual(true); cur.current.manual = true; }
      cur.current.ready = true;
      setReady(true);
      api.officialStores().then(setStores).catch(() => {});
    })();
  }, []);

  const set = useCallback(async (id: string, byHand: boolean) => {
    setCurrentStore(id);
    setStoreId(id);
    setChosen(true);
    setManual(byHand);
    cur.current = { ...cur.current, storeId: id, manual: byHand };
    await AsyncStorage.multiSet([[KEY, id], [MANUAL_KEY, byHand ? "1" : "0"]]).catch(() => {});
  }, []);
  const choose = useCallback((id: string) => set(id, true), [set]);

  const autoPick = useCallback(async (lat: number, lng: number) => {
    const r = await api.nearestStores(lat, lng).catch(() => null);
    if (!r?.nearest) return;
    setDistances(r.stores);
    const c = cur.current;
    if (!c.ready) { pending.current = { lat, lng }; return; } // retried once the saved branch is loaded
    if (c.manual || c.storeId === r.nearest.store_id) return;
    await set(r.nearest.store_id, false);
    setAutoPicked({ ...r.nearest, at: Date.now() });
  }, [set]);

  useEffect(() => {
    if (ready && pending.current) { const p = pending.current; pending.current = null; void autoPick(p.lat, p.lng); }
  }, [ready, autoPick]);

  const followNearest = useCallback(async () => { // back to automatic: nearest branch from the last GPS fix
    const n = distances?.[0];
    await set(n?.store_id ?? cur.current.storeId, false);
  }, [distances, set]);

  return (
    <StoreCtx.Provider value={{ storeId, store: stores.find((s) => s.store_id === storeId) ?? null, stores, ready, chosen, manual, choose, followNearest, distances, autoPicked, autoPick }}>
      {children}
    </StoreCtx.Provider>
  );
}

export function useStore(): Ctx {
  const v = useContext(StoreCtx);
  if (!v) throw new Error("useStore outside StoreProvider");
  return v;
}
