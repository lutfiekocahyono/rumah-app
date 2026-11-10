import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, TextInput, Modal, ScrollView, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Brand, type Category } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { Field, PrimaryButton, adminStyles } from "@/src/components/admin-form";
import { FeaturedBrandsAdmin } from "@/src/components/featured-brands-admin";

const ICONS = ["pricetag-outline", "restaurant-outline", "home-outline", "tv-outline", "shirt-outline", "happy-outline", "construct-outline",
  "car-outline", "brush-outline", "bed-outline", "basket-outline", "gift-outline", "fitness-outline", "school-outline", "paw-outline", "leaf-outline"];

type Edit =
  | { kind: "brand"; item?: Brand; draft?: Draft }
  | { kind: "cat"; item?: Category; parent?: Category; draft?: Draft };
type Draft = { name: string; pic: string; icon: string }; // typed values kept when a confirmation is cancelled
type Ask = { title: string; message: string; label: string; danger: boolean; run: () => Promise<void>; cancel?: () => void };

/** Pick a picture from the gallery and upload it; returns the stored URL. */
async function pickUpload(): Promise<string | null> {
  const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.85, allowsEditing: true, aspect: [1, 1] });
  if (r.canceled || !r.assets[0]) return null;
  const a = r.assets[0];
  return (await api.adminUpload({ uri: a.uri, name: a.fileName ?? a.uri.split("/").pop() ?? "logo.jpg", mimeType: a.mimeType ?? "image/jpeg" })).url;
}

