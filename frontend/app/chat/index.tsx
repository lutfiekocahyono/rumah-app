import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Conversation } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { fmtDate } from "@/src/utils/date";

/** Inbox. ?side=store shows the store's conversations with buyers. */
export default function ChatList() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { side } = useLocalSearchParams<{ side?: string }>();
  const isStore = side === "store";
  const [list, setList] = useState<Conversation[] | null>(null);
  const [err, setErr] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setErr(""); setList(await api.chats(isStore ? "store" : "buyer")); } catch (e: any) { setErr(e.message); setList([]); }
  }, [isStore]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="chat-list-screen">
      <ScreenHeader title={isStore ? "Chat Pembeli" : "Chat Toko"} />
      {list === null ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={list}
          keyExtractor={(c) => c.conv_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1 }}
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.brandPrimary} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Icon name="chatbubbles-outline" size={48} color={colors.muted} />
              <Text style={styles.muted}>{err || (isStore ? "Belum ada chat dari pembeli." : "Belum ada chat. Buka pesanan Anda lalu ketuk \"Chat Toko\".")}</Text>
            </View>
          }
          renderItem={({ item: c }) => {
            const unread = isStore ? c.unread_store : c.unread_user;
            return (
              <Pressable testID={`chat-row-${c.conv_id}`} style={styles.row} onPress={() => router.push(`/chat/${c.conv_id}` as any)}>
                <View style={styles.avatar}>
                  <Icon name={isStore ? "person-outline" : "storefront-outline"} size={22} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <View style={styles.between}>
                    <Text style={styles.name} numberOfLines={1}>{isStore ? c.user_name : c.store_name}</Text>
                    <Text style={styles.time}>{c.last_text ? fmtDate(c.last_at) : ""}</Text>
                  </View>
                  <View style={styles.between}>
                    <Text style={[styles.muted, unread > 0 && styles.unreadText]} numberOfLines={1}>{c.last_text || "Mulai percakapan"}</Text>
                    {unread > 0 ? <View style={styles.badge}><Text style={styles.badgeText}>{unread}</Text></View> : null}
                  </View>
                </View>
              </Pressable>
            );
          }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, minHeight: 64, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  between: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  name: { flex: 1, fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  time: { fontSize: 11, color: colors.muted },
  muted: { flex: 1, fontSize: fontSize.sm, color: colors.muted, textAlign: "left" },
  unreadText: { color: colors.onSurface, fontWeight: "600" },
  badge: { minWidth: 20, height: 20, borderRadius: 10, paddingHorizontal: 6, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  badgeText: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "700" },
});
