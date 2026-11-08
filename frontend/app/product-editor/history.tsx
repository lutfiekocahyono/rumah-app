import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, TextInput, ActivityIndicator, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type EditorContext, type PriceLog } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { SellerShell } from "@/src/components/seller-shell";
import { Pill } from "@/src/components/product-editor/ui";
import { fmtDate } from "@/src/utils/date";
import { downloadAuthed } from "@/src/utils/download";

const KINDS = [{ id: "", label: "Semua" }, { id: "price", label: "Harga" }, { id: "stock", label: "Stok" }];

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
/** First..last day of this month (0) or last month (-1). */
function monthRange(offset: 0 | -1) {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const last = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
  return { from: ymd(first), to: ymd(last), preset: offset === 0 ? "this" : "last" };
}

const val = (c: PriceLog["changes"][number], v: number | string | null) =>
  v === null ? "—" : typeof v === "string" ? v : c.kind === "price" ? formatIDR(v) : v >= 9999 ? "∞" : v.toLocaleString("id-ID");

function LogCard({ log, showStore, onProduct }: { log: PriceLog; showStore: boolean; onProduct: () => void }) {
  return (
    <View style={styles.card} testID={`ph-log-${log.log_id}`}>
      <Pressable onPress={onProduct} testID={`ph-product-${log.product_id}`} hitSlop={4}>
        <Text style={[styles.name, { color: colors.brandPrimary }]} numberOfLines={2}>{log.product_name}</Text>
      </Pressable>
      <Text style={styles.muted}>
        {fmtDate(log.at)} · oleh <Text style={styles.who}>{log.user_name}</Text> · {log.source_label}{showStore ? ` · ${log.store_name}` : ""}
      </Text>
      {log.changes.map((c, i) => {
        const up = typeof c.before === "number" && typeof c.after === "number" ? c.after > c.before : null;
        return (
          <View key={i} style={styles.change} testID="ph-change">
            <Text style={styles.label}>{c.label}{c.variant ? ` · ${c.variant}` : ""}</Text>
            <View style={styles.vals}>
              <Text style={styles.before}>{val(c, c.before)}</Text>
              <Icon name="arrow-forward" size={14} color={colors.muted} />
              <Text style={[styles.after, up === true && { color: colors.success }, up === false && { color: colors.error }]}>{val(c, c.after)}</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

export default function PriceHistory() {
  const { product } = useLocalSearchParams<{ product?: string }>();
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [ctx, setCtx] = useState<EditorContext | null>(null);
  const [storeId, setStoreId] = useState<string>(""); // admin: "" = semua toko
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [items, setItems] = useState<PriceLog[] | null>(null);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState("");
  const [range, setRange] = useState(() => monthRange(0));
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const busy = useRef(false);
  const validDate = (s: string) => !s || /^\d{4}-\d{2}-\d{2}$/.test(s);
  const rangeOk = validDate(range.from) && validDate(range.to) && !(range.from && range.to && range.from > range.to);
  const dates = rangeOk ? { date_from: range.from, date_to: range.to } : { date_from: "", date_to: "" };

  useEffect(() => { api.editorContext().then(setCtx).catch(() => {}); }, []);

  const load = useCallback(async (reset: boolean, from = 0) => {
    if (busy.current && !reset) return;
    busy.current = true;
    try {
      const r = await api.priceHistory({ store_id: admin ? storeId || null : null, product_id: product ?? null, q, kind, ...dates, skip: from });
      setErr("");
      setTotal(r.total);
      setItems((cur) => (reset ? r.items : [...(cur ?? []), ...r.items]));
    } catch (e: any) { setErr(e.message); setItems((c) => c ?? []); } finally { busy.current = false; }
  }, [admin, storeId, product, q, kind, dates.date_from, dates.date_to]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { const t = setTimeout(() => void load(true), 300); return () => clearTimeout(t); }, [load]);

  const exportXlsx = async () => {
    setExporting(true);
    setExportMsg(null);
    try {
      const sid = admin ? storeId || null : null;
      await downloadAuthed(api.priceHistoryExportUrl({ store_id: sid, product_id: product ?? null, q, kind, ...dates }),
        `riwayat-harga-stok-${sid ?? (admin ? "semua-toko" : "toko")}-${dates.date_from || "awal"}-sd-${dates.date_to || "sekarang"}.xlsx`);
      setExportMsg({ ok: true, text: "File Excel riwayat berhasil dibuat" });
    } catch (e: any) { setExportMsg({ ok: false, text: e.message }); } finally { setExporting(false); }
  };
  const preset = range.preset;

  const header = (
    <View style={styles.top}>
      <Text style={styles.muted}>
        {admin ? "Super Admin: semua toko & cabang." : "Hanya perubahan di toko Anda."} Mencatat perubahan manual harga & stok (Ubah Produk, Edit Massal, Impor Excel, Manajemen Stok, Harga Grosir).
      </Text>
      {product ? (
        <Pressable testID="ph-clear-product" style={styles.chip} onPress={() => router.setParams({ product: undefined } as any)}>
          <Text style={styles.chipText}>Hanya 1 produk · tampilkan semua</Text>
          <Icon name="close" size={14} color={colors.brandPrimary} />
        </Pressable>
      ) : null}
      {admin && ctx ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          <Pill testID="ph-store-all" label="Semua toko" on={!storeId} onPress={() => setStoreId("")} />
          {ctx.stores.map((s) => <Pill key={s.store_id} testID={`ph-store-${s.store_id}`} label={s.name} on={storeId === s.store_id} onPress={() => setStoreId(s.store_id)} />)}
        </ScrollView>
      ) : null}
      {!product ? (
        <View style={styles.search}>
          <Icon name="search" size={16} color={colors.muted} />
          <TextInput testID="ph-search" value={q} onChangeText={setQ} placeholder="Cari nama produk" placeholderTextColor={colors.muted} style={styles.searchInput} />
        </View>
      ) : null}
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        {KINDS.map((k) => <Pill key={k.id} testID={`ph-kind-${k.id || "all"}`} label={k.label} on={kind === k.id} onPress={() => setKind(k.id)} />)}
      </View>
      <View style={styles.period} testID="ph-period">
        <Text style={styles.periodTitle}>Periode laporan</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          <Pill testID="ph-range-this" label="Bulan ini" on={preset === "this"} onPress={() => setRange(monthRange(0))} />
          <Pill testID="ph-range-last" label="Bulan lalu" on={preset === "last"} onPress={() => setRange(monthRange(-1))} />
          <Pill testID="ph-range-all" label="Semua" on={preset === "all"} onPress={() => setRange({ from: "", to: "", preset: "all" })} />
        </View>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <TextInput testID="ph-date-from" value={range.from} onChangeText={(t) => setRange((r) => ({ ...r, from: t.trim(), preset: "" }))} placeholder="Dari (TTTT-BB-HH)"
            placeholderTextColor={colors.muted} style={[styles.dateInput, !validDate(range.from) && { borderColor: colors.error }]} maxLength={10} />
          <TextInput testID="ph-date-to" value={range.to} onChangeText={(t) => setRange((r) => ({ ...r, to: t.trim(), preset: "" }))} placeholder="Sampai (TTTT-BB-HH)"
            placeholderTextColor={colors.muted} style={[styles.dateInput, !validDate(range.to) && { borderColor: colors.error }]} maxLength={10} />
        </View>
        <Pressable testID="ph-export" style={[styles.exportBtn, !rangeOk && { opacity: 0.5 }]} onPress={exportXlsx} disabled={exporting || !rangeOk}>
          {exporting ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : <Icon name="download-outline" size={18} color={colors.onBrandPrimary} />}
          <Text style={styles.exportText}>Unduh Excel{admin && !storeId ? " (semua toko)" : ""}</Text>
        </Pressable>
        {!rangeOk ? <Text style={[styles.muted, { color: colors.error }]} testID="ph-range-error">Periode tidak valid: isi tanggal TTTT-BB-HH dan tanggal awal sebelum tanggal akhir.</Text>
          : exportMsg ? <Text style={[styles.muted, { color: exportMsg.ok ? colors.success : colors.error }]} testID={exportMsg.ok ? "ph-export-ok" : "ph-export-error"}>{exportMsg.text}</Text> : null}
      </View>
      {err ? <Text style={[styles.muted, { color: colors.error }]} testID="ph-error">{err}</Text> : <Text style={styles.muted}>{total.toLocaleString("id-ID")} catatan</Text>}
    </View>
  );

  return (
    <SellerShell admin={admin} title="Riwayat Harga & Stok">
      <View style={{ flex: 1 }} testID="price-history-screen">
        {items === null ? <View style={{ padding: spacing.lg }}>{header}<ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /></View> : (
          <FlatList
            data={items}
            keyExtractor={(l) => l.log_id}
            ListHeaderComponent={header}
            contentContainerStyle={{ padding: spacing.lg, paddingTop: 0, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
            keyboardShouldPersistTaps="handled"
            onEndReached={() => { if (items.length < total) void load(false, items.length); }}
            onEndReachedThreshold={0.5}
            ListEmptyComponent={err ? undefined : <Text style={[styles.muted, { textAlign: "center", marginTop: spacing.xl }]} testID="ph-empty">Belum ada perubahan harga atau stok yang tercatat.</Text>}
            renderItem={({ item }) => <LogCard log={item} showStore={admin} onProduct={() => router.setParams({ product: item.product_id } as any)} />}
          />
        )}
      </View>
    </SellerShell>
  );
}

const styles = StyleSheet.create({
  top: { paddingVertical: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 1240, alignSelf: "center" },
  period: { gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  periodTitle: { fontSize: fontSize.sm, fontWeight: "700", color: colors.onSurface },
  dateInput: { flex: 1, flexBasis: 0, minWidth: 0, minHeight: 44, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, color: colors.onSurface, backgroundColor: colors.surface },
  exportBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md },
  exportText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  muted: { fontSize: 12, color: colors.muted },
  who: { color: colors.onSurface, fontWeight: "600" },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  searchInput: { flex: 1, paddingVertical: 10, minHeight: 44, color: colors.onSurface },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 36 },
  chipText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "600" },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 6, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, width: "100%", maxWidth: 1208, alignSelf: "center" },
  name: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "600" },
  change: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, paddingTop: 6, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  label: { fontSize: 13, color: colors.onSurfaceSecondary, flexShrink: 1 },
  vals: { flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1 },
  before: { fontSize: 13, color: colors.muted, textDecorationLine: "line-through" },
  after: { fontSize: 13, color: colors.onSurface, fontWeight: "700" },
});