export default function CatalogMaster() {
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<"brand" | "cat" | "featured">("brand");
  const [brands, setBrands] = useState<Brand[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [open, setOpen] = useState<string | null>(null); // expanded main category
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [ask, setAsk] = useState<Ask | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [b, c, main] = await Promise.all([api.brands(), api.allCategories(), api.categoryCounts()]);
      setBrands(b); setCats(c);
      setCounts((x) => ({ ...x, ...Object.fromEntries(main.map((m) => [m.category_id, m.count])) }));
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { // product count of each sub-category of the expanded main category
    if (open) api.categoryCounts(open).then((s) => setCounts((x) => ({ ...x, ...Object.fromEntries(s.map((m) => [m.category_id, m.count])) }))).catch(() => {});
  }, [open]);

  const t = q.trim().toLowerCase();
  const shownBrands = useMemo(() => (t ? brands.filter((b) => b.name.toLowerCase().includes(t)) : brands), [brands, t]);
  const mains = useMemo(() => cats.filter((c) => !c.parent && (!t || c.name.toLowerCase().includes(t) || cats.some((s) => s.parent === c.category_id && s.name.toLowerCase().includes(t)))), [cats, t]);
  const subsOf = (id: string) => cats.filter((c) => c.parent === id);

  const done = async (text: string) => { setMsg({ ok: true, text }); setEdit(null); setAsk(null); await load(); };
  const fail = (e: any) => setMsg({ ok: false, text: e.message });
  // the edit sheet is a Modal too: close it first, then show the confirmation (two stacked Modals don't work on iOS / web)
  const confirmOver = (a: Ask) => { setEdit(null); setTimeout(() => setAsk(a), 350); };
  const confirmRun = async () => {
    if (!ask) return;
    setBusy(true);
    try { await ask.run(); } catch (e) { fail(e); setAsk(null); } finally { setBusy(false); }
  };

  const askDeleteBrand = async (b: Brand) => {
    try {
      const { products } = await api.adminBrandImpact(b.brand_id);
      confirmOver({ title: `Hapus merek “${b.name}”?`, label: "Ya, hapus", danger: true,
        message: products ? `${products.toLocaleString("id-ID")} produk memakai merek ini. Produknya tetap ada, mereknya menjadi “Tanpa merek”.` : "Belum ada produk yang memakai merek ini.",
        run: async () => { const r = await api.adminDeleteBrand(b.brand_id); await done(`Merek dihapus · ${r.products_updated} produk menjadi Tanpa merek`); } });
    } catch (e) { fail(e); }
  };
  const askDeleteCat = async (c: Category) => {
    try {
      const { products, subcategories } = await api.adminCategoryImpact(c.category_id);
      const parts = [subcategories ? `${subcategories} sub-kategori ikut terhapus.` : "", products ? `${products.toLocaleString("id-ID")} produk memakai kategori ini. Produk tanpa kategori lain dipindah ke “Lainnya” (tidak ada produk yang terhapus).` : "Belum ada produk di kategori ini."];
      confirmOver({ title: `Hapus kategori “${c.name}”?`, label: "Ya, hapus", danger: true, message: parts.filter(Boolean).join(" "),
        run: async () => { const r = await api.adminDeleteCategory(c.category_id); await done(`Kategori dihapus · ${r.products_moved} produk pindah ke Lainnya`); } });
    } catch (e) { fail(e); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="catalog-master-screen">
      <ScreenHeader title="Merek & Kategori" />
      <View style={styles.tabs}>
        {([["brand", `Merek (${brands.length})`], ["cat", `Kategori (${cats.filter((c) => !c.parent).length})`], ["featured", "Unggulan"]] as const).map(([k, label]) => (
          <Pressable key={k} testID={`cm-tab-${k}`} onPress={() => { setTab(k); setQ(""); setMsg(null); }} style={[styles.tab, tab === k && styles.tabOn]}>
            <Text style={[styles.tabText, tab === k && styles.tabTextOn]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      {tab === "featured" ? null : (
      <View style={styles.bar}>
        <View style={styles.search}>
          <Icon name="search" size={16} color={colors.muted} />
          <TextInput testID="cm-search" value={q} onChangeText={setQ} placeholder={tab === "brand" ? "Cari merek…" : "Cari kategori…"} placeholderTextColor={colors.muted} style={styles.searchInput} />
        </View>
        <Pressable testID="cm-add" style={styles.addBtn} onPress={() => setEdit(tab === "brand" ? { kind: "brand" } : { kind: "cat" })}>
          <Icon name="add" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.addText}>{tab === "brand" ? "Merek" : "Kategori"}</Text>
        </Pressable>
      </View>
      )}
      {msg ? <Text testID="cm-msg" style={[msg.ok ? adminStyles.ok : adminStyles.err, { paddingHorizontal: spacing.lg }]}>{msg.text}</Text> : null}

      {loading ? <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brandPrimary} /> : tab === "featured" ? <ScrollView keyboardShouldPersistTaps="handled"><FeaturedBrandsAdmin brands={brands} /></ScrollView> : tab === "brand" ? (
        <FlatList data={shownBrands} keyExtractor={(b) => b.brand_id} contentContainerStyle={styles.list}
          ListEmptyComponent={<Text style={styles.empty}>Merek tidak ditemukan</Text>}
          renderItem={({ item }) => (
            <Pressable testID={`cm-brand-${item.name}`} style={styles.row} onPress={() => setEdit({ kind: "brand", item })}>
              {item.logo ? <Image source={{ uri: imgUrl(item.logo) }} style={styles.logo} contentFit="contain" />
                : <View style={[styles.logo, styles.noLogo]}><Text style={styles.initial}>{item.name.slice(0, 1).toUpperCase()}</Text></View>}
              <Text style={styles.rowText} numberOfLines={1}>{item.name}</Text>
              <Text style={adminStyles.muted}>{item.count.toLocaleString("id-ID")} produk</Text>
              <Icon name="chevron-forward" size={16} color={colors.muted} />
            </Pressable>
          )} />
      ) : (
        <FlatList data={mains} keyExtractor={(c) => c.category_id} contentContainerStyle={styles.list}
          ListEmptyComponent={<Text style={styles.empty}>Kategori tidak ditemukan</Text>}
          renderItem={({ item }) => {
            const expanded = open === item.category_id || !!t;
            return (
              <View style={styles.catBox}>
                <View style={styles.row}>
                  <Pressable testID={`cm-cat-toggle-${item.category_id}`} hitSlop={6} onPress={() => setOpen(open === item.category_id ? null : item.category_id)} style={styles.catMain}>
                    <View style={[styles.logo, styles.noLogo]}><Icon name={(item.icon || "pricetag-outline") as any} size={18} color={colors.brandPrimary} /></View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowText} numberOfLines={1}>{item.name}</Text>
                      <Text style={adminStyles.muted}>{(counts[item.category_id] ?? 0).toLocaleString("id-ID")} produk · {subsOf(item.category_id).length} sub-kategori</Text>
                    </View>
                    <Icon name={expanded ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
                  </Pressable>
                  <Pressable testID={`cm-cat-edit-${item.category_id}`} hitSlop={6} style={styles.iconBtn} onPress={() => setEdit({ kind: "cat", item })}>
                    <Icon name="create-outline" size={18} color={colors.brandPrimary} />
                  </Pressable>
                </View>
                {expanded ? (
                  <View style={styles.subs}>
                    {subsOf(item.category_id).filter((s) => !t || s.name.toLowerCase().includes(t) || item.name.toLowerCase().includes(t)).map((s) => (
                      <Pressable key={s.category_id} testID={`cm-sub-${s.category_id}`} style={styles.subRow} onPress={() => setEdit({ kind: "cat", item: s, parent: item })}>
                        <Text style={styles.subText} numberOfLines={1}>{s.name}</Text>
                        <Text style={adminStyles.muted}>{counts[s.category_id] != null ? `${counts[s.category_id].toLocaleString("id-ID")} produk` : ""}</Text>
                        <Icon name="create-outline" size={16} color={colors.muted} />
                      </Pressable>
                    ))}
                    <Pressable testID={`cm-sub-add-${item.category_id}`} style={styles.subRow} onPress={() => setEdit({ kind: "cat", parent: item })}>
                      <Icon name="add-circle-outline" size={18} color={colors.brandPrimary} />
                      <Text style={[styles.subText, { color: colors.brandPrimary }]}>Tambah sub-kategori</Text>
                    </Pressable>
                  </View>
                ) : null}
              </View>
            );
          }} />
      )}

      {edit ? (
        <EditSheet edit={edit} count={edit.kind === "brand" ? edit.item?.count ?? 0 : edit.item ? counts[edit.item.category_id] ?? 0 : 0}
          onClose={() => setEdit(null)} onAsk={confirmOver} onDone={done} onReopen={setEdit}
          onDelete={() => (edit.kind === "brand" ? edit.item && askDeleteBrand(edit.item) : edit.item && askDeleteCat(edit.item))} />
      ) : null}
      <ConfirmDialog visible={!!ask} title={ask?.title ?? ""} message={ask?.message} confirmLabel={ask?.label} danger={ask?.danger} loading={busy}
        onConfirm={confirmRun} onCancel={() => { const c = ask?.cancel; setAsk(null); if (c) setTimeout(c, 350); }} />
    </View>
  );
}

function EditSheet({ edit, count, onClose, onAsk, onDone, onDelete, onReopen }: {
  edit: Edit; count: number; onClose: () => void; onAsk: (a: Ask) => void; onDone: (text: string) => Promise<void>; onDelete: () => void; onReopen: (e: Edit) => void;
}) {
  const insets = useSafeAreaInsets();
  const isBrand = edit.kind === "brand";
  const item = edit.item;
  const parent = edit.kind === "cat" ? edit.parent : undefined;
  const [name, setName] = useState(edit.draft?.name ?? item?.name ?? "");
  const [pic, setPic] = useState(edit.draft?.pic ?? ((isBrand ? (item as Brand | undefined)?.logo : (item as Category | undefined)?.image) ?? ""));
  const [icon, setIcon] = useState(edit.draft?.icon ?? ((!isBrand && (item as Category | undefined)?.icon) || "pricetag-outline"));
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState("");
  const what = isBrand ? "merek" : parent ? "sub-kategori" : "kategori";
  const title = `${item ? "Ubah" : "Tambah"} ${what}${parent ? ` · ${parent.name}` : ""}`;

  const upload = async () => {
    setUploading(true); setErr("");
    try { const u = await pickUpload(); if (u) setPic(u); } catch (e: any) { setErr(e.message); } finally { setUploading(false); }
  };
  const save = async () => {
    const n = name.trim();
    if (!n) { setErr(`Nama ${what} wajib diisi`); return; }
    const run = async () => {
      if (edit.kind === "brand") {
        const r = await api.adminSaveBrand({ name: n, logo: pic }, edit.item?.brand_id);
        await onDone(edit.item ? `Merek disimpan${r.products_updated ? ` · ${r.products_updated} produk ikut diganti` : ""}` : "Merek baru ditambahkan");
      } else {
        await api.adminSaveCategory({ name: n, parent: parent?.category_id ?? null, icon, image: pic }, edit.item?.category_id);
        await onDone(edit.item ? "Kategori disimpan" : `${parent ? "Sub-kategori" : "Kategori"} baru ditambahkan`);
      }
    };
    if (isBrand && item && n !== item.name && count > 0) { // renaming a used brand changes those products: confirm first
      onAsk({ title: "Ganti nama merek?", label: "Ya, ganti", danger: false,
        message: `${count.toLocaleString("id-ID")} produk bermerek “${item.name}” akan ikut menjadi “${n}”. Data produk lainnya tidak berubah.`, run,
        cancel: () => onReopen({ ...edit, draft: { name, pic, icon } }) });
      return;
    }
    setSaving(true); setErr("");
    try { await run(); } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.md }]} testID="cm-edit-sheet">
          <View style={styles.sheetHead}>
            <Text style={styles.sheetTitle}>{title}</Text>
            <Pressable testID="cm-edit-close" hitSlop={8} onPress={onClose}><Icon name="close" size={22} color={colors.onSurface} /></Pressable>
          </View>
          <ScrollView contentContainerStyle={{ gap: spacing.md }} keyboardShouldPersistTaps="handled">
            <Field testID="cm-name" label={`Nama ${what}`} value={name} onChangeText={setName} maxLength={60} placeholder={isBrand ? "Contoh: Advance" : "Contoh: Peralatan Masak"} />
            {item ? <Text style={adminStyles.muted}>{count.toLocaleString("id-ID")} produk memakai {what} ini.{!isBrand ? " Mengganti nama tidak mengubah produknya." : ""}</Text> : null}
            {!isBrand && !parent ? (
              <View style={{ gap: 6 }}>
                <Text style={adminStyles.section}>Ikon di Beranda</Text>
                <View style={styles.icons}>
                  {ICONS.map((i) => (
                    <Pressable key={i} testID={`cm-icon-${i}`} onPress={() => setIcon(i)} style={[styles.iconPick, icon === i && styles.iconPickOn]}>
                      <Icon name={i as any} size={20} color={icon === i ? colors.onBrandPrimary : colors.brandPrimary} />
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}
            <View style={{ gap: 6 }}>
              <Text style={adminStyles.section}>{isBrand ? "Logo merek" : "Gambar kategori (opsional, menggantikan ikon)"}</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <Pressable testID="cm-pic" onPress={upload} style={styles.picBox}>
                  {uploading ? <ActivityIndicator color={colors.brandPrimary} /> : pic ? <Image source={{ uri: imgUrl(pic) }} style={StyleSheet.absoluteFill} contentFit="contain" />
                    : <Icon name="image-outline" size={26} color={colors.muted} />}
                </Pressable>
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={adminStyles.muted}>{isBrand ? "Tampil di filter merek, kartu, dan halaman produk." : "Persegi, JPG/PNG."}</Text>
                  {pic ? <Pressable testID="cm-pic-remove" onPress={() => setPic("")} style={{ minHeight: 32, justifyContent: "center" }}><Text style={{ color: colors.error }}>Hapus gambar</Text></Pressable> : null}
                </View>
              </View>
            </View>
            {err ? <Text testID="cm-err" style={adminStyles.err}>{err}</Text> : null}
            <PrimaryButton testID="cm-save" label="Simpan" loading={saving} onPress={save} />
            {item && !(edit.kind === "cat" && item.category_id === "lainnya") ? (
              <Pressable testID="cm-delete" onPress={onDelete} style={styles.delBtn}>
                <Icon name="trash-outline" size={18} color={colors.error} />
                <Text style={{ color: colors.error, fontWeight: "500" }}>Hapus {what}</Text>
              </Pressable>
            ) : null}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  tabs: { flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  tab: { flex: 1, minHeight: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  tabOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabText: { color: colors.onSurface, fontSize: fontSize.sm },
  tabTextOn: { color: colors.onBrandPrimary, fontWeight: "600" },
  bar: { flexDirection: "row", gap: spacing.sm, padding: spacing.lg, paddingBottom: spacing.sm },
  search: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  searchInput: { flex: 1, minHeight: 44, color: colors.onSurface, fontSize: fontSize.sm },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 44, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  addText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  list: { padding: spacing.lg, paddingTop: spacing.sm, gap: spacing.sm, paddingBottom: 120 },
  empty: { textAlign: "center", color: colors.muted, padding: spacing.xl },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 60, padding: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md },
  rowText: { flex: 1, color: colors.onSurface, fontSize: fontSize.base },
  logo: { width: 40, height: 40, borderRadius: radius.sm },
  noLogo: { backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  initial: { color: colors.brandPrimary, fontWeight: "700" },
  catBox: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden" },
  catMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.md },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  subs: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider, paddingLeft: 64 },
  subRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, paddingRight: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  subText: { flex: 1, color: colors.onSurface, fontSize: fontSize.sm },
  overlay: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.35)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, gap: spacing.md, maxHeight: "90%", width: "100%", maxWidth: 640, alignSelf: "center" },
  sheetHead: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  sheetTitle: { flex: 1, fontSize: fontSize.lg, fontWeight: "600", color: colors.onSurface },
  icons: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  iconPick: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  iconPickOn: { backgroundColor: colors.brandPrimary },
  picBox: { width: 88, height: 88, borderRadius: radius.md, borderWidth: 1, borderStyle: "dashed", borderColor: colors.border, alignItems: "center", justifyContent: "center", overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  delBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 48 },
});
