import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, FlatList, Dimensions, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";
import { useAuth } from "@/src/auth-context";
import { useStore } from "@/src/store-context";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import { LinearGradient } from "expo-linear-gradient";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Banner } from "@/src/api";
import { HomeFeedSections } from "@/src/components/home-feed";

const { width: screenW } = Dimensions.get("window");

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [banners, setBanners] = useState<Banner[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [bannerIdx, setBannerIdx] = useState(0);
  const [bannerW, setBannerW] = useState(screenW - spacing.lg * 2);
  const { user } = useAuth();
  const { storeId, store } = useStore();
  const [unread, setUnread] = useState(0);
  useFocusEffect(useCallback(() => {
    if (!user) { setUnread(0); return; }
    api.unreadCount().then((r) => setUnread(r.count)).catch(() => {});
  }, [user]));
  const bannerRef = useRef<ScrollView>(null);
  const [productCount, setProductCount] = useState(0);

  // banners & search count; the sections below load themselves for the selected branch
  const load = useCallback(async () => {
    api.productCount().then((r) => setProductCount(r.count)).catch(() => {});
    setBanners(await api.banners().catch(() => []));
  }, []);

  useEffect(() => { setLoading(true); load().finally(() => setLoading(false)); }, [load, storeId]);
  useEffect(() => {
    if (banners.length < 2) return;
    const t = setInterval(() => {
      const next = (bannerIdx + 1) % banners.length;
      setBannerIdx(next);
      bannerRef.current?.scrollTo({ x: next * bannerW, animated: true });
    }, 4000);
    return () => clearInterval(t);
  }, [bannerIdx, bannerW, banners.length]);

  const openBanner = (b: Banner) => {
    if (!b.link_value) return;
    if (b.link_type === "category") router.push(`/category/${b.link_value}` as any);
    else if (b.link_type === "product") router.push(`/product/${b.link_value}` as any);
    else if (b.link_type === "search") router.push({ pathname: "/search", params: { q: b.link_value } } as any);
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="home-screen">
      <View style={styles.header}>
        <View style={styles.headerBrand}>
          <Image source={require("../../assets/images/pgs-logo-small.png")} style={styles.logoImg} contentFit="contain" testID="home-logo" />
          <Pressable style={{ flex: 1, minHeight: 44, justifyContent: "center" }} testID="store-switch" onPress={() => router.push("/pilih-toko?from=home" as any)}>
            <Text style={styles.brandLabel}>Produk semua cabang · toko pilihan</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <Text style={styles.brandCity} numberOfLines={1}>{store?.name ?? "PGS Sidoarjo"}</Text>
              <Icon name="chevron-down" size={16} color={colors.brandPrimary} />
            </View>
          </Pressable>
          <Pressable testID="notif-bell" hitSlop={8} onPress={() => router.push("/notifications" as any)} style={styles.iconBtn}>
            <Icon name="notifications-outline" size={22} color={colors.onSurface} />
            {unread > 0 ? <View style={styles.badge}><Text style={styles.badgeText}>{unread > 99 ? "99+" : unread}</Text></View> : null}
          </Pressable>
          <Pressable testID="wishlist-shortcut" hitSlop={8} onPress={() => router.push("/wishlist" as any)} style={styles.iconBtn}>
            <Icon name="heart-outline" size={22} color={colors.onSurface} />
          </Pressable>
        </View>
        <Pressable testID="search-input-open" style={styles.search} onPress={() => router.push("/search?focus=1" as any)}>
          <Icon name="search" size={18} color={colors.muted} />
          <Text style={styles.searchPlaceholder} testID="home-search-placeholder">
            {productCount ? `Cari dari ${productCount.toLocaleString("id-ID")} produk…` : "Cari produk…"}
          </Text>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.loadingWrap}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : (
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: spacing["2xl"] }}
          testID="home-scroll"
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.brandPrimary}
            onRefresh={async () => { setRefreshing(true); setRefreshKey((k) => k + 1); await load(); setRefreshing(false); }} />}
        >
          {/* Banner promosi */}
          {banners.length ? (
            <View style={styles.bannerWrap} testID="banner-section">
              <ScrollView
                ref={bannerRef}
                horizontal
                pagingEnabled
                onLayout={(e) => setBannerW(e.nativeEvent.layout.width)}
                showsHorizontalScrollIndicator={false}
                onMomentumScrollEnd={(e) => setBannerIdx(Math.round(e.nativeEvent.contentOffset.x / bannerW))}
              >
                {banners.map((b) => (
                  <Pressable key={b.banner_id} testID={`banner-${b.banner_id}`} onPress={() => openBanner(b)} style={[styles.banner, { width: bannerW }]}>
                    <Image source={imgUrl(b.image)} style={StyleSheet.absoluteFill} contentFit="cover" />
                    <LinearGradient colors={["transparent", "rgba(0,0,0,0.65)"]} style={StyleSheet.absoluteFill} />
                    <View style={styles.bannerContent}>
                      <Text style={styles.bannerTitle}>{b.title}</Text>
                      {b.subtitle ? <Text style={styles.bannerSubtitle}>{b.subtitle}</Text> : null}
                      {b.link_type !== "none" && b.link_value ? (
                        <View style={styles.bannerCta}>
                          <Text style={styles.bannerCtaText}>Belanja Sekarang</Text>
                          <Icon name="arrow-forward" size={14} color={colors.onBrandPrimary} />
                        </View>
                      ) : null}
                    </View>
                  </Pressable>
                ))}
              </ScrollView>
              <View style={styles.dots}>
                {banners.map((_, i) => <View key={i} style={[styles.dot, i === bannerIdx && styles.dotActive]} />)}
              </View>
            </View>
          ) : null}

          <HomeFeedSections refreshKey={refreshKey} />
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  headerBrand: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm },
  logoImg: { width: 40, height: 40 },
  brandLabel: { fontSize: 11, color: colors.muted },
  brandCity: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  badge: { position: "absolute", top: -2, right: -2, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: colors.error, alignItems: "center", justifyContent: "center", paddingHorizontal: 4 },
  badgeText: { color: colors.onError, fontSize: 10, fontWeight: "700" },
  search: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, marginTop: 4,
  },
  searchPlaceholder: { color: colors.muted, fontSize: fontSize.sm, flex: 1 },
  loadingWrap: { flex: 1, alignItems: "center", justifyContent: "center" },

  bannerWrap: { paddingTop: spacing.lg, paddingHorizontal: spacing.lg },
  banner: { height: 170, borderRadius: radius.lg, overflow: "hidden", justifyContent: "flex-end" },
  bannerContent: { padding: spacing.lg, gap: 4 },
  bannerTitle: { color: "#FFFFFF", fontSize: fontSize.xl, fontWeight: "500" },
  bannerSubtitle: { color: "#FFFFFF", fontSize: fontSize.sm, opacity: 0.9 },
  bannerCta: {
    alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, marginTop: 8,
  },
  bannerCtaText: { color: colors.onBrandPrimary, fontSize: fontSize.sm, fontWeight: "500" },
  dots: { flexDirection: "row", justifyContent: "center", gap: 6, marginTop: 8 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.border },
  dotActive: { backgroundColor: colors.brandPrimary, width: 18 },
});
