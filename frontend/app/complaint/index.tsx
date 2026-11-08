import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Complaint } from "@/src/api";
import { StatusPill } from "@/src/components/complaint-pill";
import { ScreenHeader } from "@/src/components/screen-header";
import { Chips } from "@/src/components/admin-form";
import { fmtDate } from "@/src/utils/date";

const FILTERS = [
  { id: "active", label: "Perlu Ditangani" }, { id: "refunded", label: "Refund" }, { id: "rejected", label: "Ditolak" },
  { id: "resolved", label: "Selesai" }, { id: "all", label: "Semua" },
];

/** ?scope=mine (pembeli) | store (admin cabang) | admin (super admin, semua toko). */
export default function ComplaintList() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ scope?: string }>();
  const scope = (params.scope === "store" || params.scope === "admin" ? params.scope : "mine") as "mine" | "store" | "admin";
  const [filter, setFilter] = useState(scope === "mine" ? "all" : "active");
  const [list, setList] = useState<Complaint[] | null>(null);
  const [err, setErr] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setErr(""); setList(await api.complaints(scope, scope === "mine" || filter === "all" ? "" : filter)); } catch (e: any) { setErr(e.message); setList([]); }
  }, [scope, filter]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const title = scope === "mine" ? "Komplain Saya" : scope === "store" ? "Komplain Toko" : "Komplain & Refund";

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="complaint-list-screen">
      <ScreenHeader title={title} />
      {scope !== "mine" ? (
        <View style={{ padding: spacing.lg, paddingBottom: 0 }}>
          <Chips testID="cl-filter" value={filter} onChange={(v) => { setList(null); setFilter(v); }} options={FILTERS} />
        </View>
      ) : null}
      {list === null ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={list}
          keyExtractor={(c) => c.complaint_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1 }}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.brandPrimary} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Icon name="shield-checkmark-outline" size={48} color={colors.muted} />
              <Text style={styles.muted}>{err || (scope === "mine" ? "Belum ada komplain. Komplain diajukan dari halaman detail pesanan." : "Tidak ada komplain.")}</Text>
            </View>
          }
          renderItem={({ item: c }) => (
            <Pressable testID={`cl-${c.complaint_id}`} style={styles.card} onPress={() => router.push(`/complaint/${c.complaint_id}` as any)}>
              <View style={styles.between}>
                <Text style={styles.id}>{c.complaint_id}</Text>
                <StatusPill status={c.status} />
              </View>
              <Text style={styles.muted}>{c.order_id} · {scope === "mine" ? c.store_name : `${c.user_name}${scope === "admin" ? ` · ${c.store_name}` : ""}`}</Text>
              <Text style={styles.reason}>{c.reason_label}{c.refund_amount ? ` · minta refund ${formatIDR(c.refund_amount)}` : ""}</Text>
              <Text style={styles.time}>{fmtDate(c.updated_at)}</Text>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  between: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  id: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  reason: { fontSize: fontSize.sm, color: colors.onSurface },
  muted: { fontSize: 13, color: colors.muted, textAlign: "left" },
  time: { fontSize: 11, color: colors.muted },
});
