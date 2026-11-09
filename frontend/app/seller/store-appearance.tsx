import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Product, type StoreAppearance } from "@/src/api";
import { SellerShell } from "@/src/components/seller-shell";
import { adminStyles, Card, Chips, Field, PrimaryButton } from "@/src/components/admin-form";
import { uploadWithProgress } from "@/src/utils/upload-progress";

type Feat = StoreAppearance["featured"][number];

function ImagePick({ label, url, wide, testID, storeId, onChange }: { label: string; url: string; wide?: boolean; testID: string; storeId: string; onChange: (u: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pick = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.85, allowsEditing: true, aspect: wide ? [5, 2] : [1, 1] });
    if (r.canceled || !r.assets[0]) return;
    const a = r.assets[0];
    const name = a.fileName ?? a.uri.split("/").pop() ?? "gambar.jpg";
    setBusy(true); setErr("");
    try { onChange((await uploadWithProgress(`/store-appearance/${storeId}/upload`, { uri: a.uri, name, mimeType: a.mimeType ?? "image/jpeg" }, () => {})).url); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <View style={{ gap: 6 }}>
      <Text style={adminStyles.section}>{label}</Text>
      <Pressable testID={testID} onPress={pick} style={[wide ? styles.bannerBox : styles.logoBox]}>
        {busy ? <ActivityIndicator color={colors.brandPrimary} /> : url ? <Image source={{ uri: imgUrl(url) }} style={StyleSheet.absoluteFill} resizeMode="cover" />
          : <View style={{ alignItems: "center" }}><Icon name="image-outline" size={26} color={colors.muted} /><Text style={adminStyles.muted}>Pilih gambar</Text></View>}
      </Pressable>
      {url ? <Pressable testID={`${testID}-remove`} onPress={() => onChange("")} style={{ minHeight: 32 }}><Text style={{ color: colors.error }}>Hapus gambar</Text></Pressable> : null}
      {err ? <Text style={adminStyles.err}>{err}</Text> : null}
    </View>
  );
}

function FeaturedPicker({ storeId, list, onChange }: { storeId: string; list: Feat[]; onChange: (l: Feat[]) => void }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Product[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) { setRes([]); return; }
    const t = setTimeout(() => api.products({ branch: storeId, q: q.trim() }).then((p) => setRes(p.slice(0, 8))).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [q, storeId]);
  const move = (i: number, d: number) => { const l = [...list]; const [x] = l.splice(i, 1); l.splice(i + d, 0, x); onChange(l); };
  return (
    <View style={{ gap: spacing.sm }}>
      <Text style={adminStyles.section}>Produk andalan ({list.length}/10)</Text>
      <Text style={adminStyles.muted}>Kosongkan untuk otomatis menampilkan produk terlaris toko.</Text>
      {list.map((p, i) => (
        <View key={p.product_id} style={styles.feat} testID={`sa-feat-${p.product_id}`}>
          {p.image ? <Image source={{ uri: imgUrl(p.image) }} style={styles.thumb} /> : null}
          <Text style={{ flex: 1, color: colors.onSurface }} numberOfLines={2}>{i + 1}. {p.name}</Text>
          <Pressable hitSlop={6} disabled={i === 0} onPress={() => move(i, -1)} style={styles.iconBtn}><Icon name="arrow-up" size={18} color={i === 0 ? colors.border : colors.onSurface} /></Pressable>
          <Pressable hitSlop={6} disabled={i === list.length - 1} onPress={() => move(i, 1)} style={styles.iconBtn}><Icon name="arrow-down" size={18} color={i === list.length - 1 ? colors.border : colors.onSurface} /></Pressable>
          <Pressable hitSlop={6} testID={`sa-feat-remove-${p.product_id}`} onPress={() => onChange(list.filter((x) => x.product_id !== p.product_id))} style={styles.iconBtn}><Icon name="close" size={18} color={colors.error} /></Pressable>
        </View>
      ))}
      {list.length < 10 ? (
        <>
          <TextInput testID="sa-feat-search" value={q} onChangeText={setQ} placeholder="Cari produk untuk ditambahkan…" placeholderTextColor={colors.muted} style={styles.input} />
          {res.filter((p) => !list.some((x) => x.product_id === p.product_id)).map((p) => (
            <Pressable key={p.product_id} testID={`sa-feat-add-${p.product_id}`} style={styles.feat} onPress={() => { onChange([...list, { product_id: p.product_id, name: p.name, image: p.image }]); setQ(""); }}>
              {p.image ? <Image source={{ uri: imgUrl(p.image) }} style={styles.thumb} /> : null}
              <Text style={{ flex: 1, color: colors.onSurface }} numberOfLines={2}>{p.name}</Text>
              <Icon name="add-circle" size={22} color={colors.brandPrimary} />
            </Pressable>
          ))}
        </>
      ) : null}
    </View>
  );
}

