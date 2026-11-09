import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type BranchSuggest } from "@/src/api";
import { useBuyerArea } from "@/src/components/branch-availability";
import { useStore } from "@/src/store-context";
import { useCart } from "@/src/cart-context";
import { ScreenHeader } from "@/src/components/screen-header";

export default function PickStore() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { stores, storeId, choose, distances, manual, followNearest } = useStore();
  const { refresh } = useCart();
  const area = useBuyerArea();
  const [near, setNear] = useState<BranchSuggest | null>(null);
  useEffect(() => { if (area && !distances) api.suggestStores(area).then(setNear).catch(() => {}); }, [area, distances]);
  // GPS distance first, else distance from the saved address
  const info = (id: string) => {
    const g = distances?.find((r) => r.store_id === id);
    return g ? { distance_km: g.distance_km, gps: true } : { distance_km: near?.stores.find((r) => r.store_id === id)?.distance_km ?? null, gps: false };
  };
  const nearestId = distances?.[0]?.store_id ?? near?.suggested;
  const { from } = useLocalSearchParams<{ from?: string }>();
  const back = () => { refresh(); if (router.canGoBack()) router.back(); else router.replace("/" as any); };
  // from Beranda: open the chosen branch's store page; its back button returns to Beranda
  const picked = (id: string) => { refresh(); if (from === "home") router.replace(`/shop/${id}` as any); else back(); };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="pick-store-screen">
      <ScreenHeader title="Pilih Toko" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
        <Text style={styles.sub}>Stok, harga, pesanan, dan pengiriman mengikuti toko yang dipilih.</Text>
        <Text style={styles.sub} testID="pick-store-mode">
          {manual ? "Anda memilih toko sendiri. Toko tidak berganti otomatis." : "Otomatis: toko terdekat dari lokasi Anda dipilih. Pilih toko lain untuk menggantinya."}
        </Text>
        {manual && distances?.length ? (
          <Pressable testID="pick-store-auto" style={styles.auto} onPress={async () => { await followNearest(); back(); }}>
            <Icon name="navigate" size={18} color={colors.brandPrimary} />
            <Text style={styles.autoText}>Pakai toko terdekat otomatis ({distances[0].name})</Text>
          </Pressable>
        ) : null}
        {!stores.length ? <ActivityIndicator color={colors.brandPrimary} /> : [...stores].sort((a, b) => (info(a.store_id).distance_km ?? 1e9) - (info(b.store_id).distance_km ?? 1e9)).map((s) => {
          const on = s.store_id === storeId;
          const d = info(s.store_id);
          return (
            <Pressable key={s.store_id} testID={`pick-store-${s.store_id}`} style={[styles.card, on && styles.cardOn]}
              onPress={async () => { await choose(s.store_id); picked(s.store_id); }}>
              <View style={[styles.icon, on && { backgroundColor: colors.brandPrimary }]}>
                <Icon name="storefront" size={22} color={on ? colors.onBrandPrimary : colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={styles.name}>{s.name}</Text>
                  {nearestId === s.store_id ? <View style={styles.badge} testID={`pick-store-nearest-${s.store_id}`}><Text style={styles.badgeText}>Terdekat</Text></View> : null}
                </View>
                <Text style={styles.city} testID={`pick-store-distance-${s.store_id}`}>{s.city}{d.distance_km != null ? ` · ±${d.distance_km < 1 ? "<1" : Math.round(d.distance_km)} km dari ${d.gps ? "lokasi" : "alamat"} Anda` : ""}</Text>
                {s.address ? <Text style={styles.city} numberOfLines={2}>{s.address}</Text> : null}
              </View>
              <Icon name={on ? "radio-button-on" : "radio-button-off"} size={22} color={on ? colors.brandPrimary : colors.muted} />
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  sub: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, minHeight: 72 },
  cardOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  icon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  name: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  city: { fontSize: 12, color: colors.muted },
  badge: { backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 1 },
  badgeText: { fontSize: 10, fontWeight: "700", color: colors.onBrandPrimary },
  auto: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary, paddingHorizontal: spacing.md, backgroundColor: colors.surface },
  autoText: { flex: 1, color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
});
