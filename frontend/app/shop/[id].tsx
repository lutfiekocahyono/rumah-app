import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, Dimensions, Pressable, Image, Linking, RefreshControl, TextInput, ScrollView, Platform, Share } from "react-native";
import * as Clipboard from "expo-clipboard";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Product, type ShopPage as Shop } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ProductCard } from "@/src/components/product-card";
import { adminStyles } from "@/src/components/admin-form";
import { FilterSheet, NO_FILTERS, activeCount, toQuery, type SearchFilters } from "@/src/components/search-filters";
import { useStore } from "@/src/store-context";
import { HomeFeedSections } from "@/src/components/home-feed";

const SORTS = [
  { key: "popular", label: "Terlaris" }, { key: "newest", label: "Terbaru" },
  { key: "price_asc", label: "Harga termurah" }, { key: "price_desc", label: "Harga termahal" },
] as const;

const { width: screenW } = Dimensions.get("window");
const GAP = spacing.md;
const CARD_W = (Math.min(screenW, 600) - spacing.lg * 2 - GAP) / 2;
/** Route to the store in the phone's maps app (Apple Maps on iPhone, Google Maps elsewhere). */
const openDirections = (lat: number, lng: number, name: string) => {
  const google = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
  const url = Platform.OS === "ios" ? `http://maps.apple.com/?daddr=${lat},${lng}&q=${encodeURIComponent(name)}&dirflg=d` : google;
  Linking.openURL(url).catch(() => Linking.openURL(google));
};
const wa = (p: string) => { const d = p.replace(/\D/g, ""); return d.startsWith("0") ? `62${d.slice(1)}` : d; };

function InfoRow({ icon, text, testID }: { icon: string; text: string; testID: string }) {
  return (
    <View style={styles.info} testID={testID}>
      <Icon name={icon as any} size={16} color={colors.brandPrimary} />
      <Text style={styles.infoText}>{text}</Text>
    </View>
  );
}

