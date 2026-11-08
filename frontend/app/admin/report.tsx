import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Report } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles } from "@/src/components/admin-form";

export default function AdminReport() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<{ all: Report; stores: (Report & { store_id: string; name: string })[] } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.adminReport().then(setData).catch((e) => setErr(e.message)); }, []);

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-report-screen">
      <ScreenHeader title="Laporan Pendapatan" />
      {!data ? (err ? <Text style={[adminStyles.err, { padding: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
          <View style={styles.total}>
            <Text style={styles.totalLabel}>Total pendapatan selesai (semua toko)</Text>
            <Text style={styles.totalVal} testID="report-total">{formatIDR(data.all.revenue_completed)}</Text>
            <Text style={styles.totalLabel}>Pesanan berjalan: {formatIDR(data.all.revenue_in_progress)}</Text>
          </View>
          {data.stores.map((s) => (
            <View key={s.store_id} style={styles.card} testID={`report-store-${s.store_id}`}>
              <View style={styles.between}>
                <Text style={styles.name}>{s.name}</Text>
                <Pressable hitSlop={8} onPress={() => router.push({ pathname: "/admin/store-couriers/[id]", params: { id: s.store_id, name: s.name } } as any)}>
                  <Text style={styles.link}>Tarif kurir</Text>
                </Pressable>
              </View>
              <Text style={styles.val}>{formatIDR(s.revenue_completed)}</Text>
              <Text style={adminStyles.muted}>{s.orders_completed} pesanan selesai · berjalan {formatIDR(s.revenue_in_progress)}</Text>
              {s.top_products[0] ? <Text style={adminStyles.muted} numberOfLines={1}>Terlaris: {s.top_products[0].name} ({s.top_products[0].qty})</Text> : null}
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  total: { backgroundColor: colors.brandPrimary, borderRadius: radius.md, padding: spacing.lg, gap: 4 },
  totalLabel: { color: colors.onBrandPrimary, fontSize: 12 },
  totalVal: { color: colors.onBrandPrimary, fontSize: 24, fontWeight: "700" },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  name: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  val: { fontSize: fontSize.lg, fontWeight: "700", color: colors.brandPrimary },
  link: { color: colors.brandPrimary, fontSize: 13, fontWeight: "500" },
});
