import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import * as ImagePicker from "expo-image-picker";

import { colors, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Category, type SellerProductInput } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, Chips, digits, Field, PrimaryButton } from "@/src/components/admin-form";

const EMPTY: SellerProductInput = { name: "", description: "", category: "", price: 0, original_price: 0, stock: 0, images: [] };

export default function SellerProductForm() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const isNew = id === "new";
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [form, setForm] = useState<SellerProductInput | null>(isNew ? { ...EMPTY } : null);
  const [cats, setCats] = useState<Category[]>([]);
  const [busy, setBusy] = useState("");
  const [askDel, setAskDel] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.categories().then(setCats).catch(() => {});
    if (!isNew && id) {
      api.product(id).then((p) => setForm({ name: p.name, description: p.description, category: p.category, price: p.price,
        original_price: p.original_price > p.price ? p.original_price : 0, stock: p.stock, images: p.images?.length ? p.images : [p.image] }))
        .catch((e) => setErr(e.message));
    }
  }, [id, isNew]);

  const set = (p: Partial<SellerProductInput>) => setForm((f) => (f ? { ...f, ...p } : f));

  const addPhoto = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8, allowsEditing: true, aspect: [1, 1] });
    if (r.canceled || !r.assets?.[0] || !form) return;
    const a = r.assets[0];
    setBusy("upload");
    setErr("");
    try {
      const { url } = await api.sellerUpload({ uri: a.uri, name: a.fileName ?? "produk.jpg", mimeType: a.mimeType ?? "image/jpeg" });
      setForm((f) => (f ? { ...f, images: [...f.images, url] } : f));
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const save = async () => {
    if (!form) return;
    if (form.name.trim().length < 3) return setErr("Nama produk minimal 3 huruf");
    if (!form.category) return setErr("Pilih kategori");
    if (form.price < 100) return setErr("Harga minimal Rp100");
    if (!form.images.length) return setErr("Tambahkan minimal 1 foto produk");
    setBusy("save");
    setErr("");
    try {
      await api.sellerSaveProduct({ ...form, name: form.name.trim() }, isNew ? undefined : id);
      router.back();
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const remove = async () => {
    setBusy("del");
    try { await api.sellerDeleteProduct(id!); setAskDel(false); router.back(); } catch (e: any) { setErr(e.message); setBusy(""); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="seller-product-screen">
      <ScreenHeader title={isNew ? "Tambah Produk" : "Ubah Produk"} />
      {!form ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          <Card>
            <Text style={adminStyles.section}>Foto produk (maks. 8)</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
              {form.images.map((u, i) => (
                <View key={u} style={styles.photo}>
                  <Image source={imgUrl(u)} style={styles.photoImg} contentFit="cover" />
                  <Pressable testID={`photo-remove-${i}`} hitSlop={6} style={styles.photoX} onPress={() => set({ images: form.images.filter((x) => x !== u) })}>
                    <Icon name="close" size={14} color={colors.onSurfaceInverse} />
                  </Pressable>
                </View>
              ))}
              {form.images.length < 8 ? (
                <Pressable testID="photo-add" style={[styles.photo, styles.photoAdd]} onPress={addPhoto} disabled={busy === "upload"}>
                  {busy === "upload" ? <ActivityIndicator color={colors.brandPrimary} /> : <Icon name="camera-outline" size={26} color={colors.brandPrimary} />}
                </Pressable>
              ) : null}
            </ScrollView>
            <Field testID="sp-name" label="Nama produk" value={form.name} onChangeText={(t) => set({ name: t })} />
            <Text style={adminStyles.section}>Kategori</Text>
            <Chips testID="sp-cat" value={form.category} onChange={(v) => set({ category: v })} options={cats.map((c) => ({ id: c.category_id, label: c.name }))} />
            <Field testID="sp-price" label="Harga jual (Rp)" keyboardType="number-pad" value={form.price ? String(form.price) : ""} onChangeText={(t) => set({ price: digits(t) })} />
            <Field testID="sp-orig" label="Harga coret (opsional, Rp)" hint="Isi jika ingin menampilkan diskon" keyboardType="number-pad" value={form.original_price ? String(form.original_price) : ""} onChangeText={(t) => set({ original_price: digits(t) })} />
            <Field testID="sp-stock" label="Stok" keyboardType="number-pad" value={String(form.stock)} onChangeText={(t) => set({ stock: digits(t) })} />
            <Field testID="sp-desc" label="Deskripsi" value={form.description} onChangeText={(t) => set({ description: t })} multiline />
          </Card>
          {err ? <Text style={adminStyles.err} testID="sp-error">{err}</Text> : null}
          <PrimaryButton testID="sp-save" label="Simpan Produk" onPress={save} loading={busy === "save"} />
          {!isNew ? <PrimaryButton testID="sp-delete" label="Hapus Produk" variant="danger" onPress={() => setAskDel(true)} /> : null}
        </ScrollView>
      )}
      <ConfirmDialog visible={askDel} title="Hapus produk?" message="Produk akan dihapus dari toko Anda." loading={busy === "del"}
        onConfirm={remove} onCancel={() => setAskDel(false)} />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  photo: { width: 84, height: 84, borderRadius: radius.sm, overflow: "hidden", backgroundColor: colors.surfaceTertiary },
  photoImg: { width: 84, height: 84 },
  photoX: { position: "absolute", top: 4, right: 4, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center" },
  photoAdd: { alignItems: "center", justifyContent: "center", borderWidth: 1, borderStyle: "dashed", borderColor: colors.brandPrimary },
});
