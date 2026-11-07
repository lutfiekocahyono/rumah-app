import React, { useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, TextInput, ActivityIndicator, FlatList, Dimensions } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import { LinearGradient } from "expo-linear-gradient";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Category, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;

const BANNERS = [
  {
    id: "b1",
    title: "Promo Mega Akhir Bulan",
    subtitle: "Diskon hingga 70%",
    image: "https://images.unsplash.com/photo-1724582586529-62622e50c0b3?w=1200",
  },
  {
    id: "b2",
    title: "Furniture & Home Living",
    subtitle: "Harga grosir Sidoarjo",
    image: "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=1200",
  },
  {
    id: "b3",
    title: "Elektronik Rumah",
    subtitle: "Gratis ongkir se-Jatim",
    image: "https://images.unsplash.com/photo-1740803292822-a742c6a4fef0?w=1200",
  },
];

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [cats, setCats] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [bannerIdx, setBannerIdx] = useState(0);
  const bannerRef = useRef<ScrollView>(null);

  useEffect(() => {
    (async () => {
      try {
        const [c, p] = await Promise.all([api.categories(), api.products({ sort: "popular" })]);
        setCats(c);
        setProducts(p);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      const next = (bannerIdx + 1) % BANNERS.length;
      setBannerIdx(next);
      bannerRef.current?.scrollTo({ x: next * (screenW - spacing.lg * 2), animated: true });
    }, 4000);
    return () => clearInterval(t);
  }, [bannerIdx]);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="home-screen">
      {/* Sticky header */}
      <View style={styles.header}>
        <View style={styles.headerBrand}>
          <View style={styles.logoBox}>
            <Icon name="storefront" size={18} color={colors.onBrandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.brandLabel}>Pusat Grosir</Text>
            <Text style={styles.brandCity}>Sidoarjo</Text>
          </View>
          <Pressable
            testID="wishlist-shortcut"
            hitSlop={8}
            onPress={() => router.push("/wishlist" as any)}
            style={styles.iconBtn}
          >
            <Icon name="heart-outline" size={22} color={colors.onSurface} />
          </Pressable>
        </View>
        <Pressable
          testID="search-input-open"
          style={styles.search}
          onPress={() => router.push("/search" as any)}
        >
          <Icon name="search" size={18} color={colors.muted} />
          <Text style={styles.searchPlaceholder}>Cari furniture, elektronik, dapur…</Text>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.loadingWrap}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : (
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: spacing["2xl"] }}
          testID="home-scroll"
        >
          {/* Banner carousel */}
          <View style={styles.bannerWrap}>
            <ScrollView
              ref={bannerRef}
              horizontal
              pagingEnabled
              showsHorizontalScrollIndicator={false}
              onMomentumScrollEnd={(e) => setBannerIdx(Math.round(e.nativeEvent.contentOffset.x / (screenW - spacing.lg * 2)))}
            >
              {BANNERS.map((b) => (
                <View key={b.id} style={styles.banner}>
                  <Image source={b.image} style={StyleSheet.absoluteFill} contentFit="cover" />
                  <LinearGradient
                    colors={["transparent", "rgba(0,0,0,0.65)"]}
                    style={StyleSheet.absoluteFill}
                  />
                  <View style={styles.bannerContent}>
                    <Text style={styles.bannerTitle}>{b.title}</Text>
                    <Text style={styles.bannerSubtitle}>{b.subtitle}</Text>
                    <View style={styles.bannerCta}>
                      <Text style={styles.bannerCtaText}>Belanja Sekarang</Text>
                      <Icon name="arrow-forward" size={14} color={colors.onBrandPrimary} />
                    </View>
                  </View>
                </View>
              ))}
            </ScrollView>
            <View style={styles.dots}>
              {BANNERS.map((_, i) => (
                <View key={i} style={[styles.dot, i === bannerIdx && styles.dotActive]} />
              ))}
            </View>
          </View>

          {/* Categories */}
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Kategori</Text>
            <Pressable onPress={() => router.push("/kategori" as any)}>
              <Text style={styles.linkText}>Lihat Semua</Text>
            </Pressable>
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.catsRow}
          >
            {cats.map((c) => (
              <Pressable
                key={c.category_id}
                testID={`category-${c.category_id}`}
                style={styles.catItem}
                onPress={() => router.push(`/category/${c.category_id}` as any)}
              >
                <View style={styles.catIconWrap}>
                  <Icon name={c.icon as any} size={22} color={colors.brandPrimary} />
                </View>
                <Text style={styles.catName} numberOfLines={1}>{c.name}</Text>
              </Pressable>
            ))}
          </ScrollView>

          {/* Quick promo band */}
          <View style={styles.promoBand}>
            <View style={styles.promoItem}>
              <Icon name="rocket" size={18} color={colors.brandPrimary} />
              <Text style={styles.promoText}>Pengiriman Cepat</Text>
            </View>
            <View style={styles.promoItem}>
              <Icon name="shield-checkmark" size={18} color={colors.brandPrimary} />
              <Text style={styles.promoText}>Garansi Asli</Text>
            </View>
            <View style={styles.promoItem}>
              <Icon name="pricetag" size={18} color={colors.brandPrimary} />
              <Text style={styles.promoText}>Harga Grosir</Text>
            </View>
          </View>

          {/* Products grid */}
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Rekomendasi untukmu</Text>
          </View>
          <FlatList
            data={products}
            keyExtractor={(p) => p.product_id}
            numColumns={2}
            scrollEnabled={false}
            columnWrapperStyle={{ gap: CARD_GAP, paddingHorizontal: spacing.lg }}
            contentContainerStyle={{ gap: CARD_GAP }}
            renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_WIDTH }} />}
          />
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  headerBrand: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm },
  logoBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  brandLabel: { fontSize: 11, color: colors.muted },
  brandCity: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  search: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceTertiary,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    borderRadius: radius.pill, marginTop: 4,
  },
  searchPlaceholder: { color: colors.muted, fontSize: fontSize.sm, flex: 1 },

  loadingWrap: { flex: 1, alignItems: "center", justifyContent: "center" },

  bannerWrap: { paddingTop: spacing.lg, paddingHorizontal: spacing.lg },
  banner: {
    width: screenW - spacing.lg * 2,
    height: 170,
    borderRadius: radius.lg,
    overflow: "hidden",
    justifyContent: "flex-end",
  },
  bannerContent: { padding: spacing.lg, gap: 4 },
  bannerTitle: { color: "#FFFFFF", fontSize: fontSize.xl, fontWeight: "500" },
  bannerSubtitle: { color: "#FFFFFF", fontSize: fontSize.sm, opacity: 0.9 },
  bannerCta: {
    alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, marginTop: 8,
  },
  bannerCtaText: { color: colors.onBrandPrimary, fontSize: fontSize.sm, fontWeight: "500" },
  dots: { flexDirection: "row", justifyContent: "center", gap: 6, marginTop: 8 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.border },
  dotActive: { backgroundColor: colors.brandPrimary, width: 18 },

  sectionHeader: {
    paddingHorizontal: spacing.lg,
    marginTop: spacing.xl, marginBottom: spacing.md,
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
  },
  sectionTitle: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  linkText: { fontSize: fontSize.sm, color: colors.brandPrimary, fontWeight: "500" },

  catsRow: { gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: 4 },
  catItem: { alignItems: "center", gap: 6, width: 68 },
  catIconWrap: {
    width: 56, height: 56, borderRadius: radius.md,
    backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center",
  },
  catName: { fontSize: 11, color: colors.onSurface, textAlign: "center" },

  promoBand: {
    flexDirection: "row",
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: spacing.md,
    justifyContent: "space-around",
  },
  promoItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  promoText: { fontSize: 11, color: colors.onSurface, fontWeight: "500" },
});
