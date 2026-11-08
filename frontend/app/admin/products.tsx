import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, FlatList, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Product } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

export default function AdminProducts() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [count, setCount] = useState(0);
  useEffect(() => { api.productCount().then((r) => setCount(r.count)).catch(() => {}); }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      api.products({ q: q.trim() || undefined, limit: 50 }).then(setItems).catch(() => {}).finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-products-screen">
      <ScreenHeader title="Harga Manual per Produk" />
      <View style={styles.searchWrap}>
        <View style={styles.search}>
          <Icon name="search" size={18} color={colors.muted} />
          <TextInput testID="admin-product-search" placeholder={count ? `Cari produk dari ${count.toLocaleString("id-ID")} produk` : "Cari produk"} placeholderTextColor={colors.muted}
            value={q} onChangeText={setQ} style={styles.searchInput} />
        </View>
      </View>
      {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={items}
          keyExtractor={(p) => p.product_id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          ListEmptyComponent={<Text style={styles.empty}>Produk tidak ditemukan</Text>}
          renderItem={({ item }) => (
            <Pressable style={styles.row} testID={`admin-product-${item.product_id}`} onPress={() => router.push(`/product-editor/${item.product_id}` as any)}>
              <Image source={item.image} style={styles.img} contentFit="cover" />
              <View style={{ flex: 1 }}>
                <Text style={styles.name} numberOfLines={2}>{item.name}</Text>
                <Text style={styles.price}>Eceran {formatIDR(item.price)}</Text>
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
  searchWrap: { padding: spacing.lg, paddingBottom: 0 },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  searchInput: { flex: 1, color: colors.onSurface, paddingVertical: 12 },
  empty: { textAlign: "center", color: colors.muted, marginTop: spacing.xl },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  img: { width: 56, height: 56, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  price: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
