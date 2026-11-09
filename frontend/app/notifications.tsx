import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, spacing } from "@/src/theme";
import { api, type AppNotification } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles } from "@/src/components/admin-form";
import { fmtDate } from "@/src/utils/date";

const KIND = {
  order: { icon: "receipt-outline", label: "Pesanan" },
  promo: { icon: "pricetag-outline", label: "Promo" },
  security: { icon: "shield-checkmark-outline", label: "Akun" },
  product: { icon: "cube-outline", label: "Produk" },
} as const;

export default function Notifications() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [filter, setFilter] = useState<"all" | AppNotification["kind"]>("all");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!user) return setItems([]);
    try { setItems(await api.notifications()); } catch { setItems([]); }
  }, [user]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const open = async (n: AppNotification) => {
    if (!n.read) {
      setItems((l) => l?.map((x) => (x.notif_id === n.notif_id ? { ...x, read: true } : x)) ?? l);
      api.readOne(n.notif_id).catch(() => {});
    }
    if (n.link) router.push(n.link as any);
  };

  const shown = (items ?? []).filter((n) => filter === "all" || n.kind === filter);

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="notifications-screen">
      <ScreenHeader title="Notifikasi" />
      <View style={styles.tabs}>
        {(["all", "order", "product", "promo", "security"] as const).map((k) => (
          <Pressable key={k} testID={`notif-tab-${k}`} onPress={() => setFilter(k)} style={[styles.tab, filter === k && styles.tabOn]}>
            <Text style={[styles.tabText, filter === k && styles.tabTextOn]}>{k === "all" ? "Semua" : KIND[k].label}</Text>
          </Pressable>
        ))}
      </View>
      {items?.some((n) => !n.read) ? (
        <Pressable testID="notif-read-all" hitSlop={8} style={styles.readAllRow} onPress={async () => { await api.readAll(); setItems((l) => l?.map((n) => ({ ...n, read: true })) ?? l); }}>
          <Text style={styles.readAll}>Tandai semua dibaca</Text>
        </Pressable>
      ) : null}
      {!user ? (
        <Text style={[adminStyles.muted, styles.empty]}>Masuk untuk melihat notifikasi.</Text>
      ) : items === null ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={shown}
          keyExtractor={(n) => n.notif_id}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.brandPrimary} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
          contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }}
          ListEmptyComponent={<Text style={[adminStyles.muted, styles.empty]}>Belum ada notifikasi.</Text>}
          renderItem={({ item: n }) => (
            <Pressable testID={`notif-${n.notif_id}`} style={[styles.row, !n.read && styles.unread]} onPress={() => open(n)}>
              <View style={styles.icon}><Icon name={KIND[n.kind].icon as any} size={18} color={colors.brandPrimary} /></View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.title}>{n.title}</Text>
                <Text style={styles.body}>{n.body}</Text>
                <Text style={adminStyles.muted}>{fmtDate(n.created_at)}</Text>
              </View>
              {!n.read ? <View style={styles.dot} /> : null}
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  tabs: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface },
  tab: { borderRadius: 999, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, minHeight: 34, justifyContent: "center" },
  tabOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabText: { fontSize: 12, color: colors.onSurface },
  tabTextOn: { color: colors.onBrandPrimary, fontWeight: "600" },
  readAll: { color: colors.brandPrimary, fontSize: 12, fontWeight: "500" },
  readAllRow: { alignSelf: "flex-end", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, minHeight: 36, justifyContent: "center" },
  empty: { textAlign: "center", marginTop: spacing.xl },
  row: { flexDirection: "row", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  unread: { backgroundColor: colors.brandTertiary },
  icon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  body: { fontSize: 13, color: colors.onSurfaceSecondary },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary, marginTop: 6 },
});
