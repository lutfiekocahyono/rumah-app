import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, FlatList, Dimensions, ActivityIndicator, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";
import { useStore } from "@/src/store-context";
import { Chip, FilterSheet, NO_FILTERS, activeCount, toQuery, type SearchFilters } from "@/src/components/search-filters";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;
const PAGE = 40;
const SORTS = [
  { key: "newest", label: "Terbaru" }, { key: "popular", label: "Terlaris" },
  { key: "price_asc", label: "Harga termurah" }, { key: "price_desc", label: "Harga termahal" },
] as const;

export default function Search() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { store } = useStore();
  const params = useLocalSearchParams<{ q?: string }>();
  const [q, setQ] = useState(params.q ?? "");
  const [sort, setSort] = useState<string>("newest");
  const [filters, setFilters] = useState<SearchFilters>(NO_FILTERS);
  const [sheet, setSheet] = useState(false);
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [more, setMore] = useState(false);
  const [done, setDone] = useState(true);
  const req = useRef(0);

  const nFilters = activeCount(filters);
  const searching = !!q.trim() || nFilters > 0;

  useEffect(() => {
    const t = setTimeout(() => {
      const id = ++req.current;
      if (!searching) { setResults([]); setLoading(false); return; }
      setLoading(true);
      api.products({ ...toQuery(q.trim(), filters), sort, limit: PAGE })
        .then((p) => { if (id === req.current) { setResults(p); setDone(p.length < PAGE); } })
        .catch(() => {}).finally(() => { if (id === req.current) setLoading(false); });
    }, 300);
    return () => clearTimeout(t);
  }, [q, sort, filters, searching]);

  const loadMore = useCallback(async () => {
    if (done || more || loading) return;
    const id = req.current;
    setMore(true);
    try {
      const p = await api.products({ ...toQuery(q.trim(), filters), sort, limit: PAGE, skip: results.length });
      if (id === req.current) { setResults((r) => [...r, ...p.filter((x) => !r.some((y) => y.product_id === x.product_id))]); setDone(p.length < PAGE); }
    } catch { /* keep current list */ } finally { setMore(false); }
  }, [done, more, loading, q, filters, sort, results.length]);

  const removeBrand = (b: string) => setFilters((f) => ({ ...f, brands: f.brands.filter((x) => x !== b) }));

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="search-screen">
      <View style={styles.header}>
        <Pressable testID="search-back" hitSlop={8} onPress={() => router.back()}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <View style={styles.input}>
          <Icon name="search" size={18} color={colors.muted} />
          <TextInput
            testID="search-input"
            placeholder="Cari produk…"
            placeholderTextColor={colors.muted}
            value={q} onChangeText={setQ} autoFocus
            style={{ flex: 1, color: colors.onSurface, paddingVertical: 10 }}
          />
          {q ? <Pressable hitSlop={8} onPress={() => setQ("")}><Icon name="close-circle" size={18} color={colors.muted} /></Pressable> : null}
        </View>
      </View>

      <View style={styles.bar}>
        <Pressable testID="search-filter-btn" style={[styles.filterBtn, nFilters > 0 && styles.filterBtnOn]} onPress={() => setSheet(true)}>
          <Icon name="options-outline" size={16} color={nFilters ? colors.onBrandPrimary : colors.onSurface} />
          <Text style={[styles.filterText, nFilters > 0 && { color: colors.onBrandPrimary }]}>Filter{nFilters ? ` (${nFilters})` : ""}</Text>
        </Pressable>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, paddingRight: spacing.lg }}>
          {SORTS.map((s) => <Chip key={s.key} label={s.label} on={sort === s.key} onPress={() => setSort(s.key)} testID={`search-sort-${s.key}`} />)}
        </ScrollView>
      </View>
      {filters.brands.length ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={styles.activeRow}>
          {filters.brands.map((b) => (
            <Pressable key={b} style={styles.tag} onPress={() => removeBrand(b)} testID={`search-active-brand-${b}`}>
              <Text style={styles.tagText}>{b}</Text><Icon name="close" size={14} color={colors.brandPrimary} />
            </Pressable>
          ))}
        </ScrollView>
      ) : null}

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : !searching ? (
        <View style={styles.empty}>
          <Icon name="search-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Cari furniture, elektronik, dapur, dan lainnya — atau pakai Filter untuk menelusuri per kategori & merek</Text>
        </View>
      ) : results.length === 0 ? (
        <View style={styles.empty}>
          <Icon name="sad-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Produk tidak ditemukan</Text>
          {nFilters ? <Pressable testID="search-clear-filters" onPress={() => setFilters(NO_FILTERS)} hitSlop={8}><Text style={styles.link}>Hapus semua filter</Text></Pressable> : null}
        </View>
      ) : (
        <FlatList
          testID="search-results"
          data={results}
          keyExtractor={(p) => p.product_id}
          numColumns={2}
          columnWrapperStyle={{ gap: CARD_GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: CARD_GAP, paddingVertical: spacing.md }}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_WIDTH }} />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={more ? <ActivityIndicator color={colors.brandPrimary} style={{ margin: spacing.lg }} /> : null}
        />
      )}
      <FilterSheet visible={sheet} q={q.trim()} value={filters} storeName={store?.name ?? "cabang pilihan"} onApply={setFilters} onClose={() => setSheet(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
  },
  input: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.md },
  bar: { flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingLeft: spacing.lg, paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  filterBtn: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  filterBtnOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  filterText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  activeRow: { gap: spacing.xs, paddingHorizontal: spacing.lg, paddingVertical: spacing.xs },
  tag: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 32, paddingHorizontal: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  tagText: { fontSize: 12, color: colors.brandPrimary },
  empty: { alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm, flex: 1 },
  emptyText: { color: colors.muted, fontSize: fontSize.sm, textAlign: "center" },
  link: { color: colors.brandPrimary, fontWeight: "600" },
});
