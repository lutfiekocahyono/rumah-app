import React, { useCallback, useEffect, useState } from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, type Store } from "@/src/api";
import { adminStyles, Chips } from "@/src/components/admin-form";
import { ScreenHeader } from "@/src/components/screen-header";
import { HomeSectionsEditor } from "@/src/components/home-sections-editor";

/** Super admin: edit the homepage section rules of any PGS branch. */
export default function AdminHomeSections() {
  const insets = useSafeAreaInsets();
  const [stores, setStores] = useState<Store[]>([]);
  const [storeId, setStoreId] = useState("pgs-official");
  useEffect(() => { api.officialStores().then(setStores).catch(() => {}); }, []);
  const load = useCallback(() => api.adminHomeSections(storeId), [storeId]);
  const save = useCallback((s: Parameters<typeof api.saveAdminHomeSections>[1]) => api.saveAdminHomeSections(storeId, s), [storeId]);
  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-home-sections-screen">
      <ScreenHeader title="Produk di Beranda" />
      <HomeSectionsEditor key={storeId} load={load} save={save}
        header={stores.length ? <Chips testID="hs-store" value={storeId} onChange={setStoreId} options={stores.map((s) => ({ id: s.store_id, label: s.name }))} /> : null} />
    </View>
  );
}
