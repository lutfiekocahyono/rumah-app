import React from "react";
import { View, Text, StyleSheet } from "react-native";

import { colors, fontSize, spacing, formatIDR } from "@/src/theme";
import type { PriceDown } from "@/src/api";
import { ToggleRow } from "@/src/components/admin-form";

/** Peringatan: harga cabang akan LEBIH RENDAH dari sekarang; wajib dicentang sebelum diterapkan. */
export function PriceDownWarning({ testID, count, sample, label, ok, onChange }: {
  testID: string; count: number; sample: PriceDown[]; label: string; ok: boolean; onChange: (v: boolean) => void;
}) {
  if (!count) return null;
  return (
    <View style={styles.box} testID={testID}>
      <Text style={styles.h} testID={`${testID}-count`}>⚠ {count.toLocaleString("id-ID")} produk {label} akan LEBIH MURAH dari harga cabang sekarang</Text>
      {sample.slice(0, 5).map((x) => (
        <Text key={x.product_id} style={styles.row} numberOfLines={2}>{x.name}: {formatIDR(x.old_price)} → {formatIDR(x.new_price)}</Text>
      ))}
      {count > 5 ? <Text style={styles.row}>…dan {(count - 5).toLocaleString("id-ID")} produk lainnya</Text> : null}
      <ToggleRow testID={`${testID}-ok`} label="Saya mengerti, harga ini memang diturunkan" value={ok} onChange={onChange} />
    </View>
  );
}

const styles = StyleSheet.create({
  box: { backgroundColor: colors.surfaceSecondary, borderRadius: 8, padding: spacing.sm, gap: 4, borderLeftWidth: 3, borderLeftColor: colors.error },
  h: { fontSize: fontSize.sm, fontWeight: "600", color: colors.error },
  row: { fontSize: fontSize.sm, color: colors.onSurface },
});
