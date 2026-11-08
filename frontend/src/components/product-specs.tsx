import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, fontSize, spacing } from "@/src/theme";
import type { Product, SpecKey } from "@/src/api";

const LABELS: [SpecKey | "brand", string][] = [
  ["brand", "Merek"], ["material", "Bahan"], ["color", "Warna"], ["size", "Ukuran"], ["dimensions", "Dimensi"],
  ["weight", "Berat"], ["origin_country", "Negara asal"], ["warranty", "Garansi"], ["extra", "Informasi tambahan"],
];

/** "Spesifikasi" table on the product page; dimensions and weight come from the shipping data. */
export function ProductSpecs({ product: p }: { product: Product }) {
  const auto: Partial<Record<string, string>> = {
    brand: p.brand,
    dimensions: p.length_cm && p.width_cm && p.height_cm ? `${p.length_cm} × ${p.width_cm} × ${p.height_cm} cm` : undefined,
    weight: p.weight_grams ? (p.weight_grams >= 1000 ? `${(p.weight_grams / 1000).toLocaleString("id-ID")} kg` : `${p.weight_grams} gram`) : undefined,
  };
  const rows = LABELS.map(([k, label]) => [label, auto[k] || p.specs?.[k as SpecKey] || ""] as const).filter(([, v]) => v);
  if (!rows.length) return null;
  return (
    <View style={styles.box} testID="pd-specs">
      <Text style={styles.title}>Spesifikasi</Text>
      {rows.map(([label, v]) => (
        <View key={label} style={styles.row}>
          <Text style={styles.label}>{label}</Text>
          <Text style={styles.value}>{v}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { marginTop: spacing.lg, gap: 6 },
  title: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, marginBottom: 4 },
  row: { flexDirection: "row", gap: spacing.md, paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  label: { width: 130, fontSize: fontSize.sm, color: colors.muted },
  value: { flex: 1, fontSize: fontSize.sm, color: colors.onSurface },
});
