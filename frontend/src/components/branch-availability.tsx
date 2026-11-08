import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type BranchSuggest } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { useStore } from "@/src/store-context";

/** The buyer's area for "nearest branch": default saved address area, else its city. */
export function useBuyerArea(): string {
  const { user } = useAuth();
  const [area, setArea] = useState("");
  useEffect(() => {
    if (!user) { setArea(""); return; }
    api.addresses().then((l) => {
      const d = l.find((a) => a.is_default) ?? l[0];
      setArea(d ? d.destination_label || d.city : "");
    }).catch(() => {});
  }, [user]);
  return area;
}

export function stockText(n: number) {
  if (n <= 0) return "Stok habis";
  if (n >= 9999) return "Stok tersedia";
  return n <= 5 ? `Sisa ${n}` : `Stok ${n}`;
}

/** Product page: stock at every branch, nearest first, with a one-tap switch. */
export function BranchAvailability({ productId, onSwitched }: { productId: string; onSwitched: () => void }) {
  const area = useBuyerArea();
  const { storeId, choose } = useStore();
  const [data, setData] = useState<BranchSuggest | null>(null);
  useEffect(() => { api.productAvailability(productId, area).then(setData).catch(() => {}); }, [productId, area]);

  return (
    <View style={styles.box} testID="pd-branch-stock">
      <Text style={styles.title}>Ketersediaan di toko</Text>
      {!data ? <ActivityIndicator color={colors.brandPrimary} /> : data.stores.map((s) => {
        const n = s.stock[productId] ?? 0;
        const here = s.store_id === storeId;
        return (
          <View key={s.store_id} style={styles.row} testID={`pd-branch-${s.store_id}`}>
            <Icon name="storefront-outline" size={18} color={here ? colors.brandPrimary : colors.onSurfaceSecondary} />
            <View style={{ flex: 1 }}>
              <View style={styles.nameRow}>
                <Text style={[styles.name, here && { color: colors.brandPrimary }]} numberOfLines={1}>{s.name}</Text>
                {data.suggested === s.store_id ? <View style={styles.badge}><Text style={styles.badgeText}>Terdekat</Text></View> : null}
              </View>
              <Text style={styles.sub}>
                {s.distance_km != null ? (s.distance_km < 10 ? "Di dekat Anda · " : `±${s.distance_km} km · `) : ""}<Text style={{ color: n > 0 ? colors.success : colors.error, fontWeight: "600" }}>{stockText(n)}</Text>
              </Text>
            </View>
            {here ? <Text style={styles.here}>Toko Anda</Text> : n > 0 ? (
              <Pressable testID={`pd-branch-switch-${s.store_id}`} style={styles.btn} onPress={async () => { await choose(s.store_id); onSwitched(); }}>
                <Text style={styles.btnText}>Belanja di sini</Text>
              </Pressable>
            ) : null}
          </View>
        );
      })}
      {data && !data.located ? <Text style={styles.hint}>Simpan alamat dengan area ongkir untuk melihat toko terdekat.</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, padding: spacing.md, gap: spacing.sm },
  title: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48 },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface, flexShrink: 1 },
  sub: { fontSize: 12, color: colors.muted },
  badge: { backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 1 },
  badgeText: { fontSize: 10, fontWeight: "700", color: colors.brandPrimary },
  here: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  btn: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 44, justifyContent: "center" },
  btnText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  hint: { fontSize: 12, color: colors.muted },
});
