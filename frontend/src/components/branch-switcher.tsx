import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type BranchSuggest, type CartItem } from "@/src/api";

type Props = {
  storeId: string;
  items: CartItem[];
  area: string; // destination label or city
  pin?: { lat: number; lng: number } | null; // map pin of the chosen address (more precise)
  pickup: boolean; // "Ambil di toko" selected
  onMove: (toStoreId: string) => Promise<void>;
};

/** Checkout: nearest-branch suggestion + pickup branch picker (cart moves to the chosen branch). */
export function BranchSwitcher({ storeId, items, area, pin, pickup, onMove }: Props) {
  const [data, setData] = useState<BranchSuggest | null>(null);
  const [busy, setBusy] = useState("");
  const key = items.map((i) => `${i.product_id}:${i.quantity}`).join(",");
  useEffect(() => {
    if (!items.length) return;
    const t = setTimeout(() => {
      api.suggestStores(area, items.map((i) => i.product_id), items.map((i) => i.quantity), pin).then(setData).catch(() => {});
    }, 600); // area may come from a text field — wait until typing pauses
    return () => clearTimeout(t);
  }, [area, key, pin?.lat, pin?.lng]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return null;
  const move = async (to: string) => { setBusy(to); try { await onMove(to); } finally { setBusy(""); } };
  const current = data.stores.find((s) => s.store_id === storeId);
  const best = data.suggested && data.suggested !== storeId ? data.stores.find((s) => s.store_id === data.suggested) : null;
  const dist = (km: number | null) => (km == null ? "" : km < 10 ? "di dekat Anda · " : `±${km} km · `);

  if (pickup) {
    return (
      <View style={styles.box} testID="co-pickup-box">
        <Text style={styles.title}>Ambil di toko — tanpa ongkir</Text>
        {current ? (
          <View style={styles.pickupInfo} testID="co-pickup-store">
            <Text style={styles.name}>{current.name}</Text>
            <Text style={styles.sub}>{current.address || `${current.city} (alamat lengkap akan dikirim toko)`}</Text>
            {current.pickup_hours ? <Text style={styles.sub}>Jam ambil: {current.pickup_hours}</Text> : null}
          </View>
        ) : null}
        <Text style={styles.sub}>Mau ambil di toko lain?</Text>
        {data.stores.filter((s) => s.store_id !== storeId).map((s) => (
          <View key={s.store_id} style={styles.row} testID={`co-pickup-${s.store_id}`}>
            <View style={{ flex: 1 }}>
              <Text style={styles.name}>{s.name}{data.suggested === s.store_id ? "  · Terdekat" : ""}</Text>
              <Text style={[styles.sub, { color: s.available ? colors.success : colors.error }]}>
                {dist(s.distance_km)}{s.available ? "Semua barang tersedia" : "Sebagian barang tidak tersedia"}
              </Text>
            </View>
            {s.available ? (
              <Pressable testID={`co-pickup-switch-${s.store_id}`} style={styles.btn} disabled={!!busy} onPress={() => move(s.store_id)}>
                {busy === s.store_id ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.btnText}>Ambil di sini</Text>}
              </Pressable>
            ) : null}
          </View>
        ))}
      </View>
    );
  }

  if (!best) return null;
  return (
    <View style={[styles.box, styles.banner]} testID="co-nearest-banner">
      <Icon name="navigate-circle-outline" size={22} color={colors.brandPrimary} />
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{best.name} lebih dekat</Text>
        <Text style={styles.sub}>{dist(best.distance_km)}stok semua barang tersedia{current?.distance_km != null ? ` (toko sekarang ±${current.distance_km} km)` : ""}</Text>
      </View>
      <Pressable testID="co-nearest-switch" style={styles.btn} disabled={!!busy} onPress={() => move(best.store_id)}>
        {busy ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.btnText}>Pindah</Text>}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm },
  banner: { flexDirection: "row", alignItems: "center" },
  title: { fontSize: fontSize.sm, fontWeight: "700", color: colors.onSurface },
  pickupInfo: { backgroundColor: colors.surface, borderRadius: radius.sm, padding: spacing.sm, gap: 2 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48 },
  name: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  sub: { fontSize: 12, color: colors.onSurfaceSecondary },
  btn: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 44, justifyContent: "center", backgroundColor: colors.surface },
  btnText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
});
