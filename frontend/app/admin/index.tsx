import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type AdminStats } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";

const MENU = [
  { icon: "receipt-outline", label: "Pesanan Masuk", sub: "Lihat & ubah status pesanan", to: "/admin/orders" },
  { icon: "people-outline", label: "Kategori Pelanggan", sub: "Pengecer, Reseller, Pembeli Langsung", to: "/admin/customers" },
  { icon: "add-circle-outline", label: "Tambah Produk", sub: "Seller Center: foto, video, variasi, harga & stok", to: "/product-editor/new" },
  { icon: "list-outline", label: "Daftar Produk", sub: "Edit massal, duplikat, impor & ekspor Excel", to: "/product-editor/list" },
  { icon: "cube-outline", label: "Harga Grosir per Produk", sub: "Cari produk lalu atur harga grosir di Ubah Produk", to: "/admin/products" },
  { icon: "images-outline", label: "Banner Promosi", sub: "Gambar, judul & tautan di beranda", to: "/admin/banners" },
  { icon: "flash-outline", label: "Flash Sale", sub: "Produk, harga flash & jam berakhir", to: "/admin/flash-sale" },
  { icon: "ticket-outline", label: "Voucher Diskon", sub: "Kode kupon % atau Rp untuk checkout", to: "/admin/vouchers" },
  { icon: "car-outline", label: "Gratis Ongkir", sub: "Banner info ongkir di beranda", to: "/admin/home-settings" },
  { icon: "flame-outline", label: "Produk di Beranda", sub: "Populer, Terbaru & Rekomendasi per cabang", to: "/admin/home-sections" },
  { icon: "alert-circle-outline", label: "Komplain & Refund", sub: "Pantau semua toko, putuskan komplain yang diteruskan", to: "/complaint?scope=admin" },
  { icon: "storefront-outline", label: "Verifikasi Toko", sub: "Setujui / tolak toko penjual baru", to: "/admin/stores" },
  { icon: "bar-chart-outline", label: "Laporan Pendapatan", sub: "Pendapatan & tarif kurir per toko", to: "/admin/report" },
  { icon: "card-outline", label: "Pengaturan Pembayaran", sub: "Kunci Midtrans (Sandbox / Production)", to: "/admin/payments" },
  { icon: "navigate-outline", label: "Pengaturan Ongkir Otomatis", sub: "API key RajaOngkir & lokasi asal tiap toko", to: "/admin/shipping" },
  { icon: "sync-outline", label: "Integrasi Accurate Online", sub: "Kunci API, uji koneksi, gudang & pratinjau barang", to: "/admin/accurate" },
  { icon: "phone-portrait-outline", label: "Notifikasi Push HP", sub: "Aktif/nonaktif push info produk (setelah rilis)", to: "/admin/push" },
];

export default function AdminHome() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      setErr("");
      setStats(await api.adminStats());
    } catch (e: any) {
      setErr(e.message);
    }
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  if (user?.role !== "admin") {
    return (
      <View style={[styles.root, { paddingTop: insets.top }]}>
        <ScreenHeader title="Admin Panel" />
        <View style={styles.center}>
          <Icon name="lock-closed-outline" size={40} color={colors.muted} />
          <Text style={styles.muted}>Masuk dengan akun admin untuk membuka panel ini.</Text>
          <Pressable testID="admin-login-btn" style={styles.loginBtn} onPress={() => router.push("/login" as any)}>
            <Text style={styles.loginText}>Masuk</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const cards = stats ? [
    { label: "Pesanan hari ini", value: String(stats.orders_today), icon: "bag-handle-outline" },
    { label: "Omzet hari ini", value: formatIDR(stats.revenue_today), icon: "cash-outline" },
    { label: "Perlu diproses", value: String(stats.need_action), icon: "alert-circle-outline", to: "/admin/orders" },
    { label: "Menunggu bayar", value: String(stats.waiting_payment), icon: "time-outline", to: "/admin/orders" },
    { label: "Pelanggan", value: String(stats.customers), icon: "people-outline", to: "/admin/customers" },
    { label: "Produk", value: stats.products.toLocaleString("id-ID"), icon: "cube-outline", to: "/admin/products" },
  ] : [];

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-home-screen">
      <ScreenHeader title="Admin Panel" />
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.brandPrimary} />}
      >
        <View style={styles.brand}>
          <Image source={require("../../assets/images/pgs-logo-small.png")} style={styles.logo} contentFit="contain" />
          <View style={{ flex: 1 }}>
            <Text style={styles.brandName}>Pusat Grosir Sidoarjo</Text>
            <Text style={styles.muted}>Halo, {user.name}</Text>
          </View>
        </View>
        {err ? <Text style={styles.err}>{err}</Text> : null}
        <View style={styles.grid}>
          {cards.map((c) => (
            <Pressable key={c.label} testID={`stat-${c.label}`} style={styles.stat} disabled={!c.to} onPress={() => c.to && router.push(c.to as any)}>
              <Icon name={c.icon as any} size={18} color={colors.brandPrimary} />
              <Text style={styles.statValue} numberOfLines={1} adjustsFontSizeToFit>{c.value}</Text>
              <Text style={styles.statLabel}>{c.label}</Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.list}>
          {MENU.map((m, i) => (
            <Pressable key={m.to} testID={`admin-menu-${m.to.split("/").pop()!.replace(/\?.*/, "")}`} style={[styles.row, i === MENU.length - 1 && { borderBottomWidth: 0 }]} onPress={() => router.push(m.to as any)}>
              <View style={styles.rowIcon}><Icon name={m.icon as any} size={20} color={colors.brandPrimary} /></View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowLabel}>{m.label}</Text>
                <Text style={styles.rowSub}>{m.sub}</Text>
              </View>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl },
  muted: { fontSize: fontSize.sm, color: colors.muted, textAlign: "left" },
  err: { color: colors.error, fontSize: fontSize.sm },
  loginBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.xl, minHeight: 48, justifyContent: "center" },
  loginText: { color: colors.onBrandPrimary, fontWeight: "500" },
  brand: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md },
  logo: { width: 52, height: 52 },
  brandName: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  stat: { width: "48.5%", flexGrow: 1, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  statValue: { fontSize: fontSize.xl, color: colors.onSurface, fontWeight: "500" },
  statLabel: { fontSize: 12, color: colors.muted },
  list: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, minHeight: 64, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  rowIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  rowLabel: { fontSize: fontSize.base, color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
