import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Dimensions, ActivityIndicator, ScrollView, TextInput } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useStore } from "@/src/store-context";
import { api, type Category, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";
import { FilterSheet, NO_FILTERS, activeCount, toQuery, type SearchFilters } from "@/src/components/search-filters";

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
  const { ready, storeId, stores, store } = useStore();
  const shopName = toko ? stores.find((s) => s.store_id === toko)?.name : undefined;
  const [q, setQ] = useState("");
  const [dq, setDq] = useState(""); // debounced in-category search
  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  // sub-categories with products: priced in that branch (store page) or in the shared catalog (Beranda)
  const [subs, setSubs] = useState<Category[]>([]);
  const [sub, setSub] = useState<string | null>(null);
  useEffect(() => {
    setSub(null);
    if (!id || !ready) return;
    (toko ? api.shopCategories(toko, id) : api.categoryCounts(id)).then(setSubs).catch(() => setSubs([]));
  }, [toko, id, ready, storeId]);
  const catId = sub ?? id;
  const [filters, setFilters] = useState<SearchFilters>(NO_FILTERS); // brand / price / stock
  const [sheet, setSheet] = useState(false);
  const nFilters = activeCount(filters);
  const scope = { ...toQuery(dq, filters), ...(toko ? { branch: toko } : {}) };
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
    api.products({ sort, ...scope, category: catId }, !!toko).then((p) => { setProducts(p); setDone(p.length < 40); setLoading(false); }).catch(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, sort, ready, storeId, toko, dq, sub, filters]);

  const loadMore = async () => {
    if (done || moreLoading || loading || !id) return;
    setMoreLoading(true);
    try {
      const p = await api.products({ sort, skip: products.length, ...scope, category: catId }, !!toko);
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
        <View style={{ width: 24 }} />
      </View>

      {(
        <View style={styles.searchBox}>
          <Icon name="search" size={16} color={colors.muted} />
          <TextInput testID="cat-shop-search" value={q} onChangeText={setQ} returnKeyType="search"
            placeholder={`Cari di ${cat?.name ?? "kategori ini"}${shopName ? ` · ${shopName}` : ""}…`} placeholderTextColor={colors.muted} style={styles.searchInput} />
          {q ? <Pressable testID="cat-shop-search-clear" hitSlop={10} onPress={() => setQ("")}><Icon name="close-circle" size={16} color={colors.muted} /></Pressable> : null}
        </View>
      )}

      {subs.length ? (
        <View style={styles.subWrap}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.subRow} testID="cat-subs">
          {[{ category_id: null, name: "Semua" } as { category_id: string | null; name: string; count?: number }, ...subs].map((c) => {
            const on = sub === c.category_id;
            return (
              <Pressable key={c.category_id ?? "all"} testID={`cat-sub-${c.category_id ?? "all"}`} onPress={() => setSub(c.category_id)}
                style={[styles.subChip, on && styles.subChipOn]}>
                <Text style={[styles.chipText, on && styles.subTextOn]}>{c.name}{c.count ? ` (${c.count})` : ""}</Text>
              </Pressable>
            );
          })}
          </ScrollView>
        </View>
      ) : null}

      <View style={styles.chipsWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
          {(
            <Pressable testID="cat-filter-btn" onPress={() => setSheet(true)} style={[styles.chip, styles.filterChip, nFilters > 0 && styles.chipActive]}>
              <Icon name="options-outline" size={16} color={nFilters ? colors.onBrandPrimary : colors.onSurface} />
              <Text style={[styles.chipText, nFilters > 0 && styles.chipTextActive]}>Filter{nFilters ? ` (${nFilters})` : ""}</Text>
            </Pressable>
          )}
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
          <Text style={styles.emptyText}>{dq || nFilters ? "Tidak ada produk yang cocok di kategori ini" : "Belum ada produk"}</Text>
          {nFilters ? <Pressable testID="cat-filter-reset" onPress={() => setFilters(NO_FILTERS)}><Text style={styles.resetText}>Hapus filter</Text></Pressable> : null}
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
      <FilterSheet visible={sheet} q={dq} value={filters} storeName={shopName ?? store?.name ?? "cabang pilihan"} branch={toko} fixedCategory={catId}
        onApply={setFilters} onClose={() => setSheet(false)} />
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
  searchBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginHorizontal: spacing.lg, marginTop: spacing.sm, minHeight: 40, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  searchInput: { flex: 1, minHeight: 40, fontSize: fontSize.sm, color: colors.onSurface },
  subWrap: { height: 52, justifyContent: "center" },
  subRow: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  subChip: { minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, justifyContent: "center" },
  subChipOn: { backgroundColor: colors.brandTertiary },
  subTextOn: { color: colors.brandPrimary, fontWeight: "500" },
  filterChip: { flexDirection: "row", alignItems: "center", gap: 4 },
  resetText: { color: colors.brandPrimary, fontWeight: "500", padding: spacing.sm },
  chipsWrap: { height: 56, justifyContent: "center", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  chipsRow: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center", flexShrink: 0 },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontSize: fontSize.sm },
  chipTextActive: { color: colors.onBrandPrimary, fontWeight: "500" },
  empty: { alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.xl, flex: 1 },
  emptyText: { color: colors.muted, fontSize: fontSize.sm },
});
