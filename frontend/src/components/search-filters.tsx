import React, { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Modal, TextInput, Switch, ActivityIndicator } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { useStore } from "@/src/store-context";
import { api, type ProductFacets } from "@/src/api";

export type SearchFilters = { category: string; brands: string[]; min: number | null; max: number | null; in_stock: boolean; wholesale: boolean };
export const NO_FILTERS: SearchFilters = { category: "", brands: [], min: null, max: null, in_stock: false, wholesale: false };

export function activeCount(f: SearchFilters) {
  return (f.category ? 1 : 0) + (f.brands.length ? 1 : 0) + (f.min != null || f.max != null ? 1 : 0) + (f.in_stock ? 1 : 0) + (f.wholesale ? 1 : 0);
}

export function toQuery(q: string, f: SearchFilters) {
  return { q: q || undefined, category: f.category || undefined, brands: f.brands, min_price: f.min, max_price: f.max, in_stock: f.in_stock, wholesale: f.wholesale };
}

const digits = (t: string) => { const n = t.replace(/\D/g, ""); return n ? Math.min(Number(n), 999999999) : null; };
const fmt = (n: number | null) => (n == null ? "" : n.toLocaleString("id-ID"));
const BRANDS_SHOWN = 40;

/** Lembar filter pencarian: kategori, merek, rentang harga, ketersediaan stok cabang & harga grosir. */
export function FilterSheet({ visible, q, value, storeName, onApply, onClose, branch }: {
  visible: boolean; q: string; value: SearchFilters; storeName: string; onApply: (f: SearchFilters) => void; onClose: () => void; branch?: string;
}) {
  const insets = useSafeAreaInsets();
  const [f, setF] = useState(value);
  const [facets, setFacets] = useState<ProductFacets | null>(null);
  const [brandQ, setBrandQ] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (visible) { setF(value); setBrandQ(""); } }, [visible, value]);
  const { storeId } = useStore();
  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    const t = setTimeout(() => api.productFacets({ ...toQuery(q, f), branch }, !!branch).then(setFacets).catch(() => {}).finally(() => setLoading(false)), 300);
    return () => clearTimeout(t);
  }, [visible, q, f, storeId, branch]);

  const set = (p: Partial<SearchFilters>) => setF((x) => ({ ...x, ...p }));
  const brands = useMemo(() => {
    const all = facets?.brands ?? [];
    const t = brandQ.trim().toLowerCase();
    const list = t ? all.filter((b) => b.name.toLowerCase().includes(t)) : all;
    const chosen = f.brands.filter((b) => !list.some((x) => x.name === b)).map((name) => ({ name, count: 0 }));
    return [...chosen, ...list].slice(0, BRANDS_SHOWN + chosen.length);
  }, [facets, brandQ, f.brands]);
  const toggleBrand = (b: string) => set({ brands: f.brands.includes(b) ? f.brands.filter((x) => x !== b) : [...f.brands, b] });
  const badRange = f.min != null && f.max != null && f.min > f.max;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior="padding" style={styles.backdrop}>
        <Pressable style={{ flex: 1 }} onPress={onClose} />
        <View style={[styles.sheet, { paddingBottom: Math.max(spacing.lg, insets.bottom) }]} testID="filter-sheet">
          <View style={styles.head}>
            <Text style={styles.h}>Filter</Text>
            <Pressable testID="filter-reset" hitSlop={8} onPress={() => setF(NO_FILTERS)}><Text style={styles.link}>Reset</Text></Pressable>
            <Pressable testID="filter-close" hitSlop={12} onPress={onClose}><Icon name="close" size={22} color={colors.onSurface} /></Pressable>
          </View>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.md }}>
            <Text style={styles.label}>Kategori</Text>
            <View style={styles.wrap}>
              <Chip label="Semua" on={!f.category} onPress={() => set({ category: "" })} testID="filter-cat-all" />
              {(facets?.categories ?? []).map((c) => (
                <Chip key={c.category_id} label={`${c.name} (${c.count})`} on={f.category === c.category_id} testID={`filter-cat-${c.category_id}`}
                  onPress={() => set({ category: f.category === c.category_id ? "" : c.category_id })} />
              ))}
            </View>

            <Text style={styles.label}>Rentang harga</Text>
            <View style={styles.row}>
              <PriceBox testID="filter-min" placeholder="Minimum" value={fmt(f.min)} onChange={(t) => set({ min: digits(t) })} />
              <Text style={styles.small}>–</Text>
              <PriceBox testID="filter-max" placeholder="Maksimum" value={fmt(f.max)} onChange={(t) => set({ max: digits(t) })} />
            </View>
            {badRange ? <Text style={[styles.small, { color: colors.error }]} testID="filter-range-error">Harga minimum lebih besar dari maksimum</Text>
              : facets && facets.total ? <Text style={styles.small}>Harga di hasil ini: {formatIDR(facets.price_min)} – {formatIDR(facets.price_max)}</Text> : null}

            <Text style={styles.label}>Merek{f.brands.length ? ` (${f.brands.length} dipilih)` : ""}</Text>
            <View style={styles.search}>
              <Icon name="search" size={16} color={colors.muted} />
              <TextInput testID="filter-brand-search" value={brandQ} onChangeText={setBrandQ} placeholder="Cari merek" placeholderTextColor={colors.muted}
                style={{ flex: 1, color: colors.onSurface, paddingVertical: 8 }} />
            </View>
            <View style={styles.wrap}>
              {brands.map((b) => (
                <Chip key={b.name} label={b.count ? `${b.name} (${b.count})` : b.name} on={f.brands.includes(b.name)} onPress={() => toggleBrand(b.name)} testID={`filter-brand-${b.name}`} />
              ))}
              {facets && !brands.length ? <Text style={styles.small}>Tidak ada merek</Text> : null}
            </View>

            <Text style={styles.label}>Lainnya</Text>
            <ToggleRow testID="filter-instock" label={`Tersedia di ${storeName}`} value={f.in_stock} onChange={(v) => set({ in_stock: v })} />
            <ToggleRow testID="filter-wholesale" label="Ada harga grosir" value={f.wholesale} onChange={(v) => set({ wholesale: v })} />
          </ScrollView>
          <Pressable testID="filter-apply" style={[styles.apply, badRange && { opacity: 0.5 }]} disabled={badRange} onPress={() => { onApply(f); onClose(); }}>
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} />
              : <Text style={styles.applyText}>{facets ? `Tampilkan ${facets.total.toLocaleString("id-ID")} produk` : "Terapkan"}</Text>}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

