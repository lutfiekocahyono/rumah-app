import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Category, type HomeSectionKey, type HomeSectionsSettings, type HomeSort } from "@/src/api";
import { adminStyles, Card, Chips, digits, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";
import { ProductPicker } from "@/src/components/product-picker";

type Pin = { product_id: string; name: string; image: string };
type Draft = { enabled: boolean; title: string; limit: string; sort: HomeSort; categories: string[]; days: string; pins: Pin[] };

const SECTIONS: { key: HomeSectionKey; label: string; icon: string }[] = [
  { key: "popular", label: "Produk Populer", icon: "flame-outline" },
  { key: "newest", label: "Produk Terbaru", icon: "sparkles-outline" },
  { key: "recommended", label: "Rekomendasi untukmu", icon: "thumbs-up-outline" },
];
const SORTS: { id: HomeSort; label: string }[] = [
  { id: "best_selling", label: "Terlaris" },
  { id: "rating", label: "Rating tertinggi" },
  { id: "most_viewed", label: "Paling sering dilihat" },
  { id: "newest", label: "Terbaru / restok" },
  { id: "random", label: "Acak" },
];
const PERSONAL = { id: "personal" as HomeSort, label: "Sesuai minat pembeli" };

const toDrafts = (s: HomeSectionsSettings) =>
  Object.fromEntries(SECTIONS.map(({ key }) => {
    const c = s.sections[key];
    return [key, { enabled: c.enabled, title: c.title, limit: String(c.limit), sort: c.sort, categories: c.categories, days: String(c.days), pins: c.pinned_products }];
  })) as unknown as Record<HomeSectionKey, Draft>;

/** Rules editor for the three homepage product sections of one branch. */
export function HomeSectionsEditor({ load, save, header }: {
  load: () => Promise<HomeSectionsSettings>;
  save: (s: Parameters<typeof api.saveSellerHomeSections>[0]) => Promise<HomeSectionsSettings>;
  header?: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  const [drafts, setDrafts] = useState<Record<HomeSectionKey, Draft> | null>(null);
  const [storeName, setStoreName] = useState("");
  const [tab, setTab] = useState<HomeSectionKey>("popular");
  const [cats, setCats] = useState<Category[]>([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  const reload = useCallback(async () => {
    setDrafts(null);
    try { const s = await load(); setStoreName(s.store_name); setDrafts(toDrafts(s)); } catch (e: any) { setMsg({ err: e.message, ok: "" }); }
  }, [load]);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => { api.categories().then(setCats).catch(() => {}); }, []);

  const d = drafts?.[tab];
  const set = (patch: Partial<Draft>) => setDrafts((x) => (x ? { ...x, [tab]: { ...x[tab], ...patch } } : x));
  const movePin = (i: number, dir: -1 | 1) => {
    if (!d) return;
    const pins = [...d.pins];
    const j = i + dir;
    if (j < 0 || j >= pins.length) return;
    [pins[i], pins[j]] = [pins[j], pins[i]];
    set({ pins });
  };

  const submit = async () => {
    if (!drafts) return;
    setSaving(true);
    setMsg({ err: "", ok: "" });
    try {
      const body = Object.fromEntries(SECTIONS.map(({ key }) => {
        const x = drafts[key];
        return [key, { enabled: x.enabled, title: x.title.trim() || SECTIONS.find((s) => s.key === key)!.label, limit: Math.min(30, Math.max(1, digits(x.limit) || 10)),
          sort: x.sort, pinned: x.pins.map((p) => p.product_id), categories: x.categories, days: Math.min(90, Math.max(1, digits(x.days) || 7)) }];
      })) as any;
      const s = await save(body);
      setDrafts(toDrafts(s));
      setMsg({ err: "", ok: "Pengaturan beranda disimpan" });
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        {header}
        {!drafts || !d ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
          <>
            <Text style={adminStyles.muted}>
              Aturan untuk pembeli yang memilih cabang {storeName}. Produk pilihan manual dari semua cabang tampil bersama di beranda (cabang pembeli lebih dulu), lalu sisanya diisi otomatis.
            </Text>
            <Chips testID="hs-tab" value={tab} onChange={setTab} options={SECTIONS.map((s) => ({ id: s.key, label: s.label }))} />

            <Card>
              <ToggleRow testID="hs-enabled" label="Tampilkan di beranda" value={d.enabled} onChange={(v) => set({ enabled: v })} />
              <Field testID="hs-title" label="Judul bagian" value={d.title} onChangeText={(t) => set({ title: t })} maxLength={40} />
              <Field testID="hs-limit" label={tab === "recommended" ? "Jumlah produk per halaman (1–30)" : "Jumlah produk (1–30)"} keyboardType="number-pad" value={d.limit} onChangeText={(t) => set({ limit: t.replace(/\D/g, "") })} />
            </Card>

            <Text style={adminStyles.section}>Urutan otomatis</Text>
            <Card>
              <Chips testID="hs-sort" value={d.sort} onChange={(v) => set({ sort: v })} options={tab === "recommended" ? [PERSONAL, ...SORTS] : SORTS} />
              {tab === "newest" ? (
                <>
                  <Field testID="hs-days" label="Periode (hari)" keyboardType="number-pad" value={d.days} onChangeText={(t) => set({ days: t.replace(/\D/g, "") })}
                    hint={`Hanya produk yang baru diunggah ATAU baru direstok dalam ${digits(d.days) || 7} hari terakhir.`} />
                </>
              ) : null}
              <Text style={adminStyles.muted}>Terlaris = data terjual lama + pesanan selesai di aplikasi (berkurang lagi bila pesanan dibatalkan).</Text>
            </Card>

            <Text style={adminStyles.section}>Batasi ke kategori (kosong = semua kategori)</Text>
            <Card>
              <View style={styles.wrap}>
                {cats.map((c) => {
                  const on = d.categories.includes(c.category_id);
                  return (
                    <Pressable key={c.category_id} testID={`hs-cat-${c.category_id}`} style={[styles.chip, on && styles.chipOn]}
                      onPress={() => set({ categories: on ? d.categories.filter((x) => x !== c.category_id) : [...d.categories, c.category_id] })}>
                      <Text style={[styles.chipText, on && styles.chipTextOn]}>{c.name}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </Card>

            <Text style={adminStyles.section}>Produk pilihan manual (tampil paling depan, maks. 30)</Text>
            <Card>
              {d.pins.length ? d.pins.map((p, i) => (
                <View key={p.product_id} style={styles.pin} testID={`hs-pin-${p.product_id}`}>
                  <Text style={styles.pinNo}>{i + 1}</Text>
                  <Image source={imgUrl(p.image)} style={styles.pinImg} contentFit="cover" />
                  <Text style={styles.pinName} numberOfLines={2}>{p.name}</Text>
                  <Pressable hitSlop={6} testID={`hs-pin-up-${p.product_id}`} onPress={() => movePin(i, -1)} style={styles.iconBtn} disabled={i === 0}>
                    <Icon name="chevron-up" size={18} color={i === 0 ? colors.border : colors.onSurface} />
                  </Pressable>
                  <Pressable hitSlop={6} testID={`hs-pin-down-${p.product_id}`} onPress={() => movePin(i, 1)} style={styles.iconBtn} disabled={i === d.pins.length - 1}>
                    <Icon name="chevron-down" size={18} color={i === d.pins.length - 1 ? colors.border : colors.onSurface} />
                  </Pressable>
                  <Pressable hitSlop={6} testID={`hs-pin-remove-${p.product_id}`} onPress={() => set({ pins: d.pins.filter((x) => x.product_id !== p.product_id) })} style={styles.iconBtn}>
                    <Icon name="close-circle" size={20} color={colors.error} />
                  </Pressable>
                </View>
              )) : <Text style={adminStyles.muted}>Belum ada. Beranda memakai urutan otomatis.</Text>}
              {d.pins.length < 30 ? (
                <ProductPicker testID="hs-pin-search" onPick={(p) => { if (!d.pins.some((x) => x.product_id === p.product_id)) set({ pins: [...d.pins, { product_id: p.product_id, name: p.name, image: p.image }] }); }} />
              ) : null}
            </Card>

            {msg.err ? <Text style={adminStyles.err} testID="hs-error">{msg.err}</Text> : null}
            {msg.ok ? <Text style={adminStyles.ok} testID="hs-ok">{msg.ok}</Text> : null}
            <PrimaryButton testID="hs-save" label="Simpan Semua Bagian" onPress={submit} loading={saving} />
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 44, justifyContent: "center" },
  chipOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, color: colors.onSurface },
  chipTextOn: { color: colors.onBrandPrimary, fontWeight: "500" },
  pin: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48 },
  pinNo: { width: 18, fontSize: fontSize.sm, color: colors.muted, textAlign: "center" },
  pinImg: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  pinName: { flex: 1, fontSize: 13, color: colors.onSurface },
  iconBtn: { width: 32, height: 40, alignItems: "center", justifyContent: "center" },
});