function Header({ s, q, setQ, sort, setSort, nFilters, openFilter, homeReady, refreshKey }: {
  s: Shop; q: string; setQ: (v: string) => void; sort: string; setSort: (v: string) => void; nFilters: number; openFilter: () => void; homeReady: boolean; refreshKey: number;
}) {
  return (
    <View style={{ marginBottom: spacing.sm }}>
      <View style={styles.bannerWrap} testID="shop-banner">
        {s.banner ? <Image source={{ uri: imgUrl(s.banner) }} style={styles.banner} resizeMode="cover" />
          : <View style={[styles.banner, styles.bannerEmpty]}><Icon name="storefront-outline" size={40} color={colors.onBrandPrimary} /></View>}
      </View>
      <View style={styles.card}>
        <View style={styles.logoRow}>
          <View style={styles.logo} testID="shop-logo">
            {s.logo ? <Image source={{ uri: imgUrl(s.logo) }} style={styles.logoImg} />
              : <Icon name={s.official ? "shield-checkmark" : "storefront"} size={30} color={colors.brandPrimary} />}
          </View>
          <View style={{ flex: 1, paddingTop: 30, gap: 2 }}>
            <Text style={styles.name} testID="shop-name">{s.name}</Text>
            <Text style={adminStyles.muted}>{s.city} · {s.product_count ?? 0} produk toko</Text>
          </View>
        </View>
        {s.description ? <Text style={styles.desc} testID="shop-desc">{s.description}</Text> : null}
        {s.address ? <InfoRow icon="location-outline" text={s.address} testID="shop-address" /> : null}
        {s.lat != null && s.lng != null ? (
          <Pressable testID="shop-directions" style={[styles.btn, { alignSelf: "flex-start" }]} onPress={() => openDirections(s.lat!, s.lng!, s.name)}>
            <Icon name="navigate" size={16} color={colors.brandPrimary} /><Text style={styles.btnText}>Petunjuk arah ke toko</Text>
          </Pressable>
        ) : null}
        {s.pickup_hours ? <InfoRow icon="time-outline" text={`Jam ambil: ${s.pickup_hours}`} testID="shop-hours" /> : null}
        {s.phone ? (
          <>
            <InfoRow icon="call-outline" text={s.phone} testID="shop-phone" />
            <View style={styles.btnRow}>
              <Pressable testID="shop-call" style={styles.btn} onPress={() => Linking.openURL(`tel:${s.phone}`)}>
                <Icon name="call" size={16} color={colors.brandPrimary} /><Text style={styles.btnText}>Telepon</Text>
              </Pressable>
              <Pressable testID="shop-wa" style={styles.btn} onPress={() => Linking.openURL(`https://wa.me/${wa(s.phone!)}`)}>
                <Icon name="logo-whatsapp" size={16} color={colors.brandPrimary} /><Text style={styles.btnText}>WhatsApp</Text>
              </Pressable>
            </View>
          </>
        ) : null}
      </View>
      {s.featured.length ? (
        <View style={styles.section} testID="shop-featured">
          <Text style={styles.h}>{s.featured_manual ? "Produk Andalan" : "Produk Andalan · Terlaris"}</Text>
          <FlatList horizontal data={s.featured} keyExtractor={(p) => p.product_id} showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: GAP, paddingHorizontal: spacing.lg }}
            renderItem={({ item }) => <ProductCard product={item} style={{ width: 150 }} />} />
        </View>
      ) : null}
      {/* same sections as Beranda, priced for this branch (the buyer's branch is switched to it on open) */}
      {s.official && homeReady ? <HomeFeedSections refreshKey={refreshKey} shop /> : null}
      <Text style={[styles.h, { paddingHorizontal: spacing.lg, marginTop: spacing.lg }]} testID="shop-all-title">Semua Produk Toko</Text>
      <View style={{ gap: spacing.sm, marginTop: spacing.sm }}>
        <View style={styles.searchBox}>
          <Icon name="search" size={18} color={colors.muted} />
          <TextInput testID="shop-search" value={q} onChangeText={setQ} placeholder={`Cari di ${s.name}…`} placeholderTextColor={colors.muted}
            style={styles.searchInput} returnKeyType="search" />
          {q ? <Pressable testID="shop-search-clear" hitSlop={10} onPress={() => setQ("")}><Icon name="close-circle" size={18} color={colors.muted} /></Pressable> : null}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, paddingHorizontal: spacing.lg }}>
          <Pressable testID="shop-filter-btn" onPress={openFilter} style={[styles.chip, styles.filterChip, nFilters > 0 && styles.chipOn]}>
            <Icon name="options-outline" size={16} color={nFilters ? colors.onBrandPrimary : colors.onSurface} />
            <Text style={[styles.chipText, nFilters > 0 && { color: colors.onBrandPrimary }]}>Filter{nFilters ? ` (${nFilters})` : ""}</Text>
          </Pressable>
          {SORTS.map((o) => (
            <Pressable key={o.key} testID={`shop-sort-${o.key}`} onPress={() => setSort(o.key)} style={[styles.chip, sort === o.key && styles.chipOn]}>
              <Text style={[styles.chipText, sort === o.key && { color: colors.onBrandPrimary }]}>{o.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
    </View>
  );
}

export default function ShopPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [store, setStore] = useState<Shop | null>(null);
  const [items, setItems] = useState<Product[]>([]);
  const [err, setErr] = useState("");
  const [more, setMore] = useState(false);
  const [done, setDone] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("popular");
  const [filters, setFilters] = useState<SearchFilters>(NO_FILTERS);
  const [sheet, setSheet] = useState(false);
  const nFilters = activeCount(filters);
  const filtered = !!(q.trim() || nFilters);
  // official branch: the whole catalog of that branch (shared + its own) with its prices & stock; other stores: their own products
  const fetchPage = useCallback((skip: number) => {
    if (!id || !store) return Promise.resolve([] as Product[]);
    return api.products({ ...toQuery(q.trim(), filters), sort, skip, limit: 40, ...(store.official ? { branch: id } : { store: id }) }, store.official);
  }, [id, store, q, filters, sort]);

  const load = useCallback(async () => {
    if (!id) return;
    setErr("");
    try { setStore(await api.shopPage(id)); } catch (e: any) { setErr(e.message); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!store) return;
    let live = true;
    const t = setTimeout(() => fetchPage(0).then((p) => { if (live) { setItems(p); setDone(p.length < 40); } }).catch(() => {}), 300);
    return () => { live = false; clearTimeout(t); };
  }, [store, fetchPage]);

  // a branch store page shows that branch: the buyer continues shopping (detail, cart) there
  const { ready, storeId, stores, choose } = useStore();
  useEffect(() => {
    if (ready && id && id !== storeId && stores.some((s) => s.store_id === id)) void choose(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, id, stores.length]);

  const [toast, setToast] = useState("");
  const showToast = (t: string) => { setToast(t); setTimeout(() => setToast(""), 2500); };
  const share = async () => {
    if (!store || !id) return;
    const base = Platform.OS === "web" ? window.location.origin : process.env.EXPO_PUBLIC_BACKEND_URL;
    const url = `${base}/shop/${encodeURIComponent(id)}${store.official ? `?toko=${encodeURIComponent(id)}` : ""}`;
    const text = `Belanja di ${store.name}${store.city ? ` (${store.city})` : ""} - Pusat Grosir Sidoarjo`;
    try {
      if (Platform.OS !== "web") { await Share.share({ message: `${text}\n${url}`, url, title: store.name }); return; }
      const nav: any = typeof navigator !== "undefined" ? navigator : null;
      const touch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
      if (touch && nav?.share) { await nav.share({ title: store.name, text, url }); return; }
      await Clipboard.setStringAsync(url);
      showToast("Tautan toko disalin");
    } catch (e: any) {
      if (e?.name !== "AbortError") showToast("Gagal membagikan, coba lagi");
    }
  };

  const loadMore = async () => {
    if (more || done || !id || !items.length) return;
    setMore(true);
    try {
      const p = await fetchPage(items.length);
      setItems((c) => { const seen = new Set(c.map((x) => x.product_id)); return [...c, ...p.filter((x) => !seen.has(x.product_id))]; });
      if (p.length < 40) setDone(true);
    } finally { setMore(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="shop-screen">
      <ScreenHeader title={store?.name ?? "Toko"} right={store ? (
        <Pressable testID="shop-share-btn" hitSlop={8} onPress={share} accessibilityLabel="Bagikan toko" style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}>
          <Icon name="share-social-outline" size={22} color={colors.onSurface} />
        </Pressable>
      ) : null} />
      {toast ? <View style={styles.toast} testID="shop-toast"><Text style={styles.toastText}>{toast}</Text></View> : null}
      {err ? <Text style={[adminStyles.err, { padding: spacing.lg }]} testID="shop-error">{err}</Text> : !store ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={items}
          keyExtractor={(p) => p.product_id}
          numColumns={2}
          columnWrapperStyle={{ gap: GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: GAP, paddingBottom: insets.bottom + spacing.xl }}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); setQ(""); setFilters(NO_FILTERS); setSort("popular"); setRefreshKey((k) => k + 1); await load(); setRefreshing(false); }} />}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={<Header s={store} q={q} setQ={setQ} sort={sort} setSort={setSort} nFilters={nFilters} openFilter={() => setSheet(true)} homeReady={storeId === id} refreshKey={refreshKey} />}
          ListEmptyComponent={filtered ? (
            <View style={styles.empty} testID="shop-no-match">
              <Icon name="search-outline" size={32} color={colors.muted} />
              <Text style={styles.emptyH}>Produk tidak ditemukan di toko ini</Text>
              <Pressable testID="shop-reset" style={styles.btn} onPress={() => { setQ(""); setFilters(NO_FILTERS); }}><Text style={styles.btnText}>Tampilkan semua produk toko</Text></Pressable>
            </View>
          ) :
            <View style={styles.empty} testID="shop-empty">
              <Icon name="cube-outline" size={36} color={colors.muted} />
              <Text style={styles.emptyH}>Toko ini belum punya produk</Text>
            </View>
          }
          ListFooterComponent={more ? <ActivityIndicator color={colors.brandPrimary} /> : !done && items.length ? (
            <Pressable onPress={loadMore} style={{ alignItems: "center", padding: spacing.md, minHeight: 44 }}><Text style={{ color: colors.brandPrimary }}>Muat lagi</Text></Pressable>
          ) : null}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_W }} />}
        />
      )}
      <FilterSheet visible={sheet} q={q.trim()} value={filters} storeName={store?.name ?? "toko ini"} branch={store?.official ? id : undefined}
        onApply={setFilters} onClose={() => setSheet(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  bannerWrap: { width: "100%", aspectRatio: 2.5, maxHeight: 260 },
  banner: { width: "100%", height: "100%" },
  bannerEmpty: { backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  card: { backgroundColor: colors.surface, paddingHorizontal: spacing.lg, paddingBottom: spacing.lg, gap: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  logoRow: { flexDirection: "row", gap: spacing.md, marginTop: -32 },
  logo: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.surface, borderWidth: 3, borderColor: colors.surface, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  logoImg: { width: "100%", height: "100%" },
  name: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  desc: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, lineHeight: 20 },
  info: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  infoText: { flex: 1, fontSize: fontSize.sm, color: colors.onSurface },
  btnRow: { flexDirection: "row", gap: spacing.sm },
  btn: { flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  btnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  section: { backgroundColor: colors.surface, paddingVertical: spacing.md, gap: spacing.sm, marginTop: spacing.sm },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface, paddingHorizontal: spacing.lg },
  empty: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  searchBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginHorizontal: spacing.lg, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  searchInput: { flex: 1, color: colors.onSurface, paddingVertical: 10, fontSize: fontSize.sm },
  chip: { minHeight: 44, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center", backgroundColor: colors.surface },
  filterChip: { flexDirection: "row", alignItems: "center", gap: 4 },
  toast: { position: "absolute", bottom: 96, alignSelf: "center", zIndex: 10, backgroundColor: colors.onSurface, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  toastText: { color: colors.surface, fontSize: fontSize.sm, fontWeight: "600" },
  chipOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "600" },
  emptyH: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, textAlign: "center" },
});
