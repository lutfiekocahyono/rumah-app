import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Dimensions } from "react-native";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Category, type FlashSale, type HomeFeed, type HomeSettings, type Product, type Voucher } from "@/src/api";
import { useStore } from "@/src/store-context";
import { ProductCard } from "@/src/components/product-card";
import { FlashSaleSection, FreeShippingBanner, ProductRail, SectionHeader, VoucherStrip } from "@/src/components/home-sections";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (Math.min(screenW, 600) - spacing.lg * 2 - CARD_GAP) / 2;

type Data = { cats: Category[]; flash: FlashSale; vouchers: Voucher[]; settings: HomeSettings | null; feed: HomeFeed | null; recs: Product[] };
const EMPTY: Data = { cats: [], flash: { active: false, items: [] }, vouchers: [], settings: null, feed: null, recs: [] };

/** Beranda sections (Kategori, Gratis Ongkir, Flash Sale, Voucher, Populer, Terbaru, Rekomendasi) for the selected branch:
 * every price, stock and flash price follows that branch. Used on Beranda and on the branch store page. */
export function HomeFeedSections({ refreshKey = 0, onLoaded, shop = false }: { refreshKey?: number; onLoaded?: () => void; shop?: boolean }) {
  const router = useRouter();
  const { storeId, store } = useStore();
  const [data, setData] = useState<Data>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [recMore, setRecMore] = useState(false);
  const [recDone, setRecDone] = useState(false);
  const recSkip = useRef(0); // server-side offset (dedupe on screen may hide some items)
  const recPage = useRef(20); // page size set by the branch admin

  const load = useCallback(async () => {
    const safe = <T,>(p: Promise<T>, fb: T) => p.catch(() => fb);
    const [cats, flash, vouchers, settings, feed] = await Promise.all([
      safe(api.categories(), []), safe(api.flashSale(shop), EMPTY.flash), safe(api.vouchers(), []),
      safe(api.homeSettings(), null), safe(api.homeSections(shop), null),
    ]);
    const recs = feed?.recommended.items ?? [];
    setData({ cats, flash, vouchers, settings, feed, recs });
    recSkip.current = recs.length;
    recPage.current = feed?.recommended.limit ?? 20;
    setRecDone(!feed?.recommended.more || recs.length < recPage.current);
  }, [shop]);

  useEffect(() => {
    setLoading(true);
    load().finally(() => { setLoading(false); onLoaded?.(); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, storeId, refreshKey]);

  const loadMoreRecs = async () => {
    setRecMore(true);
    try {
      const more = await api.moreRecommended(recSkip.current, recPage.current, shop);
      recSkip.current += more.length;
      setData((d) => {
        const have = new Set(d.recs.map((p) => p.product_id));
        return { ...d, recs: [...d.recs, ...more.filter((p) => !have.has(p.product_id))] };
      });
      if (more.length < recPage.current) setRecDone(true);
    } finally {
      setRecMore(false);
    }
  };

  const onFlashEnd = useCallback(() => setData((d) => ({ ...d, flash: { active: false, items: [] } })), []);

  if (loading && !data.feed) return <View style={styles.loadingWrap}><ActivityIndicator color={colors.brandPrimary} /></View>;
  return (
    <View testID="home-feed-sections">
      {/* Kategori */}
      <SectionHeader
        title="Kategori"
        right={<Pressable onPress={() => router.push("/kategori" as any)}><Text style={styles.linkText}>Lihat Semua</Text></Pressable>}
      />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.catsRow}>
        {data.cats.map((c) => (
          <Pressable key={c.category_id} testID={`category-${c.category_id}`} style={styles.catItem}
            onPress={() => router.push(`/category/${c.category_id}` as any)}>
            <View style={styles.catIconWrap}><Icon name={c.icon as any} size={22} color={colors.brandPrimary} /></View>
            <Text style={styles.catName} numberOfLines={2}>{c.name}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {data.settings ? <FreeShippingBanner s={data.settings.free_shipping} city={store?.city} /> : null}

      <FlashSaleSection flash={data.flash} onEnd={onFlashEnd} />

      <VoucherStrip
        vouchers={data.vouchers}
        onChange={(v) => setData((d) => ({ ...d, vouchers: d.vouchers.map((x) => (x.code === v.code ? v : x)) }))}
      />

      {data.feed?.popular.enabled ? <ProductRail title={data.feed.popular.title} icon="flame-outline" items={data.feed.popular.items} testID="popular-section" /> : null}
      {data.feed?.newest.enabled ? <ProductRail title={data.feed.newest.title} icon="sparkles-outline" items={data.feed.newest.items} testID="newest-section" /> : null}

      {/* Rekomendasi */}
      {shop ? (
        <ProductRail
          title={data.feed?.recommended.title ?? "Rekomendasi untukmu"} icon="thumbs-up-outline" items={data.recs} testID="recommend-section"
          onEndReached={() => { if (!recDone && !recMore) loadMoreRecs(); }} loadingMore={recMore}
        />
      ) : data.recs.length ? (
        <View testID="recommend-section">
          <SectionHeader title={data.feed?.recommended.title ?? "Rekomendasi untukmu"} icon="thumbs-up-outline" />
          <View style={styles.grid}>
            {data.recs.map((item) => <ProductCard key={item.product_id} product={item} style={{ width: CARD_WIDTH }} />)}
          </View>
          {!recDone ? (
            <Pressable testID="home-load-more" style={styles.moreBtn} onPress={loadMoreRecs} disabled={recMore}>
              {recMore ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.moreText}>Lihat lebih banyak produk</Text>}
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  loadingWrap: { padding: spacing.xl, alignItems: "center" },
  linkText: { fontSize: fontSize.sm, color: colors.brandPrimary, fontWeight: "500" },
  catsRow: { gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: 4 },
  catItem: { alignItems: "center", gap: 6, width: 68 },
  catIconWrap: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  catName: { fontSize: 11, color: colors.onSurface, textAlign: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: CARD_GAP, paddingHorizontal: spacing.lg },
  moreBtn: { marginHorizontal: spacing.lg, marginTop: spacing.lg, minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  moreText: { color: colors.brandPrimary, fontWeight: "500" },
});