function Editor({ a, onSaved }: { a: StoreAppearance; onSaved: (a: StoreAppearance) => void }) {
  const router = useRouter();
  const [f, setF] = useState(a);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { setF(a); }, [a]);
  const set = (p: Partial<StoreAppearance>) => { setF((x) => ({ ...x, ...p })); setMsg(null); };
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const { store_id: _s, name: _n, city: _c, featured, ...rest } = f;
      const r = await api.saveStoreAppearance(f.store_id, { ...rest, featured_ids: featured.map((x) => x.product_id) });
      onSaved(r); setMsg({ ok: true, text: "Tampilan toko disimpan" });
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  };
  return (
    <View style={{ gap: spacing.md }}>
      <Card>
        <ImagePick label="Banner (lebar, rasio 5:2)" wide url={f.banner} testID="sa-banner" storeId={f.store_id} onChange={(u) => set({ banner: u })} />
        <ImagePick label="Logo" url={f.logo} testID="sa-logo" storeId={f.store_id} onChange={(u) => set({ logo: u })} />
      </Card>
      <Card>
        <Field testID="sa-desc" label="Deskripsi toko" value={f.description} onChangeText={(t) => set({ description: t })} multiline maxLength={500} />
        <Field testID="sa-address" label="Alamat" value={f.address} onChangeText={(t) => set({ address: t })} multiline maxLength={300} />
        <Field testID="sa-hours" label="Jam ambil" placeholder="mis. Senin–Sabtu 08.00–16.00" value={f.pickup_hours} onChangeText={(t) => set({ pickup_hours: t })} maxLength={80} />
        <Field testID="sa-phone" label="Telepon / WhatsApp" keyboardType="phone-pad" value={f.phone} onChangeText={(t) => set({ phone: t })} maxLength={20} />
      </Card>
      <Card><FeaturedPicker storeId={f.store_id} list={f.featured} onChange={(l) => set({ featured: l })} /></Card>
      {msg ? <Text style={msg.ok ? adminStyles.ok : adminStyles.err} testID="sa-msg">{msg.text}</Text> : null}
      <PrimaryButton testID="sa-save" label="Simpan tampilan" loading={busy} onPress={save} />
      <PrimaryButton testID="sa-preview" label="Lihat halaman toko" variant="outline" onPress={() => router.push(`/shop/${f.store_id}` as any)} />
    </View>
  );
}

/** Tampilan toko cabang: admin cabang mengatur tokonya sendiri; Super Admin bisa memilih cabang. */
export default function StoreAppearanceScreen() {
  const insets = useSafeAreaInsets();
  const [list, setList] = useState<StoreAppearance[] | null>(null);
  const [sel, setSel] = useState("");
  const [err, setErr] = useState("");
  const [admin, setAdmin] = useState(false);
  useEffect(() => {
    api.me().then((u) => setAdmin(u.role === "admin")).catch(() => {});
    api.storeAppearance().then((l) => { setList(l); setSel(l[0]?.store_id ?? ""); }).catch((e) => setErr(e.message));
  }, []);
  const cur = list?.find((x) => x.store_id === sel);
  return (
    <SellerShell admin={admin} title="Tampilan Toko">
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled" testID="store-appearance-screen">
        <Text style={adminStyles.muted}>Atur banner, logo, info, dan produk andalan yang dilihat pembeli di halaman toko cabang.</Text>
        {err ? <Text style={adminStyles.err} testID="sa-error">{err}</Text> : !list ? <ActivityIndicator color={colors.brandPrimary} /> : (
          <>
            {list.length > 1 ? <Chips testID="sa-store" options={list.map((x) => ({ id: x.store_id, label: x.name }))} value={sel} onChange={setSel} /> : <Text style={styles.h}>{cur?.name}</Text>}
            {cur ? <Editor key={cur.store_id} a={cur} onSaved={(a) => setList((l) => l!.map((x) => (x.store_id === a.store_id ? a : x)))} /> : null}
          </>
        )}
      </ScrollView>
    </SellerShell>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  bannerBox: { width: "100%", aspectRatio: 2.5, borderRadius: radius.md, borderWidth: 1, borderStyle: "dashed", borderColor: colors.border, alignItems: "center", justifyContent: "center", overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  logoBox: { width: 96, height: 96, borderRadius: 48, borderWidth: 1, borderStyle: "dashed", borderColor: colors.border, alignItems: "center", justifyContent: "center", overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  feat: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  thumb: { width: 40, height: 40, borderRadius: radius.sm },
  iconBtn: { width: 36, height: 36, alignItems: "center", justifyContent: "center" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, minHeight: 44, color: colors.onSurface, backgroundColor: colors.surface },
});
