import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, Dimensions, Pressable, Image, Linking, RefreshControl, TextInput, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Product, type ShopPage as Shop } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ProductCard } from "@/src/components/product-card";
import { adminStyles } from "@/src/components/admin-form";

const { width: screenW } = Dimensions.get("window");
const GAP = spacing.md;
const CARD_W = (Math.min(screenW, 600) - spacing.lg * 2 - GAP) / 2;
const wa = (p: string) => { const d = p.replace(/\D/g, ""); return d.startsWith("0") ? `62${d.slice(1)}` : d; };

function InfoRow({ icon, text, testID }: { icon: string; text: string; testID: string }) {
  return (
    <View style={styles.info} testID={testID}>
      <Icon name={icon as any} size={16} color={colors.brandPrimary} />
      <Text style={styles.infoText}>{text}</Text>
    </View>
  );
}

function Header({ s, q, setQ, cat, setCat }: { s: Shop; q: string; setQ: (v: string) => void; cat: string; setCat: (v: string) => void }) {
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
      <Text style={[styles.h, { paddingHorizontal: spacing.lg, marginTop: spacing.md }]}>Produk Toko</Text>
      {s.product_count ? (
        <View style={{ gap: spacing.sm, marginTop: spacing.sm }}>
          <View style={styles.searchBox}>
            <Icon name="search" size={18} color={colors.muted} />
            <TextInput testID="shop-search" value={q} onChangeText={setQ} placeholder={`Cari di ${s.name}…`} placeholderTextColor={colors.muted}
              style={styles.searchInput} returnKeyType="search" />
            {q ? <Pressable testID="shop-search-clear" hitSlop={10} onPress={() => setQ("")}><Icon name="close-circle" size={18} color={colors.muted} /></Pressable> : null}
          </View>
          {s.categories.length > 1 ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, paddingHorizontal: spacing.lg }}>
              {[{ category_id: "", name: "Semua", count: s.product_count ?? 0 }, ...s.categories].map((c) => {
                const on = cat === c.category_id;
                return (
                  <Pressable key={c.category_id || "all"} testID={`shop-cat-${c.category_id || "all"}`} onPress={() => setCat(c.category_id)} style={[styles.chip, on && styles.chipOn]}>
                    <Text style={[styles.chipText, on && { color: colors.onBrandPrimary }]}>{c.name} ({c.count})</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

export default function ShopPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [store, setStore] = useState<Shop | null>(null);
  const [items, setItems] = useState<Product[]>([]);
  const [err, setErr] = useState("");
  const [more, setMore] = useState(false);
  const [done, setDone] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const filtered = !!(q.trim() || cat);

  const load = useCallback(async () => {
    if (!id) return;
    setErr("");
    try {
      const [s, p] = await Promise.all([api.shopPage(id), api.shopProducts(id)]);
      setStore(s); setItems(p); setDone(p.length < 40);
    } catch (e: any) { setErr(e.message); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);

  // search / category inside this store
  const first = React.useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (!id) return;
    let live = true;
    const t = setTimeout(() => api.shopProducts(id, 0, q.trim(), cat).then((p) => { if (live) { setItems(p); setDone(p.length < 40); } }).catch(() => {}), 300);
    return () => { live = false; clearTimeout(t); };
  }, [id, q, cat]);

  const loadMore = async () => {
    if (more || done || !id || !items.length) return;
    setMore(true);
    try {
      const p = await api.shopProducts(id, items.length, q.trim(), cat);
      setItems((c) => { const seen = new Set(c.map((x) => x.product_id)); return [...c, ...p.filter((x) => !seen.has(x.product_id))]; });
      if (p.length < 40) setDone(true);
    } finally { setMore(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="shop-screen">
      <ScreenHeader title={store?.name ?? "Toko"} />
      {err ? <Text style={[adminStyles.err, { padding: spacing.lg }]} testID="shop-error">{err}</Text> : !store ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={items}
          keyExtractor={(p) => p.product_id}
          numColumns={2}
          columnWrapperStyle={{ gap: GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: GAP, paddingBottom: insets.bottom + spacing.xl }}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); setQ(""); setCat(""); await load(); setRefreshing(false); }} />}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={<Header s={store} q={q} setQ={setQ} cat={cat} setCat={setCat} />}
          ListEmptyComponent={filtered ? (
            <View style={styles.empty} testID="shop-no-match">
              <Icon name="search-outline" size={32} color={colors.muted} />
              <Text style={styles.emptyH}>Produk tidak ditemukan di toko ini</Text>
              <Pressable testID="shop-reset" style={styles.btn} onPress={() => { setQ(""); setCat(""); }}><Text style={styles.btnText}>Tampilkan semua produk toko</Text></Pressable>
            </View>
          ) :
            <View style={styles.empty} testID="shop-empty">
              <Icon name="cube-outline" size={36} color={colors.muted} />
              <Text style={styles.emptyH}>{store.official ? "Cabang ini belum punya produk khusus" : "Toko ini belum punya produk"}</Text>
              {store.official ? <Text style={[adminStyles.muted, { textAlign: "center" }]}>Produk katalog PGS tetap bisa dibeli dari cabang ini dengan harga & stok cabang.</Text> : null}
              {store.official ? (
                <Pressable testID="shop-empty-catalog" style={styles.btn} onPress={() => router.push("/(tabs)/katalog" as any)}>
                  <Text style={styles.btnText}>Lihat Katalog</Text>
                </Pressable>
              ) : null}
            </View>
          }
          ListFooterComponent={more ? <ActivityIndicator color={colors.brandPrimary} /> : !done && items.length ? (
            <Pressable onPress={loadMore} style={{ alignItems: "center", padding: spacing.md, minHeight: 44 }}><Text style={{ color: colors.brandPrimary }}>Muat lagi</Text></Pressable>
          ) : null}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_W }} />}
        />
      )}
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
  chip: { minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center", backgroundColor: colors.surface },
  chipOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "600" },
  emptyH: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, textAlign: "center" },
});
