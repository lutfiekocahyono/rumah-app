import React from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";

export default function OrderSuccess() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { order_id, total } = useLocalSearchParams<{ order_id: string; total: string }>();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="order-success">
      <View style={styles.center}>
        <View style={styles.iconWrap}>
          <Icon name="checkmark" size={46} color={colors.onSuccess} />
        </View>
        <Text style={styles.title}>Pembayaran Berhasil!</Text>
        <Text style={styles.subtitle}>Terima kasih telah berbelanja di Pusat Grosir Sidoarjo.</Text>

        <View style={styles.card}>
          <Row label="Nomor Pesanan" value={order_id ?? "—"} />
          <Row label="Total Pembayaran" value={formatIDR(Number(total ?? 0))} highlight />
          <Row label="Status" value="Berhasil Dibayar" />
        </View>
      </View>
      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.lg, insets.bottom + spacing.sm) }]}>
        <Pressable testID="to-orders" style={styles.outlineBtn} onPress={() => router.replace("/orders" as any)}>
          <Text style={styles.outlineText}>Lihat Pesanan</Text>
        </Pressable>
        <Pressable testID="back-home" style={styles.primaryBtn} onPress={() => router.replace("/(tabs)" as any)}>
          <Text style={styles.primaryText}>Kembali ke Beranda</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, highlight && { color: colors.brandPrimary, fontSize: fontSize.lg, fontWeight: "500" }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface, justifyContent: "space-between" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  iconWrap: { width: 88, height: 88, borderRadius: 44, backgroundColor: colors.success, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, color: colors.onSurface, fontWeight: "500" },
  subtitle: { fontSize: fontSize.sm, color: colors.muted, textAlign: "center", maxWidth: 300 },
  card: { width: "100%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, gap: spacing.sm, marginTop: spacing.md },
  row: { flexDirection: "row", justifyContent: "space-between" },
  rowLabel: { color: colors.muted, fontSize: fontSize.sm },
  rowValue: { color: colors.onSurface, fontSize: fontSize.sm, fontWeight: "500" },
  bottom: { flexDirection: "row", gap: spacing.sm, padding: spacing.lg },
  outlineBtn: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center" },
  outlineText: { color: colors.onSurface, fontWeight: "500" },
  primaryBtn: { flex: 1, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center" },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "500" },
});
