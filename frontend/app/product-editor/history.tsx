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

const KINDS = [{ id: "", label: "Semua" }, { id: "price", label: "Harga" }, { id: "stock", label: "Stok" }];

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
  const busy = useRef(false);

  useEffect(() => { api.editorContext().then(setCtx).catch(() => {}); }, []);

  const load = useCallback(async (reset: boolean, from = 0) => {
    if (busy.current && !reset) return;
    busy.current = true;
    try {
      const r = await api.priceHistory({ store_id: admin ? storeId || null : null, product_id: product ?? null, q, kind, skip: from });
      setErr("");
      setTotal(r.total);
      setItems((cur) => (reset ? r.items : [...(cur ?? []), ...r.items]));
    } catch (e: any) { setErr(e.message); setItems((c) => c ?? []); } finally { busy.current = false; }
  }, [admin, storeId, product, q, kind]);

  useEffect(() => { const t = setTimeout(() => void load(true), 300); return () => clearTimeout(t); }, [load]);

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
            ListEmptyComponent={err ? null : <Text style={[styles.muted, { textAlign: "center", marginTop: spacing.xl }]} testID="ph-empty">Belum ada perubahan harga atau stok yang tercatat.</Text>}
            renderItem={({ item }) => <LogCard log={item} showStore={admin} onProduct={() => router.setParams({ product: item.product_id } as any)} />}
          />
        )}
      </View>
    </SellerShell>
  );
}

const styles = StyleSheet.create({
  top: { paddingVertical: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 1240, alignSelf: "center" },
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
