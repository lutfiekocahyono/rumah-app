import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import type { ProductForm } from "@/src/api";
import { Input, Section, digitsOf, rupiah, ui } from "./ui";
import { checklist, type Errors } from "./form";

export function PriceStock({ form, set, errors }: { form: ProductForm; set: (p: Partial<ProductForm>) => void; errors: Errors }) {
  const pct = form.price && form.discount_price && form.discount_price < form.price ? Math.round(((form.price - form.discount_price) / form.price) * 100) : 0;
  const active = form.variants.filter((r) => r.active);
  const total = form.variants_enabled ? active.reduce((t, r) => t + r.stock, 0) : form.stock;
  const low = form.low_stock_alert > 0 && total <= form.low_stock_alert;
  const prices = active.map((r) => r.price).filter(Boolean);
  return (
    <Section title="Harga & Stok" icon="pricetag-outline" testID="pe-price">
      {form.variants_enabled ? (
        <View style={styles.info} testID="pe-price-variant-note">
          <Icon name="information-circle-outline" size={18} color={colors.brandPrimary} />
          <Text style={[ui.hint, { flex: 1 }]}>
            Harga dan stok diatur per variasi di tabel variasi.{prices.length ? ` Harga ${formatIDR(Math.min(...prices))}${Math.max(...prices) > Math.min(...prices) ? ` – ${formatIDR(Math.max(...prices))}` : ""}.` : ""} Total stok {total}.
          </Text>
        </View>
      ) : (
        <>
          <View style={ui.row}>
            <Input testID="pe-price-normal" label="Harga normal" required prefix="Rp" keyboardType="number-pad" value={rupiah(form.price)}
              onChangeText={(t) => set({ price: digitsOf(t) })} error={errors.price} placeholder="0" />
            <Input testID="pe-price-discount" label="Harga diskon" prefix="Rp" keyboardType="number-pad" value={rupiah(form.discount_price)}
              onChangeText={(t) => set({ discount_price: digitsOf(t) })} error={errors.discount_price} placeholder="Kosongkan jika tidak diskon" />
          </View>
          {pct ? <Text style={styles.pct} testID="pe-discount-pct">Diskon {pct}% · pembeli hemat {formatIDR(form.price - form.discount_price)}</Text> : null}
          <Input testID="pe-stock" label="Jumlah stok" required keyboardType="number-pad" value={String(form.stock)}
            onChangeText={(t) => set({ stock: Math.min(999999, digitsOf(t)) })} error={errors.stock} />
        </>
      )}
      <View style={ui.row}>
        <Input testID="pe-min-order" label="Minimum pembelian" keyboardType="number-pad" value={String(form.min_order || "")}
          onChangeText={(t) => set({ min_order: Math.min(9999, digitsOf(t)) })} error={errors.min_order} />
        <Input testID="pe-max-order" label="Maksimum pembelian" keyboardType="number-pad" value={form.max_order ? String(form.max_order) : ""}
          onChangeText={(t) => set({ max_order: Math.min(9999, digitsOf(t)) })} error={errors.max_order} placeholder="Tanpa batas" />
        <Input testID="pe-low-stock" label="Peringatan stok menipis" keyboardType="number-pad" value={form.low_stock_alert ? String(form.low_stock_alert) : ""}
          onChangeText={(t) => set({ low_stock_alert: Math.min(99999, digitsOf(t)) })} placeholder="Mis. 5" hint="Beri tanda bila stok ≤ angka ini" />
      </View>
      {low ? (
        <View style={[styles.info, { backgroundColor: colors.brandTertiary }]} testID="pe-low-stock-warning">
          <Icon name="warning-outline" size={18} color={colors.warning} />
          <Text style={[ui.hint, { flex: 1, color: colors.onSurface }]}>Stok menipis: {total} tersisa (batas peringatan {form.low_stock_alert}).</Text>
        </View>
      ) : null}
    </Section>
  );
}

/** Completeness indicator: progress bar + checklist. */
export function Completeness({ form }: { form: ProductForm }) {
  const items = checklist(form);
  const pct = Math.round((items.filter((i) => i.done).length / items.length) * 100);
  const requiredLeft = items.filter((i) => i.required && !i.done).length;
  return (
    <View style={[ui.card, { gap: spacing.sm }]} testID="pe-completeness">
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Text style={[ui.title, { flex: 1 }]}>Kelengkapan produk</Text>
        <Text style={styles.pctBig} testID="pe-completeness-pct">{pct}%</Text>
      </View>
      <View style={styles.bar}><View style={[styles.fill, { width: `${pct}%` }, requiredLeft === 0 && { backgroundColor: colors.success }]} /></View>
      <Text style={ui.hint}>{requiredLeft ? `${requiredLeft} data wajib belum lengkap` : "Data wajib lengkap — siap dipublikasikan"}</Text>
      <View style={{ gap: 4 }}>
        {items.map((i) => (
          <View key={i.label} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Icon name={i.done ? "checkmark-circle" : "ellipse-outline"} size={16} color={i.done ? colors.success : i.required ? colors.error : colors.muted} />
            <Text style={[styles.item, i.done && { color: colors.muted }]}>{i.label}{i.required ? "" : " (disarankan)"}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  info: { flexDirection: "row", gap: spacing.sm, alignItems: "center", padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  pct: { color: colors.success, fontSize: fontSize.sm, fontWeight: "600" },
  pctBig: { fontSize: fontSize.lg, fontWeight: "700", color: colors.brandPrimary },
  bar: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  fill: { height: 8, backgroundColor: colors.brandPrimary },
  item: { fontSize: 13, color: colors.onSurface },
});
