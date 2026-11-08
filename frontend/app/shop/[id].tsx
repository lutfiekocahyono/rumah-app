import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, Dimensions, Pressable } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Product, type Store } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ProductCard } from "@/src/components/product-card";
import { adminStyles } from "@/src/components/admin-form";

const { width: screenW } = Dimensions.get("window");
const GAP = spacing.md;
const CARD_W = (screenW - spacing.lg * 2 - GAP) / 2;

export default function ShopPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [store, setStore] = useState<Store | null>(null);
  const [items, setItems] = useState<Product[]>([]);
  const [err, setErr] = useState("");
  const [more, setMore] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.storePage(id).then(setStore).catch((e) => setErr(e.message));
    api.products({ store: id, sort: "popular" }).then((p) => { setItems(p); setDone(p.length < 40); }).catch(() => {});
  }, [id]);

  const loadMore = async () => {
    if (more || done || !id || !items.length) return;
    setMore(true);
    try {
      const p = await api.products({ store: id, sort: "popular", skip: items.length });
      setItems((c) => { const seen = new Set(c.map((x) => x.product_id)); return [...c, ...p.filter((x) => !seen.has(x.product_id))]; });
      if (p.length < 40) setDone(true);
    } finally { setMore(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="shop-screen">
      <ScreenHeader title={store?.name ?? "Toko"} />
      {err ? <Text style={[adminStyles.err, { padding: spacing.lg }]}>{err}</Text> : !store ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={items}
          keyExtractor={(p) => p.product_id}
          numColumns={2}
          columnWrapperStyle={{ gap: GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: GAP, paddingBottom: insets.bottom + spacing.xl }}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListHeaderComponent={
            <View style={styles.head}>
              <View style={styles.logo}><Icon name={store.store_id === "pgs-official" ? "shield-checkmark" : "storefront"} size={28} color={colors.onBrandPrimary} /></View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.name}>{store.name}</Text>
                <Text style={adminStyles.muted}>{store.city} · {store.product_count ?? 0} produk</Text>
                {store.description ? <Text style={styles.desc} numberOfLines={3}>{store.description}</Text> : null}
              </View>
            </View>
          }
          ListEmptyComponent={<Text style={[adminStyles.muted, { textAlign: "center" }]}>Toko ini belum punya produk.</Text>}
          ListFooterComponent={more ? <ActivityIndicator color={colors.brandPrimary} /> : !done && items.length ? (
            <Pressable onPress={loadMore} style={{ alignItems: "center", padding: spacing.md }}><Text style={{ color: colors.brandPrimary }}>Muat lagi</Text></Pressable>
          ) : null}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_W }} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: "row", gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surface, marginBottom: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  logo: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  name: { fontSize: fontSize.lg, fontWeight: "600", color: colors.onSurface },
  desc: { fontSize: 13, color: colors.onSurfaceSecondary },
});
