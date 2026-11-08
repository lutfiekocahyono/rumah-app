import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ScrollView, TextInput, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

const FILTERS: { id: string; label: string }[] = [
  { id: "", label: "Semua" },
  { id: "paid", label: "Dibayar" },
  { id: "cod", label: "COD" },
  { id: "pending", label: "Menunggu Bayar" },
  { id: "processing", label: "Diproses" },
  { id: "shipped", label: "Dikirim" },
  { id: "completed", label: "Selesai" },
  { id: "cancelled", label: "Dibatalkan" },
];

export function statusColor(s: Order["status"]) {
  if (s === "paid" || s === "completed") return colors.success;
  if (s === "pending" || s === "cod") return colors.warning;
  if (s === "processing" || s === "shipped") return colors.info;
  return colors.error;
}

export default function AdminOrders() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrders(await api.adminOrders(filter || undefined, q.trim() || undefined));
    } catch {
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, [filter, q]);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => { void load(); }, 250);
    return () => clearTimeout(t);
  }, [load]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-orders-screen">
      <ScreenHeader title="Pesanan Masuk" />
      <View style={styles.top}>
        <View style={styles.search}>
          <Icon name="search" size={18} color={colors.muted} />
          <TextInput testID="admin-order-search" placeholder="Cari no. pesanan, nama, HP" placeholderTextColor={colors.muted}
            value={q} onChangeText={setQ} style={styles.searchInput} autoCapitalize="none" />
        </View>
      </View>
      <View style={styles.chipsWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
          {FILTERS.map((f) => {
            const active = f.id === filter;
            return (
              <Pressable key={f.id || "all"} testID={`order-filter-${f.id || "all"}`} style={[styles.chip, active && styles.chipActive]} onPress={() => setFilter(f.id)}>
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{f.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
      {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={orders}
          keyExtractor={(o) => o.order_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={<Text style={styles.empty}>Belum ada pesanan</Text>}
          renderItem={({ item }) => (
            <Pressable style={styles.card} testID={`admin-order-${item.order_id}`} onPress={() => router.push(`/admin/order/${item.order_id}` as any)}>
              <View style={styles.cardTop}>
                <Text style={styles.orderId}>{item.order_id}</Text>
                <View style={[styles.badge, { borderColor: statusColor(item.status) }]}>
                  <Text style={[styles.badgeText, { color: statusColor(item.status) }]}>{ORDER_STATUS_LABEL[item.status]}</Text>
                </View>
              </View>
              <Text style={styles.name}>{item.shipping.full_name} · {item.shipping.phone}</Text>
              <View style={styles.cardTop}>
                <Text style={styles.muted}>{new Date(item.created_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" })} · {item.items.length} produk</Text>
                <Text style={styles.total}>{formatIDR(item.total)}</Text>
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  top: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  searchInput: { flex: 1, color: colors.onSurface, paddingVertical: 12 },
  chipsWrap: { height: 56, justifyContent: "center" },
  chipsRow: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, justifyContent: "center", flexShrink: 0 },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontSize: fontSize.sm },
  chipTextActive: { color: colors.onBrandPrimary },
  empty: { textAlign: "center", color: colors.muted, marginTop: spacing.xl },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 6, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  orderId: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  badge: { borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2 },
  badgeText: { fontSize: 11, fontWeight: "500" },
  name: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  muted: { fontSize: 12, color: colors.muted, flex: 1 },
  total: { fontSize: fontSize.base, color: colors.brandPrimary, fontWeight: "500" },
});
