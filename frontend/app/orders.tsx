import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Order } from "@/src/api";

export default function Orders() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.orders().then((o) => { setOrders(o); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="orders-screen">
      <View style={styles.header}>
        <Pressable testID="orders-back" hitSlop={8} onPress={() => router.back()}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Daftar Pesanan</Text>
        <View style={{ width: 24 }} />
      </View>
      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : orders.length === 0 ? (
        <View style={styles.empty}>
          <Icon name="receipt-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Belum ada pesanan</Text>
        </View>
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(o) => o.order_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}
          renderItem={({ item }) => (
            <View style={styles.card} testID={`order-${item.order_id}`}>
              <View style={styles.cardHeader}>
                <Text style={styles.orderId}>{item.order_id}</Text>
                <View style={styles.statusBadge}>
                  <Text style={styles.statusText}>{item.status.toUpperCase()}</Text>
                </View>
              </View>
              {item.items.slice(0, 2).map((it) => (
                <View key={it.product_id} style={styles.orderRow}>
                  <Image source={it.image} style={styles.rowImg} contentFit="cover" />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowName} numberOfLines={2}>{it.name}</Text>
                    <Text style={styles.rowQty}>x{it.quantity} · {formatIDR(it.price)}</Text>
                  </View>
                </View>
              ))}
              {item.items.length > 2 ? <Text style={styles.more}>+{item.items.length - 2} produk lain</Text> : null}
              <View style={styles.cardFooter}>
                <Text style={styles.totalLabel}>Total</Text>
                <Text style={styles.totalValue}>{formatIDR(item.total)}</Text>
              </View>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  emptyText: { color: colors.muted, fontSize: fontSize.sm },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, gap: spacing.sm },
  cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  orderId: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  statusBadge: { backgroundColor: colors.brandTertiary, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  statusText: { color: colors.brandPrimary, fontSize: 10, fontWeight: "500" },
  orderRow: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  rowImg: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  rowName: { fontSize: fontSize.sm, color: colors.onSurface },
  rowQty: { fontSize: 11, color: colors.muted, marginTop: 2 },
  more: { fontSize: 11, color: colors.muted },
  cardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: spacing.sm },
  totalLabel: { color: colors.muted, fontSize: fontSize.sm },
  totalValue: { color: colors.brandPrimary, fontSize: fontSize.base, fontWeight: "500" },
});
