import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ScrollView, useWindowDimensions } from "react-native";
import { useRouter, usePathname } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api } from "@/src/api";

type Item = { label: string; icon: string; to: string; testID: string };
type Group = { label: string; icon: string; children: Item[] };

/** Seller Center menu. Only screens that exist for the role are listed (no dead buttons). */
function menu(admin: boolean, storeId: string): (Item | Group)[] {
  const branch = storeId === "pgs-jombang" || storeId === "pgs-jember";
  const official = branch || storeId === "pgs-official";
  const i = (label: string, icon: string, to: string): Item => ({ label, icon, to, testID: `nav-${label.toLowerCase().replace(/\s+/g, "-")}` });
  return [
    i("Dashboard", "grid-outline", admin ? "/admin" : "/seller"),
    { label: "Produk", icon: "cube-outline", children: [
      i("Tambah Produk", "add-circle-outline", "/product-editor/new"),
      i("Daftar Produk", "list-outline", "/product-editor/list"),
      i("Kategori Produk", "pricetags-outline", "/(tabs)/kategori"),
      ...(admin ? [] : [i("Manajemen Stok", "layers-outline", "/seller/stock")]),
      ...(admin || branch ? [i("Harga Cabang", "cash-outline", "/seller/branch-prices")] : []),
      i("Riwayat Harga & Stok", "time-outline", "/product-editor/history"),
    ] },
    i("Pesanan", "receipt-outline", admin ? "/admin/orders" : "/seller/orders"),
    i("Pengiriman", "car-outline", admin ? "/admin/shipping" : "/seller/couriers"),
    ...(admin ? [i("Promosi", "megaphone-outline", "/admin/vouchers")] : []),
    ...(admin ? [] : [i("Chat", "chatbubbles-outline", "/chat?side=store")]),
    i("Komplain", "alert-circle-outline", admin ? "/complaint?scope=admin" : "/complaint?scope=store"),
    ...(!admin && official ? [i("Beranda Toko", "flame-outline", "/seller/home-sections"), i("Jadwal Flash Sale", "flash-outline", "/seller/flash-schedule")] : []),
    i("Laporan Penjualan", "bar-chart-outline", admin ? "/admin/report" : "/seller"),
    i("Pengaturan Toko", "settings-outline", admin ? "/admin/stores" : "/seller"),
  ];
}

function Nav({ admin, onGo }: { admin: boolean; onGo: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const [open, setOpen] = useState(true);
  const [storeId, setStoreId] = useState("");
  useEffect(() => { if (!admin) api.myStore().then((s) => setStoreId(s?.store_id ?? "")).catch(() => {}); }, [admin]);
  const row = (it: Item, sub = false) => {
    const on = path === it.to || (it.to === "/product-editor/new" && path.startsWith("/product-editor") && path !== "/product-editor/list" && path !== "/product-editor/history");
    return (
      <Pressable key={it.testID} testID={it.testID} style={[styles.item, sub && styles.sub, on && styles.itemOn]}
        onPress={() => { onGo(); if (!on) router.push(it.to as any); }}>
        <Icon name={it.icon as any} size={18} color={on ? colors.brandPrimary : colors.onSurfaceSecondary} />
        <Text style={[styles.itemText, on && styles.itemTextOn]}>{it.label}</Text>
      </Pressable>
    );
  };
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.md, gap: 2 }}>
      <Text style={styles.brand}>PGS Seller Center</Text>
      {menu(admin, storeId).map((m) => ("children" in m ? (
        <View key={m.label}>
          <Pressable testID="nav-produk" style={styles.item} onPress={() => setOpen((o) => !o)}>
            <Icon name={m.icon as any} size={18} color={colors.onSurfaceSecondary} />
            <Text style={[styles.itemText, { flex: 1 }]}>{m.label}</Text>
            <Icon name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
          </Pressable>
          {open ? m.children.map((c) => row(c, true)) : null}
        </View>
      ) : row(m)))}
    </ScrollView>
  );
}

/** Dashboard layout: fixed sidebar on wide screens (≥ 900px), slide-in menu on phones/tablets. */
export function SellerShell({ admin, title, right, children }: { admin: boolean; title: string; right?: React.ReactNode; children: React.ReactNode }) {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const wide = width >= 900;
  const [drawer, setDrawer] = useState(false);
  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      {wide ? <View style={styles.side} testID="seller-sidebar"><Nav admin={admin} onGo={() => {}} /></View> : null}
      <View style={{ flex: 1 }}>
        <View style={styles.top}>
          {wide ? (
            <Pressable testID="shell-back" hitSlop={8} onPress={() => (router.canGoBack() ? router.back() : router.replace((admin ? "/admin" : "/seller") as any))}>
              <Icon name="chevron-back" size={22} color={colors.onSurface} />
            </Pressable>
          ) : (
            <>
              <Pressable testID="shell-back" hitSlop={8} onPress={() => (router.canGoBack() ? router.back() : router.replace((admin ? "/admin" : "/seller") as any))} style={styles.menuBtn}>
                <Icon name="chevron-back" size={22} color={colors.onSurface} />
              </Pressable>
              <Pressable testID="shell-menu" hitSlop={8} onPress={() => setDrawer(true)} style={styles.menuBtn}>
                <Icon name="menu" size={22} color={colors.onSurface} />
              </Pressable>
            </>
          )}
          <Text style={styles.title} numberOfLines={1}>{title}</Text>
          {right}
        </View>
        {children}
      </View>
      <Modal visible={drawer && !wide} transparent animationType="fade" onRequestClose={() => setDrawer(false)}>
        <View style={styles.overlay}>
          <View style={[styles.drawer, { paddingTop: insets.top }]} testID="seller-drawer">
            <Nav admin={admin} onGo={() => setDrawer(false)} />
          </View>
          <Pressable style={{ flex: 1 }} onPress={() => setDrawer(false)} testID="drawer-close" />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, flexDirection: "row", backgroundColor: colors.surfaceSecondary },
  side: { width: 248, backgroundColor: colors.surface, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: colors.border },
  top: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, minHeight: 56, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  menuBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { flex: 1, fontSize: fontSize.lg, fontWeight: "600", color: colors.onSurface },
  brand: { fontSize: fontSize.base, fontWeight: "700", color: colors.brandPrimary, paddingHorizontal: spacing.sm, paddingVertical: spacing.md },
  item: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 44, paddingHorizontal: spacing.sm, borderRadius: radius.sm },
  sub: { paddingLeft: spacing.xl },
  itemOn: { backgroundColor: colors.brandTertiary },
  itemText: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  itemTextOn: { color: colors.brandPrimary, fontWeight: "600" },
  overlay: { flex: 1, flexDirection: "row", backgroundColor: "rgba(0,0,0,0.35)" },
  drawer: { width: 280, backgroundColor: colors.surface },
});