export function Chip({ label, on, onPress, testID }: { label: string; on: boolean; onPress: () => void; testID: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.chip, on && styles.chipOn]}>
      <Text style={[styles.chipText, on && styles.chipTextOn]} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

function PriceBox({ value, onChange, placeholder, testID }: { value: string; onChange: (t: string) => void; placeholder: string; testID: string }) {
  return (
    <View style={[styles.search, { flex: 1 }]}>
      <Text style={styles.small}>Rp</Text>
      <TextInput testID={testID} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.muted}
        keyboardType="number-pad" style={{ flex: 1, color: colors.onSurface, paddingVertical: 8 }} />
    </View>
  );
}

function ToggleRow({ label, value, onChange, testID }: { label: string; value: boolean; onChange: (v: boolean) => void; testID: string }) {
  return (
    <Pressable style={styles.toggle} onPress={() => onChange(!value)}>
      <Text style={[styles.chipText, { flex: 1 }]}>{label}</Text>
      <Switch testID={testID} value={value} onValueChange={onChange} trackColor={{ true: colors.brandPrimary, false: colors.border }} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, maxHeight: "88%" },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.lg, minHeight: 44 },
  h: { flex: 1, fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  link: { color: colors.brandPrimary, fontWeight: "600" },
  label: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  small: { fontSize: 12, color: colors.onSurfaceSecondary },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.xs, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, minHeight: 44 },
  chip: { minHeight: 44, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center", maxWidth: 240 },
  chipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextOn: { color: colors.onBrandPrimary, fontWeight: "600" },
  toggle: { flexDirection: "row", alignItems: "center", minHeight: 48 },
  apply: { minHeight: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  applyText: { color: colors.onBrandPrimary, fontWeight: "700" },
});
