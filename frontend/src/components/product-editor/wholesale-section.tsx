import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { CUSTOMER_TYPE_LABEL, type CustomerType, type PriceTier, type ProductForm } from "@/src/api";
import { FieldError, Input, Pill, Section, digitsOf, rupiah, ui } from "./ui";
import type { Errors } from "./form";

const TYPES: CustomerType[] = ["langsung", "pengecer", "reseller"];
const MAX = 10;

/** Range label "1–5", "6–11", "12+" for each tier of a table. */
const rangeOf = (q: number, all: number[]) => {
  const next = all.filter((x) => x > q).sort((a, b) => a - b)[0];
  return next ? (next - 1 > q ? `${q}–${next - 1}` : `${q}`) : `${q}+`;
};

/** Harga grosir: rupiah per tingkat jumlah beli, per kategori pelanggan (Pembeli Langsung, Pengecer, Reseller). */
export function WholesaleSection({ form, set, errors }: { form: ProductForm; set: (p: Partial<ProductForm>) => void; errors: Errors }) {
  const [type, setType] = useState<CustomerType>("langsung");
  const base = form.discount_price || form.price;
  const rows = form.tier_prices[type] ?? [];
  const setRows = (r: PriceTier[]) => {
    const next = { ...form.tier_prices };
    if (r.length) next[type] = r; else delete next[type];
    set({ tier_prices: next });
  };
  const qtys = rows.map((r) => r.min_qty).filter((q) => q > 0);
  const implicit = type === "langsung" && !qtys.includes(1); // first tier = harga jual from Harga & Stok
  const allQ = implicit ? [1, ...qtys] : qtys;
  const add = () => {
    const last = Math.max(0, ...allQ);
    const lastPrice = rows.length ? rows[rows.length - 1].price : base;
    setRows([...rows, { min_qty: last ? (last < 6 ? 6 : last * 2) : 1, price: lastPrice }]);
  };

  if (form.variants_enabled) {
    return (
      <Section title="Harga Grosir" icon="layers-outline" testID="pe-wholesale" subtitle="Harga bertingkat per jumlah beli">
        <Text style={ui.hint} testID="pe-wholesale-variant-note">Produk bervariasi memakai harga per variasi. Harga grosir hanya untuk produk tanpa variasi.</Text>
      </Section>
    );
  }
  return (
    <Section title="Harga Grosir" icon="layers-outline" testID="pe-wholesale"
      subtitle="Harga Rupiah per pcs untuk tiap tingkat jumlah beli. Kosongkan jika produk tidak punya harga grosir.">
      <View style={ui.row}>
        {TYPES.map((t) => (
          <Pill key={t} testID={`pe-tier-type-${t}`} label={`${CUSTOMER_TYPE_LABEL[t]}${form.tier_prices[t]?.length ? ` (${form.tier_prices[t]!.length})` : ""}`}
            on={type === t} onPress={() => setType(t)} />
        ))}
      </View>
      {!rows.length && type !== "langsung" ? (
        <View style={styles.note} testID="pe-tier-fallback">
          <Icon name="information-circle-outline" size={18} color={colors.brandPrimary} />
          <Text style={[ui.hint, { flex: 1 }]}>{CUSTOMER_TYPE_LABEL[type]} belum punya tabel sendiri, jadi memakai harga Pembeli Langsung.</Text>
          {form.tier_prices.langsung?.length ? (
            <Pressable testID="pe-tier-copy" onPress={() => setRows([{ min_qty: 1, price: base }, ...(form.tier_prices.langsung ?? []).filter((r) => r.min_qty > 1)])}>
              <Text style={styles.link}>Salin dari Pembeli Langsung</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {implicit ? (
        <View style={styles.row} testID="pe-tier-implicit">
          <Text style={styles.range}>Beli {rangeOf(1, allQ)}</Text>
          <Text style={[ui.hint, { flex: 1 }]}>{base ? formatIDR(base) : "Rp –"} / pcs · harga jual di Harga & Stok</Text>
        </View>
      ) : null}
      {rows.map((r, i) => (
        <View key={i} style={styles.tier} testID={`pe-tier-row-${i}`}>
          <Text style={styles.rangeTop} testID={`pe-tier-range-${i}`}>Beli {r.min_qty ? rangeOf(r.min_qty, allQ) : "…"}</Text>
          <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
            <View style={{ flex: 2 }}>
              <Input compact testID={`pe-tier-qty-${i}`} label="Mulai (pcs)" keyboardType="number-pad" value={r.min_qty ? String(r.min_qty) : ""}
                onChangeText={(t) => setRows(rows.map((x, j) => (j === i ? { ...x, min_qty: Math.min(99999, digitsOf(t)) } : x)))} />
            </View>
            <View style={{ flex: 3 }}>
              <Input compact testID={`pe-tier-price-${i}`} label="Harga / pcs" prefix="Rp" keyboardType="number-pad" value={rupiah(r.price)}
                onChangeText={(t) => setRows(rows.map((x, j) => (j === i ? { ...x, price: digitsOf(t) } : x)))} />
            </View>
            <Pressable testID={`pe-tier-del-${i}`} style={styles.del} onPress={() => setRows(rows.filter((_, j) => j !== i))} accessibilityLabel="Hapus tingkat">
              <Icon name="trash-outline" size={18} color={colors.error} />
            </Pressable>
          </View>
        </View>
      ))}
      <FieldError msg={errors[`tiers.${type}`]} testID="pe-tier-error" />
      {TYPES.filter((t) => t !== type && errors[`tiers.${t}`]).map((t) => <FieldError key={t} msg={errors[`tiers.${t}`]} />)}
      {rows.length < MAX ? (
        <Pressable testID="pe-tier-add" style={styles.add} onPress={add}>
          <Icon name="add" size={18} color={colors.brandPrimary} />
          <Text style={styles.link}>Tambah tingkat harga</Text>
        </Pressable>
      ) : null}
      <Text style={ui.hint}>Contoh: beli 1–5 = Rp50.000, beli 6–11 = Rp48.000, beli 12+ = Rp45.000. Tabel ini tampil di detail produk.</Text>
    </Section>
  );
}

const styles = StyleSheet.create({
  note: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "flex-end", gap: spacing.sm, paddingVertical: 4 },
  range: { width: 90, fontSize: fontSize.sm, fontWeight: "700", color: colors.onSurface, paddingBottom: 12 },
  tier: { gap: 4, paddingVertical: 4, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  rangeTop: { fontSize: fontSize.sm, fontWeight: "700", color: colors.onSurface, paddingTop: 4 },
  del: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  add: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 44, alignSelf: "flex-start" },
  link: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
});
