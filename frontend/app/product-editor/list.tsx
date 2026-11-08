import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, TextInput, ActivityIndicator, ScrollView } from "react-native";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, imgUrl, type EditorContext, type EditorListItem } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { SellerShell } from "@/src/components/seller-shell";
import { Pill } from "@/src/components/product-editor/ui";
import { BulkDialog, type BulkKind } from "@/src/components/product-editor/bulk-dialog";
import { ImportDialog } from "@/src/components/product-editor/import-dialog";
import { downloadAuthed } from "@/src/utils/download";

const FILTERS = [{ id: "", label: "Semua" }, { id: "active", label: "Aktif" }, { id: "inactive", label: "Nonaktif" }, { id: "empty", label: "Stok habis" }];

function Row({ p, on, toggle, onEdit, onDuplicate, dup }: { p: EditorListItem; on: boolean; toggle: () => void; onEdit: () => void; onDuplicate: () => void; dup: boolean }) {
  return (
    <View style={[styles.row, on && styles.rowOn]} testID={`pl-row-${p.product_id}`}>
      <Pressable testID={`pl-check-${p.product_id}`} hitSlop={8} onPress={toggle} style={styles.check}>
        <Icon name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.brandPrimary : colors.muted} />
      </Pressable>
      <Image source={imgUrl(p.image)} style={styles.img} contentFit="cover" />
      <Pressable style={{ flex: 1, gap: 2 }} onPress={onEdit}>
        <Text style={styles.name} numberOfLines={2}>{p.name}</Text>
        <Text style={styles.muted} numberOfLines={1}>{p.sku ? `SKU ${p.sku} · ` : ""}{p.variants ? `${p.variants} variasi` : "Tanpa variasi"}</Text>
        <View style={styles.meta}>
          <Text style={styles.price}>{p.variants ? "mulai " : ""}{formatIDR(p.price)}</Text>
          {p.original_price > p.price ? <Text style={styles.strike}>{formatIDR(p.original_price)}</Text> : null}
          <Text style={[styles.muted, !p.stock && { color: colors.error }]}>· {p.stock ? `Stok ${p.stock}` : "Stok habis"}</Text>
          {p.status === "inactive" ? <Text style={styles.badge} testID={`pl-inactive-${p.product_id}`}>Nonaktif</Text> : null}
        </View>
      </Pressable>
      <Pressable testID={`pl-duplicate-${p.product_id}`} style={styles.iconBtn} onPress={onDuplicate} disabled={dup} accessibilityLabel="Duplikat produk">
        {dup ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="copy-outline" size={20} color={colors.brandPrimary} />}
      </Pressable>
      <Pressable testID={`pl-edit-${p.product_id}`} style={styles.iconBtn} onPress={onEdit} accessibilityLabel="Ubah produk">
        <Icon name="create-outline" size={20} color={colors.onSurfaceSecondary} />
      </Pressable>
    </View>
  );
}

