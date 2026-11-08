import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Wallet } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { fmtDate } from "@/src/utils/date";

const KIND = { refund: "Refund komplain", payment: "Dipakai belanja", return: "Saldo dikembalikan" } as const;

export default function WalletScreen() {
  const insets = useSafeAreaInsets();
  const [w, setW] = useState<Wallet | null>(null);
  const [err, setErr] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async () => { try { setErr(""); setW(await api.wallet()); } catch (e: any) { setErr(e.message); } }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="wallet-screen">
      <ScreenHeader title="Saldo Saya" />
      {!w ? (err ? <Text style={styles.err}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />) : (
        <FlatList
          data={w.transactions}
          keyExtractor={(t) => t.tx_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.brandPrimary} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
          ListHeaderComponent={
            <View style={{ gap: spacing.md, marginBottom: spacing.sm }}>
              <View style={styles.hero}>
                <Icon name="wallet-outline" size={28} color={colors.onBrandPrimary} />
                <Text style={styles.heroLabel}>Saldo tersedia</Text>
                <Text style={styles.heroValue} testID="wallet-balance">{formatIDR(w.balance)}</Text>
                <Text style={styles.heroSub}>Bisa dipakai saat checkout di toko mana pun.</Text>
              </View>
              <Text style={styles.section}>Riwayat</Text>
            </View>
          }
          ListEmptyComponent={<Text style={styles.muted}>Belum ada transaksi saldo. Refund komplain yang disetujui akan masuk ke sini.</Text>}
          renderItem={({ item: t }) => (
            <View style={styles.row}>
              <Icon name={t.amount > 0 ? "arrow-down-circle-outline" : "arrow-up-circle-outline"} size={24} color={t.amount > 0 ? colors.success : colors.muted} />
              <View style={{ flex: 1 }}>
                <Text style={styles.kind}>{KIND[t.kind] ?? t.kind}</Text>
                <Text style={styles.muted} numberOfLines={2}>{t.note}</Text>
                <Text style={styles.time}>{fmtDate(t.created_at)}</Text>
              </View>
              <Text style={[styles.amount, { color: t.amount > 0 ? colors.success : colors.onSurface }]}>{t.amount > 0 ? "+" : "-"}{formatIDR(Math.abs(t.amount))}</Text>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  err: { color: colors.error, padding: spacing.lg },
  hero: { backgroundColor: colors.brandPrimary, borderRadius: radius.md, padding: spacing.lg, gap: 4 },
  heroLabel: { color: colors.onBrandPrimary, fontSize: fontSize.sm, opacity: 0.9 },
  heroValue: { color: colors.onBrandPrimary, fontSize: 28, fontWeight: "700" },
  heroSub: { color: colors.onBrandPrimary, fontSize: 12, opacity: 0.85 },
  section: { fontSize: fontSize.sm, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  kind: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  muted: { fontSize: 12, color: colors.muted },
  time: { fontSize: 11, color: colors.muted, marginTop: 2 },
  amount: { fontSize: fontSize.base, fontWeight: "700" },
});
