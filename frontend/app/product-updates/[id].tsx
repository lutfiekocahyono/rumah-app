import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Image, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type ProductUpdates } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { fmtDate } from "@/src/utils/date";

/** Daftar produk dari satu ringkasan notifikasi "Update produk". */
export default function ProductUpdatesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [d, setD] = useState<ProductUpdates | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => { if (id) api.productUpdates(id).then(setD).catch((e) => setErr(e.message)); }, [id]);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="product-updates-screen">
      <ScreenHeader title="Update Produk" />
      {err ? <Text style={styles.err}>{err}</Text> : !d ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={d.items}
          keyExtractor={(i) => i.product_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}
          ListHeaderComponent={<View style={{ marginBottom: spacing.sm }}><Text style={styles.h}>{d.title}</Text><Text style={styles.sub}>{fmtDate(d.created_at)}</Text></View>}
          renderItem={({ item }) => (
            <Pressable style={styles.row} onPress={() => router.push(`/product/${item.product_id}` as any)} testID={`pu-item-${item.product_id}`}>
              {item.image ? <Image source={{ uri: item.image }} style={styles.img} /> : <View style={[styles.img, { backgroundColor: colors.surfaceTertiary }]} />}
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.name} numberOfLines={2}>{item.name}</Text>
                <Text style={styles.change} numberOfLines={2}>{item.change}</Text>
              </View>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  sub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surface, minHeight: 72 },
  img: { width: 56, height: 56, borderRadius: radius.sm },
  name: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  change: { fontSize: 13, color: colors.brandPrimary },
  err: { color: colors.error, textAlign: "center", marginTop: spacing.xl },
});
