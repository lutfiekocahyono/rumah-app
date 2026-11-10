import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Dimensions, ActivityIndicator, ScrollView, TextInput } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useStore } from "@/src/store-context";
import { api, imgUrl, type Brand, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";
import { FilterSheet, NO_FILTERS, activeCount, toQuery, type SearchFilters } from "@/src/components/search-filters";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;
const SORTS = [
  { id: "popular", label: "Terlaris" },
  { id: "newest", label: "Terbaru" },
  { id: "price_asc", label: "Termurah" },
  { id: "price_desc", label: "Termahal" },
  { id: "rating", label: "Rating" },
];

/** Halaman merek: logo + semua produk merek itu, harga & stok cabang pilihan pembeli, filter & urutan seperti Katalog. */
export default function BrandPage() {
  const { name: raw } = useLocalSearchParams<{ name: string }>();
  const name = raw ?? ""; // expo-router already decodes the segment
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { ready, storeId, store } = useStore();
  const [brand, setBrand] = useState<Brand | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [sort, setSort] = useState("popular");
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const [filters, setFilters] = useState<SearchFilters>(NO_FILTERS);
  const [sheet, setSheet] = useState(false);
  const nFilters = activeCount(filters);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [moreLoading, setMoreLoading] = useState(false);
  const real = brand?.name ?? name; // listed spelling ("q2 & gsf" -> "Q2 & GSF")
  // branch = buyer's branch: its own price AND stock (like the store page)
  const query = () => ({ ...toQuery(dq, filters), brands: [real], sort, ...(storeId ? { branch: storeId } : {}) });

  useEffect(() => { api.brands().then((bs) => setBrand(bs.find((b) => b.name.toLowerCase() === name.toLowerCase()) ?? null)).catch(() => {}); }, [name]);
  useEffect(() => {
    if (!name || !ready) return; // prices follow the buyer's saved branch
    setLoading(true); setDone(false);
    api.products(query()).then((p) => { setProducts(p); setDone(p.length < 40); }).catch(() => setProducts([])).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [real, sort, ready, storeId, dq, filters]);

  const loadMore = async () => {
    if (done || moreLoading || loading) return;
    setMoreLoading(true);
    try {
      const p = await api.products({ ...query(), skip: products.length });
      setProducts((cur) => { const have = new Set(cur.map((x) => x.product_id)); return [...cur, ...p.filter((x) => !have.has(x.product_id))]; });
      if (p.length < 40) setDone(true);
    } finally { setMoreLoading(false); }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="brand-screen">
      <View style={styles.header}>
        <Pressable testID="brand-back" hitSlop={12} style={{ minWidth: 44, minHeight: 44, justifyContent: "center" }} onPress={() => router.back()}><Icon name="chevron-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headTitle} numberOfLines={1}>Merek</Text>
        <View style={{ width: 44 }} />
      </View>
      <View style={styles.hero} testID="brand-hero">
        {brand?.logo ? <Image testID="brand-logo" source={{ uri: imgUrl(brand.logo) }} style={styles.logo} contentFit="contain" />
          : <View style={[styles.logo, styles.noLogo]}><Text style={styles.initial}>{name.slice(0, 1).toUpperCase()}</Text></View>}
        <View style={{ flex: 1 }}>
          <Text style={styles.title} testID="brand-name">{brand?.name ?? name}</Text>
          <Text style={styles.sub}>{[brand ? `${brand.count.toLocaleString("id-ID")} produk` : "", store?.name ? `harga & stok ${store.name}` : ""].filter(Boolean).join(" · ")}</Text>
        </View>
      </View>
      <View style={styles.searchBox}>
        <Icon name="search" size={16} color={colors.muted} />
        <TextInput testID="brand-search" value={q} onChangeText={setQ} returnKeyType="search" placeholder={`Cari di ${brand?.name ?? name}…`} placeholderTextColor={colors.muted} style={styles.searchInput} />
        {q ? <Pressable testID="brand-search-clear" hitSlop={10} onPress={() => setQ("")}><Icon name="close-circle" size={16} color={colors.muted} /></Pressable> : null}
      </View>
      <View style={styles.chipsWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
          <Pressable testID="brand-filter-btn" onPress={() => setSheet(true)} style={[styles.chip, styles.filterChip, nFilters > 0 && styles.chipActive]}>
            <Icon name="options-outline" size={16} color={nFilters ? colors.onBrandPrimary : colors.onSurface} />
            <Text style={[styles.chipText, nFilters > 0 && styles.chipTextActive]}>Filter{nFilters ? ` (${nFilters})` : ""}</Text>
          </Pressable>
          {SORTS.map((s) => (
            <Pressable key={s.id} testID={`brand-sort-${s.id}`} style={[styles.chip, s.id === sort && styles.chipActive]} onPress={() => setSort(s.id)}>
              <Text style={[styles.chipText, s.id === sort && styles.chipTextActive]}>{s.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
      {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : products.length === 0 ? (
        <View style={styles.empty}>
          <Icon name="cube-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>{dq || nFilters ? "Tidak ada produk yang cocok" : "Belum ada produk merek ini"}</Text>
          {nFilters || dq ? <Pressable testID="brand-filter-reset" onPress={() => { setFilters(NO_FILTERS); setQ(""); }}><Text style={styles.resetText}>Hapus pencarian & filter</Text></Pressable> : null}
        </View>
      ) : (
        <FlatList data={products} keyExtractor={(p) => p.product_id} numColumns={2}
          columnWrapperStyle={{ gap: CARD_GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: CARD_GAP, paddingVertical: spacing.md, paddingBottom: spacing.xl }}
          onEndReached={loadMore} onEndReachedThreshold={0.5}
          ListFooterComponent={moreLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} /> : null}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_WIDTH }} />} />
      )}
      <FilterSheet visible={sheet} q={dq} value={filters} storeName={store?.name ?? "cabang pilihan"} fixedBrand={real} branch={storeId || undefined}
        onApply={setFilters} onClose={() => setSheet(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  headTitle: { flex: 1, textAlign: "center", fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  hero: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginHorizontal: spacing.lg, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  logo: { width: 64, height: 64, borderRadius: radius.md, backgroundColor: colors.surface },
  noLogo: { backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  initial: { fontSize: 28, fontWeight: "700", color: colors.brandPrimary },
  title: { fontSize: fontSize.xl, fontWeight: "600", color: colors.onSurface },
  sub: { fontSize: fontSize.sm, color: colors.muted, marginTop: 2 },
  searchBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginHorizontal: spacing.lg, marginTop: spacing.sm, minHeight: 40, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  searchInput: { flex: 1, minHeight: 40, fontSize: fontSize.sm, color: colors.onSurface },
  chipsWrap: { height: 56, justifyContent: "center", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  chipsRow: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center", flexShrink: 0 },
  filterChip: { flexDirection: "row", alignItems: "center", gap: 4 },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurface, fontSize: fontSize.sm },
  chipTextActive: { color: colors.onBrandPrimary, fontWeight: "500" },
  empty: { alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.xl, flex: 1 },
  emptyText: { color: colors.muted, fontSize: fontSize.sm },
  resetText: { color: colors.brandPrimary, fontWeight: "500", padding: spacing.sm },
});
