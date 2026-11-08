import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Chips } from "@/src/components/admin-form";
import { fmtDate } from "@/src/utils/date";

const FILTERS = [
  { id: "new", label: "Pesanan Baru" }, { id: "pending", label: "Belum Bayar" }, { id: "processing", label: "Diproses" },
  { id: "shipped", label: "Dikirim" }, { id: "completed", label: "Selesai" }, { id: "cancelled", label: "Batal" }, { id: "all", label: "Semua" },
];

export default function SellerOrders() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [filter, setFilter] = useState("new");
  const [list, setList] = useState<Order[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setList(await api.sellerOrders(filter === "all" ? undefined : filter)); } catch { setList([]); }
  }, [filter]);
  useFocusEffect(useCallback(() => { setList(null); void load(); }, [load]));

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="seller-orders-screen">
      <ScreenHeader title="Pesanan Toko" />
      <View style={{ padding: spacing.lg, paddingBottom: 0 }}>
        <Chips testID="so-filter" value={filter} onChange={setFilter} options={FILTERS} />
      </View>
      {list === null ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={list}
          keyExtractor={(o) => o.order_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.brandPrimary} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
          ListEmptyComponent={<Text style={adminStyles.muted}>Tidak ada pesanan.</Text>}
          renderItem={({ item: o }) => (
            <Pressable testID={`so-${o.order_id}`} style={styles.card} onPress={() => router.push(`/seller/order/${o.order_id}` as any)}>
              <View style={styles.between}>
                <Text style={styles.id}>{o.order_id}</Text>
                <Text style={styles.status}>{ORDER_STATUS_LABEL[o.status]}</Text>
              </View>
              <Text style={adminStyles.muted}>{fmtDate(o.created_at)} · {o.shipping.full_name} · {o.courier?.name ?? "-"}</Text>
              <Text style={styles.items} numberOfLines={1}>{o.items.map((i) => `${i.name} x${i.quantity}`).join(", ")}</Text>
              <Text style={styles.total}>{formatIDR(o.total)}</Text>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  between: { flexDirection: "row", justifyContent: "space-between" },
  id: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  status: { fontSize: 12, fontWeight: "600", color: colors.brandPrimary },
  items: { fontSize: 13, color: colors.onSurfaceSecondary },
  total: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
});
