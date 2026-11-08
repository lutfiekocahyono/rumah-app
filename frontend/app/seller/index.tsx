import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Product, type Report, type Store, type StoreInput } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { UnreadBadge, useChatUnread } from "@/src/components/unread-badge";
import { adminStyles, Card, Field, PrimaryButton } from "@/src/components/admin-form";

const STATUS = {
  pending: { label: "Menunggu verifikasi admin", color: colors.warning, icon: "time-outline" },
  active: { label: "Toko aktif", color: colors.success, icon: "checkmark-circle-outline" },
  rejected: { label: "Pengajuan ditolak", color: colors.error, icon: "close-circle-outline" },
  suspended: { label: "Toko dinonaktifkan", color: colors.error, icon: "ban-outline" },
} as const;

export default function SellerHome() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [store, setStore] = useState<Store | null | undefined>(undefined);
  const [products, setProducts] = useState<Product[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [form, setForm] = useState<StoreInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const unread = useChatUnread(store?.status === "active");

  const load = useCallback(async () => {
    if (!user) return setStore(null);
    try {
      const s = await api.myStore();
      setStore(s);
      if (s?.status === "active") {
        const [p, r] = await Promise.all([s.store_id === "pgs-official" ? Promise.resolve([]) : api.sellerProducts(), api.sellerReport()]);
        setProducts(p);
        setReport(r);
      }
    } catch (e: any) { setErr(e.message); setStore(null); }
  }, [user]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const set = (p: Partial<StoreInput>) => setForm((f) => (f ? { ...f, ...p } : f));
  const submit = async () => {
    if (!form) return;
    if (form.name.trim().length < 3 || form.city.trim().length < 2) return setErr("Lengkapi nama toko (min. 3 huruf) dan kota");
    if (form.phone.trim() && form.phone.trim().length < 8) return setErr("Nomor HP minimal 8 angka, atau kosongkan dulu");
    setBusy(true);
    setErr("");
    try {
      setStore(store ? await api.editStore(form) : await api.openStore(form));
      setForm(null);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (!user) {
    return (
      <View style={[adminStyles.root, { paddingTop: insets.top }]}>
        <ScreenHeader title="Toko Saya" />
        <View style={{ padding: spacing.lg, gap: spacing.md }}>
          <Text style={adminStyles.muted}>Masuk dulu untuk membuka toko.</Text>
          <PrimaryButton label="Masuk" onPress={() => router.push("/login" as any)} />
        </View>
      </View>
    );
  }

  const st = store ? STATUS[store.status] : null;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="seller-screen">
      <ScreenHeader title="Toko Saya" />
      {store === undefined ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          {err ? <Text style={adminStyles.err} testID="seller-error">{err}</Text> : null}
          {form ? (
            <Card>
              <Text style={styles.h}>{store ? "Ubah Profil Toko" : "Buka Toko Baru"}</Text>
              {!store ? <Text style={adminStyles.muted}>Toko akan diverifikasi admin sebelum tampil di marketplace.</Text> : null}
              <Field testID="store-name" label="Nama toko" value={form.name} onChangeText={(t) => set({ name: t })} placeholder="Contoh: Toko Berkah Jaya" />
              <Field testID="store-desc" label="Deskripsi toko" value={form.description} onChangeText={(t) => set({ description: t })} multiline />
              <Field testID="store-city" label="Kota" value={form.city} onChangeText={(t) => set({ city: t })} />
              <Field testID="store-phone" label="No. HP / WhatsApp toko (opsional)" value={form.phone} onChangeText={(t) => set({ phone: t })} keyboardType="phone-pad" />
              <Field testID="store-address" label="Alamat toko untuk Ambil di toko (opsional)" value={form.address ?? ""} onChangeText={(t) => set({ address: t })} multiline />
              <Field testID="store-hours" label="Jam ambil pesanan (opsional)" value={form.pickup_hours ?? ""} onChangeText={(t) => set({ pickup_hours: t })} placeholder="Contoh: Senin–Sabtu 08.00–16.00" />
              <PrimaryButton testID="store-submit" label={store ? "Simpan" : "Ajukan Toko"} onPress={submit} loading={busy} />
              <PrimaryButton label="Batal" variant="outline" onPress={() => setForm(null)} />
            </Card>
          ) : !store ? (
            <Card>
              <Icon name="storefront-outline" size={40} color={colors.brandPrimary} />
              <Text style={styles.h}>Mulai berjualan di Pusat Grosir Sidoarjo</Text>
              <Text style={adminStyles.muted}>Buka toko gratis, tambah produk, dan jangkau pembeli grosir & eceran.</Text>
              <PrimaryButton testID="open-store-btn" label="Buka Toko" onPress={() => setForm({ name: "", description: "", city: "Sidoarjo", phone: user.phone ?? "", logo: "" })} />
            </Card>
          ) : (
            <Card>
              <View style={styles.between}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.h}>{store.name}</Text>
                  <Text style={adminStyles.muted}>{store.city}</Text>
                </View>
                <Pressable testID="store-edit" hitSlop={8} onPress={() => setForm({ name: store.name, description: store.description, city: store.city, phone: store.phone ?? "", logo: store.logo, address: store.address ?? "", pickup_hours: store.pickup_hours ?? "" })}>
                  <Icon name="create-outline" size={22} color={colors.brandPrimary} />
                </Pressable>
              </View>
              {st ? (
                <View style={[styles.status, { borderColor: st.color }]} testID="store-status">
                  <Icon name={st.icon as any} size={16} color={st.color} />
                  <Text style={[styles.statusText, { color: st.color }]}>{st.label}</Text>
                </View>
              ) : null}
              {store.note ? <Text style={adminStyles.muted}>Catatan admin: {store.note}</Text> : null}
              {store.status === "rejected" ? <Text style={adminStyles.muted}>Perbaiki data toko lalu simpan untuk mengajukan ulang.</Text> : null}
              {store.status === "active" ? (
                <PrimaryButton label="Lihat Halaman Toko" variant="outline" onPress={() => router.push(`/shop/${store.store_id}` as any)} />
              ) : null}
            </Card>
          )}

          {store?.status === "active" ? (
            <>
              {report ? (
                <View style={styles.stats} testID="seller-report">
                  <View style={styles.stat}><Text style={styles.statVal}>{formatIDR(report.revenue_completed)}</Text><Text style={adminStyles.muted}>Pendapatan selesai</Text></View>
                  <View style={styles.stat}><Text style={styles.statVal}>{formatIDR(report.revenue_in_progress)}</Text><Text style={adminStyles.muted}>Pesanan berjalan</Text></View>
                  <View style={styles.stat}><Text style={styles.statVal}>{(report.by_status.paid?.orders ?? 0) + (report.by_status.cod?.orders ?? 0)}</Text><Text style={adminStyles.muted}>Pesanan baru</Text></View>
                  <View style={styles.stat}><Text style={styles.statVal}>{report.orders_completed}</Text><Text style={adminStyles.muted}>Pesanan selesai</Text></View>
                </View>
              ) : null}
              <View style={styles.nav}>
                {[
                  { icon: "receipt-outline", label: "Pesanan", to: "/seller/orders" },
                  { icon: "cube-outline", label: "Stok", to: "/seller/stock" },
                  { icon: "car-outline", label: "Tarif Kurir", to: "/seller/couriers" },
                  { icon: "chatbubbles-outline", label: "Chat", to: "/chat?side=store", badge: unread.store },
                  { icon: "alert-circle-outline", label: "Komplain", to: "/complaint?scope=store" },
                  ...(store.official ? [{ icon: "flame-outline", label: "Beranda", to: "/seller/home-sections" }] : []),
                ].map((n: { icon: string; label: string; to: string; badge?: number }) => (
                  <Pressable key={n.to} testID={`seller-nav-${n.to.split("/").pop()!.replace(/\?.*/, "")}`} style={styles.navItem} onPress={() => router.push(n.to as any)}>
                    <Icon name={n.icon as any} size={24} color={colors.brandPrimary} />
                    <Text style={styles.navText}>{n.label}</Text>
                    {n.badge ? (
                      <View style={styles.navBadge}><UnreadBadge count={n.badge} testID="seller-nav-chat-badge" /></View>
                    ) : null}
                  </Pressable>
                ))}
              </View>
              {report?.top_products.length ? (
                <Card>
                  <Text style={styles.h}>Produk terlaris</Text>
                  {report.top_products.map((t) => (
                    <Text key={t.product_id} style={adminStyles.muted} numberOfLines={1}>{t.qty}x · {t.name} · {formatIDR(t.revenue)}</Text>
                  ))}
                </Card>
              ) : null}
              <View style={styles.between}>
                <Text style={styles.h}>Produk Toko Ini ({products.length})</Text>
                <Pressable testID="seller-add-product" style={styles.addBtn} onPress={() => router.push("/seller/product/new" as any)}>
                  <Icon name="add" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.addText}>Tambah</Text>
                </Pressable>
              </View>
              {!products.length ? <Text style={adminStyles.muted}>Belum ada produk. Tambahkan produk pertama Anda.</Text> : products.map((p) => (
                <Pressable key={p.product_id} testID={`seller-product-${p.product_id}`} style={styles.row} onPress={() => router.push(`/seller/product/${p.product_id}` as any)}>
                  <Image source={p.image} style={styles.img} contentFit="cover" />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name} numberOfLines={2}>{p.name}</Text>
                    <Text style={styles.price}>{formatIDR(p.price)}</Text>
                    <Text style={[adminStyles.muted, !p.stock && { color: colors.error }]}>{p.stock ? `Stok ${p.stock}` : "Stok habis"}</Text>
                  </View>
                  <Icon name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>
              ))}
            </>
          ) : null}
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  stats: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  stat: { width: "48%", flexGrow: 1, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, gap: 2 },
  statVal: { fontSize: fontSize.base, fontWeight: "700", color: colors.brandPrimary },
  nav: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  navItem: { width: "31%", flexGrow: 1, alignItems: "center", gap: 6, backgroundColor: colors.surface, borderRadius: radius.md, paddingVertical: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, minHeight: 72 },
  navBadge: { position: "absolute", top: 6, right: 6 },
  navText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  between: { flexDirection: "row", alignItems: "center", gap: spacing.sm, justifyContent: "space-between" },
  status: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 6, alignSelf: "flex-start" },
  statusText: { fontSize: 13, fontWeight: "600" },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 40 },
  addText: { color: colors.onBrandPrimary, fontWeight: "500" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  img: { width: 64, height: 64, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  price: { fontSize: fontSize.sm, color: colors.brandPrimary, fontWeight: "600" },
});
