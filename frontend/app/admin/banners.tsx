import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import * as ImagePicker from "expo-image-picker";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Banner, type BannerInput, type Category } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ProductPicker } from "@/src/components/product-picker";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, Chips, digits, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

const EMPTY: BannerInput = { title: "", subtitle: "", image: "", link_type: "none", link_value: "", order: 0, active: true };
const LINKS = [
  { id: "none", label: "Tanpa tautan" }, { id: "category", label: "Kategori" },
  { id: "product", label: "Produk" }, { id: "search", label: "Kata pencarian" },
] as const;

export default function AdminBanners() {
  const insets = useSafeAreaInsets();
  const [list, setList] = useState<Banner[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<BannerInput | null>(null);
  const [editId, setEditId] = useState<string | undefined>();
  const [productName, setProductName] = useState("");
  const [busy, setBusy] = useState("");
  const [askDel, setAskDel] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  const load = useCallback(async () => {
    try {
      const [b, c] = await Promise.all([api.adminBanners(), api.categories()]);
      setList(b);
      setCats(c);
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const set = (patch: Partial<BannerInput>) => setForm((f) => (f ? { ...f, ...patch } : f));

  const pickImage = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8, allowsEditing: true, aspect: [16, 7] });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setBusy("upload");
    setMsg({ err: "", ok: "" });
    try {
      const { url } = await api.adminUpload({ uri: a.uri, name: a.fileName ?? "banner.jpg", mimeType: a.mimeType ?? "image/jpeg" });
      set({ image: url });
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    if (!form) return;
    if (!form.title.trim() || !form.image) return setMsg({ err: "Judul dan gambar wajib diisi", ok: "" });
    if (form.link_type !== "none" && !form.link_value.trim()) return setMsg({ err: "Pilih tujuan tautan", ok: "" });
    setBusy("save");
    try {
      await api.adminSaveBanner({ ...form, link_value: form.link_type === "none" ? "" : form.link_value.trim() }, editId);
      setForm(null);
      setMsg({ err: "", ok: "Banner disimpan" });
      await load();
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setBusy("");
    }
  };

  const remove = async (id: string) => {
    setBusy(`del-${id}`);
    try {
      await api.adminDeleteBanner(id);
      setForm(null);
      await load();
    } finally {
      setBusy("");
    }
  };

  const edit = (b?: Banner) => {
    setMsg({ err: "", ok: "" });
    setEditId(b?.banner_id);
    setProductName(b?.link_type === "product" ? b.link_value : "");
    setForm(b ? { title: b.title, subtitle: b.subtitle, image: b.image, link_type: b.link_type, link_value: b.link_value, order: b.order, active: b.active }
      : { ...EMPTY, order: list.length });
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-banners-screen">
      <ScreenHeader title="Banner Promosi" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        {msg.err ? <Text style={adminStyles.err} testID="banner-error">{msg.err}</Text> : null}
        {msg.ok ? <Text style={adminStyles.ok}>{msg.ok}</Text> : null}

        {form ? (
          <Card>
            <Text style={styles.formTitle}>{editId ? "Ubah Banner" : "Banner Baru"}</Text>
            <Pressable testID="banner-pick-image" style={styles.imgPick} onPress={pickImage} disabled={busy === "upload"}>
              {form.image ? <Image source={imgUrl(form.image)} style={StyleSheet.absoluteFill} contentFit="cover" /> : null}
              {busy === "upload" ? <ActivityIndicator color={colors.brandPrimary} /> : (
                <View style={styles.imgPickInner}>
                  <Icon name="image-outline" size={20} color={colors.onSurface} />
                  <Text style={styles.imgPickText}>{form.image ? "Ganti gambar" : "Pilih gambar banner"}</Text>
                </View>
              )}
            </Pressable>
            <Field testID="banner-title" label="Judul" value={form.title} onChangeText={(t) => set({ title: t })} placeholder="Contoh: Promo Akhir Bulan" />
            <Field testID="banner-subtitle" label="Keterangan (opsional)" value={form.subtitle} onChangeText={(t) => set({ subtitle: t })} placeholder="Contoh: Diskon hingga 30%" />
            <Text style={adminStyles.section}>Saat banner ditekan, buka:</Text>
            <Chips testID="banner-link" options={LINKS as any} value={form.link_type} onChange={(v) => set({ link_type: v, link_value: "" })} />
            {form.link_type === "category" ? (
              <Chips testID="banner-cat" options={cats.map((c) => ({ id: c.category_id, label: c.name }))} value={form.link_value} onChange={(v) => set({ link_value: v })} />
            ) : null}
            {form.link_type === "search" ? (
              <Field testID="banner-search" label="Kata pencarian" value={form.link_value} onChangeText={(t) => set({ link_value: t })} placeholder="Contoh: panci" />
            ) : null}
            {form.link_type === "product" ? (
              <View style={{ gap: spacing.sm }}>
                {form.link_value ? <Text style={styles.picked} numberOfLines={1}>Produk: {productName || form.link_value}</Text> : null}
                <ProductPicker testID="banner-product" onPick={(p) => { set({ link_value: p.product_id }); setProductName(p.name); }} />
              </View>
            ) : null}
            <Field testID="banner-order" label="Urutan tampil" keyboardType="number-pad" value={String(form.order)} onChangeText={(t) => set({ order: digits(t) })} />
            <ToggleRow testID="banner-active" label="Tampilkan di beranda" value={form.active} onChange={(v) => set({ active: v })} />
            <PrimaryButton testID="banner-save" label="Simpan Banner" onPress={save} loading={busy === "save"} />
            <PrimaryButton label="Batal" variant="outline" onPress={() => setForm(null)} />
            {editId ? <PrimaryButton testID="banner-delete" label="Hapus Banner" variant="danger" onPress={() => setAskDel(true)} /> : null}
            <ConfirmDialog visible={askDel} title="Hapus banner?" message={`Banner "${form.title}" akan dihapus dari beranda.`}
              loading={busy === `del-${editId}`} onCancel={() => setAskDel(false)} onConfirm={async () => { await remove(editId!); setAskDel(false); }} />
          </Card>
        ) : (
          <PrimaryButton testID="banner-add" label="+ Tambah Banner" onPress={() => edit()} />
        )}

        {loading ? <ActivityIndicator color={colors.brandPrimary} /> : list.map((b) => (
          <Pressable key={b.banner_id} testID={`admin-banner-${b.banner_id}`} style={styles.row} onPress={() => edit(b)}>
            <Image source={imgUrl(b.image)} style={styles.thumb} contentFit="cover" />
            <View style={{ flex: 1 }}>
              <Text style={styles.name} numberOfLines={1}>{b.title}</Text>
              <Text style={adminStyles.muted} numberOfLines={1}>
                #{b.order} · {b.active ? "Tampil" : "Disembunyikan"} · {LINKS.find((l) => l.id === b.link_type)?.label}
              </Text>
            </View>
            <Icon name="create-outline" size={20} color={colors.muted} />
          </Pressable>
        ))}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  formTitle: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  imgPick: { height: 150, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary, overflow: "hidden", alignItems: "center", justifyContent: "center" },
  imgPickInner: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8 },
  imgPickText: { fontSize: fontSize.sm, color: colors.onSurface },
  picked: { fontSize: fontSize.sm, color: colors.brandPrimary },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, minHeight: 64 },
  thumb: { width: 88, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
});
