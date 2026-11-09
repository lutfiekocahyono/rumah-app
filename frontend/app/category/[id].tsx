import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Dimensions, ActivityIndicator, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useStore } from "@/src/store-context";
import { api, type Category, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;

const SORTS = [
  { id: "popular", label: "Terlaris" },
  { id: "price_asc", label: "Termurah" },
  { id: "price_desc", label: "Termahal" },
  { id: "rating", label: "Rating" },
];

export default function CategoryPage() {
  // ?toko=<cabang>: opened from a branch store page, only products priced in that branch
  const { id, toko } = useLocalSearchParams<{ id: string; toko?: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [cat, setCat] = useState<Category | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [sort, setSort] = useState("popular");
  const { ready, storeId, stores } = useStore();
  const shopName = toko ? stores.find((s) => s.store_id === toko)?.name : undefined;
  const scope = toko ? { branch: toko } : {};
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [moreLoading, setMoreLoading] = useState(false);

  useEffect(() => {
    api.categories().then((cs) => setCat(cs.find((c) => c.category_id === id) ?? null));
  }, [id]);

  useEffect(() => {
    if (!id || !ready) return; // wait for the saved branch: prices follow it
    setLoading(true);
    setDone(false);
    api.products({ category: id, sort, ...scope }, !!toko).then((p) => { setProducts(p); setDone(p.length < 40); setLoading(false); }).catch(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, sort, ready, storeId, toko]);

  const loadMore = async () => {
    if (done || moreLoading || loading || !id) return;
    setMoreLoading(true);
    try {
      const p = await api.products({ category: id, sort, skip: products.length, ...scope }, !!toko);
      setProducts((cur) => { const have = new Set(cur.map((x) => x.product_id)); return [...cur, ...p.filter((x) => !have.has(x.product_id))]; });
      if (p.length < 40) setDone(true);
    } finally {
      setMoreLoading(false);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="category-screen">
      <View style={styles.header}>
        <Pressable testID="cat-back" hitSlop={8} onPress={() => router.back()}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <View style={styles.titleWrap}>
          <Text style={styles.title}>{cat?.name ?? "Kategori"}</Text>
          {shopName ? <Text testID="cat-shop-name" style={styles.sub}>di {shopName}</Text> : null}
        </View>
        <Pressable testID="cat-search" hitSlop={8} onPress={() => router.push("/search?focus=1" as any)}>
          <Icon name="search" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      <View style={styles.chipsWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
          {SORTS.map((s) => {
            const active = s.id === sort;
            return (
              <Pressable
                key={s.id}
                testID={`sort-${s.id}`}
                style={[styles.chip, active && styles.chipActive]}
                onPress={() => setSort(s.id)}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{s.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : products.length === 0 ? (
        <View style={styles.empty}>
          <Icon name="cube-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Belum ada produk</Text>
        </View>
      ) : (
        <FlatList
          data={products}
          keyExtractor={(p) => p.product_id}
          numColumns={2}
          columnWrapperStyle={{ gap: CARD_GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: CARD_GAP, paddingVertical: spacing.md, paddingBottom: spacing.xl }}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={moreLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} /> : null}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_WIDTH }} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  titleWrap: { flex: 1, alignItems: "center" },
  sub: { fontSize: fontSize.sm, color: colors.muted },
  chipsWrap: { height: 56, justifyContent: "center", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  chipsRow: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center", flexShrink: 0 },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontSize: fontSize.sm },
  chipTextActive: { color: colors.onBrandPrimary, fontWeight: "500" },
  empty: { alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.xl, flex: 1 },
  emptyText: { color: colors.muted, fontSize: fontSize.sm },
});
