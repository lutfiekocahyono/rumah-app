import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Keyboard, Platform } from "react-native";
import { usePathname, useRouter } from "expo-router";
import { SafeAreaInsetsContext, useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useCart } from "@/src/cart-context";

// login / daftar / pembayaran stay plain so buyers can focus on finishing
const PLAIN = [/^\/login/, /^\/register/, /^\/forgot-password/, /^\/checkout/];
// these already have their own search box at the top
const OWN_SEARCH = [/^\/$/, /^\/search/, /^\/katalog/, /^\/scan/];

const ITEMS = [
  { key: "home", label: "Beranda", icon: "home", to: "/", match: (p: string) => p === "/" },
  { key: "katalog", label: "Katalog", icon: "grid", to: "/katalog",
    match: (p: string) => p.startsWith("/katalog") || p.startsWith("/search") || p.startsWith("/kategori") || p.startsWith("/category") },
  { key: "scan", label: "Scan", icon: "scan", to: "/scan", match: (p: string) => p.startsWith("/scan") },
  { key: "keranjang", label: "Keranjang", icon: "cart", to: "/keranjang", match: (p: string) => p.startsWith("/keranjang") },
  { key: "akun", label: "Akun", icon: "person", to: "/akun", match: (p: string) => p.startsWith("/akun") },
] as const;

function TopSearch({ top }: { top: number }) {
  const router = useRouter();
  return (
    <View style={[styles.top, { paddingTop: top + spacing.sm }]} testID="global-search-bar">
      <Pressable testID="global-search" style={styles.search} onPress={() => router.push("/search?focus=1" as any)}>
        <Icon name="search" size={18} color={colors.muted} />
        <Text style={styles.searchText}>Cari di Katalog Produk…</Text>
      </Pressable>
    </View>
  );
}

function BottomNav({ path, bottom }: { path: string; bottom: number }) {
  const router = useRouter();
  const { cart } = useCart();
  const go = (to: string) => {
    if (to === "/scan") router.push("/scan" as any);
    else router.navigate((to === "/" ? "/(tabs)" : `/(tabs)${to}`) as any);
  };
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(bottom, 6) }]} testID="global-bottom-nav">
      <View style={styles.barInner}>
        {ITEMS.map((it) => {
          const on = it.match(path);
          const tint = on ? colors.brandPrimary : colors.muted;
          if (it.key === "scan") {
            return (
              <Pressable key={it.key} testID="tab-scan" style={styles.item} onPress={() => go(it.to)} accessibilityLabel="Scan">
                <View style={styles.scanBtn}><Icon name="scan" size={26} color={colors.onBrandPrimary} /></View>
                <Text style={[styles.label, { color: tint }]}>{it.label}</Text>
              </Pressable>
            );
          }
          return (
            <Pressable key={it.key} testID={`tab-${it.key}`} style={styles.item} onPress={() => go(it.to)} accessibilityLabel={it.label}>
              <View>
                <Icon name={(on ? it.icon : `${it.icon}-outline`) as any} size={24} color={tint} />
                {it.key === "keranjang" && cart.item_count > 0 ? (
                  <View style={styles.badge} testID="cart-tab-badge"><Text style={styles.badgeText}>{cart.item_count > 99 ? "99+" : cart.item_count}</Text></View>
                ) : null}
              </View>
              <Text style={[styles.label, { color: tint }]}>{it.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** Search box on top + navigation bar at the bottom of every page (except login & payment). */
export function AppChrome({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const insets = useSafeAreaInsets();
  const [kb, setKb] = useState(false);
  useEffect(() => {
    if (Platform.OS === "web") return;
    const a = Keyboard.addListener("keyboardDidShow", () => setKb(true));
    const b = Keyboard.addListener("keyboardDidHide", () => setKb(false));
    return () => { a.remove(); b.remove(); };
  }, []);
  const plain = PLAIN.some((r) => r.test(path));
  const showTop = !plain && !OWN_SEARCH.some((r) => r.test(path));
  const showBottom = !plain && !kb;
  // screens add their own safe-area padding: give them 0 where our bars already cover the notch / home indicator
  const inner = { ...insets, top: showTop ? 0 : insets.top, bottom: showBottom ? 0 : insets.bottom };
  return (
    <View style={styles.root}>
      {showTop ? <TopSearch top={insets.top} /> : null}
      <SafeAreaInsetsContext.Provider value={inner}>
        <View style={styles.root}>{children}</View>
      </SafeAreaInsetsContext.Provider>
      {showBottom ? <BottomNav path={path} bottom={insets.bottom} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  top: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 42, borderRadius: radius.pill, paddingHorizontal: spacing.md, backgroundColor: colors.surfaceSecondary, width: "100%", maxWidth: 720, alignSelf: "center" },
  searchText: { color: colors.muted, fontSize: fontSize.sm },
  bar: { backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  barInner: { flexDirection: "row", alignItems: "flex-end", width: "100%", maxWidth: 720, alignSelf: "center", paddingTop: 6 },
  item: { flex: 1, alignItems: "center", justifyContent: "flex-end", gap: 2, minHeight: 50 },
  label: { fontSize: 11 },
  scanBtn: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: -22, borderWidth: 4, borderColor: colors.surface },
  badge: { position: "absolute", top: -4, right: -8, minWidth: 16, height: 16, paddingHorizontal: 4, borderRadius: 8, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  badgeText: { color: colors.onBrandPrimary, fontSize: 10, fontWeight: "500" },
});
