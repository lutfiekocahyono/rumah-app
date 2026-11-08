import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type ActivityLog } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles } from "@/src/components/admin-form";
import { fmtDate } from "@/src/utils/date";

const ICON: Record<string, string> = {
  auth: "log-in-outline", security: "shield-checkmark-outline", profile: "person-outline", address: "location-outline",
  order: "receipt-outline", settings: "settings-outline", store: "storefront-outline",
};

export default function Activity() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<{ logs: ActivityLog[]; recently_viewed: { product_id: string; name: string; image: string; price: number }[] } | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => { api.activity().then(setData).catch((e) => setErr(e.message)); }, []);

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="activity-screen">
      <ScreenHeader title="Riwayat Aktivitas" />
      {!data ? (err ? <Text style={[adminStyles.err, { padding: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />) : (
        <ScrollView contentContainerStyle={{ paddingVertical: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
          {data.recently_viewed.length ? (
            <>
              <Text style={[styles.h, { paddingHorizontal: spacing.lg }]}>Terakhir dilihat</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.lg }}>
                {data.recently_viewed.map((p) => (
                  <Pressable key={p.product_id} testID={`viewed-${p.product_id}`} style={styles.viewed} onPress={() => router.push(`/product/${p.product_id}` as any)}>
                    <Image source={p.image} style={styles.viewedImg} contentFit="cover" />
                    <Text style={styles.viewedName} numberOfLines={2}>{p.name}</Text>
                    <Text style={styles.viewedPrice}>{formatIDR(p.price)}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            </>
          ) : null}
          <Text style={[styles.h, { paddingHorizontal: spacing.lg }]}>Aktivitas akun</Text>
          <View style={styles.list}>
            {!data.logs.length ? <Text style={[adminStyles.muted, { padding: spacing.md }]}>Belum ada aktivitas.</Text> : data.logs.map((l) => (
              <View key={l.log_id} style={styles.row} testID={`log-${l.log_id}`}>
                <View style={styles.icon}><Icon name={(ICON[l.action] ?? "ellipse-outline") as any} size={18} color={colors.brandPrimary} /></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.detail}>{l.detail}</Text>
                  <Text style={adminStyles.muted}>{fmtDate(l.created_at)}</Text>
                </View>
              </View>
            ))}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  viewed: { width: 120, backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden", borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  viewedImg: { width: 120, height: 120, backgroundColor: colors.surfaceTertiary },
  viewedName: { fontSize: 12, color: colors.onSurface, paddingHorizontal: 6, paddingTop: 4, minHeight: 34 },
  viewedPrice: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", padding: 6 },
  list: { marginHorizontal: spacing.lg, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", gap: spacing.md, padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider, alignItems: "center" },
  icon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  detail: { fontSize: fontSize.sm, color: colors.onSurface },
});