export default function ProductList() {
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [ctx, setCtx] = useState<EditorContext | null>(null);
  const [storeId, setStoreId] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [items, setItems] = useState<EditorListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<BulkKind | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [dup, setDup] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const busy = useRef(false);

  useEffect(() => { api.editorContext().then((c) => { setCtx(c); setStoreId((c.stores.find((s) => s.store_id === "pgs-official") ?? c.stores[0])?.store_id ?? null); }).catch((e) => setMsg({ ok: false, text: e.message })); }, []);

  const load = useCallback(async (reset: boolean, from = 0) => {
    if (!storeId || (busy.current && !reset)) return;
    busy.current = true;
    try {
      const r = await api.editorList({ store_id: admin ? storeId : null, q, status: filter, skip: from });
      setTotal(r.total);
      setItems((cur) => (reset ? r.items : [...(cur ?? []), ...r.items.filter((p) => !(cur ?? []).some((c) => c.product_id === p.product_id))]));
    } catch (e: any) { setMsg({ ok: false, text: e.message }); setItems((c) => c ?? []); } finally { busy.current = false; }
  }, [storeId, q, filter, admin]);

  useEffect(() => {
    if (!storeId) return;
    const t = setTimeout(() => { setSel(new Set()); void load(true); }, 300);
    return () => clearTimeout(t);
  }, [load, storeId]);
  const first = useRef(true);
  useFocusEffect(useCallback(() => { if (first.current) { first.current = false; return; } void load(true); }, [load]));

  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const allOn = !!items?.length && items.every((p) => sel.has(p.product_id));
  const toggleAll = () => setSel(allOn ? new Set() : new Set(items?.map((p) => p.product_id)));
  const storeName = ctx?.stores.find((s) => s.store_id === storeId)?.name ?? "";

  const duplicate = async (id: string) => {
    setDup(id);
    try { const d = await api.editorDuplicate(id); router.push(`/product-editor/new?draft=${d.draft_id}` as any); }
    catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setDup(""); }
  };
  const exportXlsx = async () => {
    setExporting(true);
    setMsg(null);
    try {
      await downloadAuthed(api.editorExportUrl(admin ? storeId : null), `produk-${storeId}.xlsx`);
      setMsg({ ok: true, text: "File Excel berhasil dibuat" });
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setExporting(false); }
  };

  const header = (
        <View style={styles.top}>
          {admin && ctx && ctx.stores.length > 1 ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
              {ctx.stores.map((s) => <Pill key={s.store_id} testID={`pl-store-${s.store_id}`} label={s.name} on={storeId === s.store_id} onPress={() => setStoreId(s.store_id)} />)}
            </ScrollView>
          ) : null}
          <View style={styles.actions}>
            <Pressable testID="pl-add" style={styles.primary} onPress={() => router.push("/product-editor/new" as any)}>
              <Icon name="add" size={18} color={colors.onBrandPrimary} /><Text style={styles.primaryText}>Tambah Produk</Text>
            </Pressable>
            <Pressable testID="pl-export" style={styles.outline} onPress={exportXlsx} disabled={exporting}>
              {exporting ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="download-outline" size={18} color={colors.brandPrimary} />}
              <Text style={styles.outlineText}>Ekspor Excel</Text>
            </Pressable>
            <Pressable testID="pl-import" style={styles.outline} onPress={() => setImporting(true)}>
              <Icon name="cloud-upload-outline" size={18} color={colors.brandPrimary} /><Text style={styles.outlineText}>Impor Excel</Text>
            </Pressable>
          </View>
          <View style={styles.search}>
            <Icon name="search" size={16} color={colors.muted} />
            <TextInput testID="pl-search" value={q} onChangeText={setQ} placeholder="Cari nama atau SKU" placeholderTextColor={colors.muted} style={styles.searchInput} />
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {FILTERS.map((f) => <Pill key={f.id} testID={`pl-filter-${f.id || "all"}`} label={f.label} on={filter === f.id} onPress={() => setFilter(f.id)} />)}
          </ScrollView>
          {msg ? <Text style={[styles.muted, { color: msg.ok ? colors.success : colors.error }]} testID={msg.ok ? "pl-msg-ok" : "pl-msg-error"}>{msg.text}</Text> : null}
          <Pressable testID="pl-select-all" style={styles.selAll} onPress={toggleAll} disabled={!items?.length}>
            <Icon name={allOn ? "checkbox" : "square-outline"} size={20} color={allOn ? colors.brandPrimary : colors.muted} />
            <Text style={styles.muted}>Pilih semua yang tampil · {total.toLocaleString("id-ID")} produk</Text>
          </Pressable>
        </View>
  );

  return (
    <SellerShell admin={admin} title="Daftar Produk">
      <View style={{ flex: 1 }} testID="product-list-screen">
        {items === null ? <View style={{ padding: spacing.lg }}>{header}<ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /></View> : (
          <FlatList
            data={items}
            ListHeaderComponent={header}
            keyExtractor={(p) => p.product_id}
            contentContainerStyle={{ padding: spacing.lg, paddingTop: 0, gap: spacing.sm, paddingBottom: insets.bottom + (sel.size ? 140 : spacing.xl) }}
            keyboardShouldPersistTaps="handled"
            onEndReached={() => { if (items.length < total) void load(false, items.length); }}
            onEndReachedThreshold={0.5}
            ListEmptyComponent={<Text style={[styles.muted, { textAlign: "center", marginTop: spacing.xl }]} testID="pl-empty">Belum ada produk. Tambah produk atau impor dari Excel.</Text>}
            renderItem={({ item }) => (
              <Row p={item} on={sel.has(item.product_id)} toggle={() => toggle(item.product_id)} dup={dup === item.product_id}
                onEdit={() => router.push(`/product-editor/${item.product_id}` as any)} onDuplicate={() => duplicate(item.product_id)} />
            )}
          />
        )}
        {sel.size ? (
          <View style={[styles.bar, { paddingBottom: Math.max(spacing.md, insets.bottom) }]} testID="pl-bulk-bar">
            <View style={styles.barHead}>
              <Text style={styles.barTitle} testID="pl-selected-count">{sel.size} produk dipilih</Text>
              <Pressable testID="pl-clear" hitSlop={8} onPress={() => setSel(new Set())}><Text style={styles.outlineText}>Batal pilih</Text></Pressable>
            </View>
            <View style={styles.actions}>
              <Pressable testID="pl-bulk-price" style={styles.outline} onPress={() => setBulk("price")}><Icon name="pricetag-outline" size={16} color={colors.brandPrimary} /><Text style={styles.outlineText}>Ubah Harga</Text></Pressable>
              <Pressable testID="pl-bulk-stock" style={styles.outline} onPress={() => setBulk("stock")}><Icon name="layers-outline" size={16} color={colors.brandPrimary} /><Text style={styles.outlineText}>Ubah Stok</Text></Pressable>
              <Pressable testID="pl-bulk-status" style={styles.outline} onPress={() => setBulk("status")}><Icon name="eye-outline" size={16} color={colors.brandPrimary} /><Text style={styles.outlineText}>Status</Text></Pressable>
            </View>
          </View>
        ) : null}
      </View>
      <BulkDialog kind={bulk} ids={[...sel]} storeId={admin ? storeId : null} onClose={() => setBulk(null)} onDone={() => void load(true)} />
      <ImportDialog visible={importing} storeId={admin ? storeId : null} storeName={storeName} onClose={() => setImporting(false)} onDone={() => void load(true)} />
    </SellerShell>
  );
}

const styles = StyleSheet.create({
  top: { paddingVertical: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 1240, alignSelf: "center" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  primary: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 44 },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  outline: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 44, backgroundColor: colors.surface },
  outlineText: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  searchInput: { flex: 1, paddingVertical: 10, minHeight: 44, color: colors.onSurface },
  selAll: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 36 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, width: "100%", maxWidth: 1208, alignSelf: "center" },
  rowOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  check: { width: 36, height: 44, alignItems: "center", justifyContent: "center" },
  img: { width: 56, height: 56, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  muted: { fontSize: 12, color: colors.muted },
  meta: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 6 },
  price: { fontSize: fontSize.sm, color: colors.brandPrimary, fontWeight: "700" },
  strike: { fontSize: 12, color: colors.muted, textDecorationLine: "line-through" },
  badge: { fontSize: 11, color: colors.error, borderWidth: 1, borderColor: colors.error, borderRadius: radius.pill, paddingHorizontal: 6 },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  bar: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: spacing.sm },
  barHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  barTitle: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
});
