import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, CUSTOMER_TYPE_LABEL, type CustomerType } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

const TYPES: CustomerType[] = ["langsung", "pengecer", "reseller"];
type TierRow = { min_qty: string; discount_percent: string };

export default function AdminPricing() {
  const insets = useSafeAreaInsets();
  const [disc, setDisc] = useState<Record<CustomerType, string>>({ langsung: "0", pengecer: "0", reseller: "0" });
  const [tiers, setTiers] = useState<TierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.adminPricing().then((p) => {
      setDisc({ langsung: String(p.type_discounts.langsung ?? 0), pengecer: String(p.type_discounts.pengecer ?? 0), reseller: String(p.type_discounts.reseller ?? 0) });
      setTiers(p.qty_tiers.map((t) => ({ min_qty: String(t.min_qty), discount_percent: String(t.discount_percent) })));
    }).catch((e) => setMsg({ ok: false, text: e.message })).finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setMsg(null);
    const qty = tiers.map((t) => ({ min_qty: parseInt(t.min_qty, 10), discount_percent: parseFloat(t.discount_percent.replace(",", ".")) }));
    if (qty.some((t) => !(t.min_qty >= 2) || !(t.discount_percent >= 0 && t.discount_percent <= 100))) {
      setMsg({ ok: false, text: "Jumlah minimal ≥ 2 dan potongan 0–100%" });
      return;
    }
    const td = Object.fromEntries(TYPES.map((t) => [t, parseFloat(disc[t].replace(",", ".")) || 0])) as Record<CustomerType, number>;
    setSaving(true);
    try {
      const p = await api.adminSavePricing({ type_discounts: td, qty_tiers: qty });
      setTiers(p.qty_tiers.map((t) => ({ min_qty: String(t.min_qty), discount_percent: String(t.discount_percent) })));
      setMsg({ ok: true, text: "Pengaturan harga disimpan" });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-pricing-screen">
      <ScreenHeader title="Pengaturan Harga" />
      {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + 120 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.section}>Potongan per Kategori Pelanggan</Text>
          <Text style={styles.help}>Persen potongan dari harga eceran (harga website). Berlaku untuk semua produk.</Text>
          <View style={styles.card}>
            {TYPES.map((t) => (
              <View key={t} style={styles.inputRow}>
                <Text style={styles.label}>{CUSTOMER_TYPE_LABEL[t]}</Text>
                <View style={styles.inputBox}>
                  <TextInput
                    testID={`type-discount-${t}`}
                    value={disc[t]}
                    onChangeText={(v) => setDisc((d) => ({ ...d, [t]: v }))}
                    keyboardType="decimal-pad"
                    style={styles.input}
                  />
                  <Text style={styles.suffix}>%</Text>
                </View>
              </View>
            ))}
          </View>

          <Text style={styles.section}>Potongan Tambahan per Jumlah Beli</Text>
          <Text style={styles.help}>Contoh: beli ≥ 12 pcs dapat potongan 4% lagi. Dipakai untuk produk yang tidak punya harga manual.</Text>
          <View style={styles.card}>
            {tiers.length === 0 ? <Text style={styles.help}>Belum ada aturan jumlah.</Text> : null}
            {tiers.map((t, i) => (
              <View key={i} style={styles.tierRow}>
                <Text style={styles.label}>Beli ≥</Text>
                <View style={[styles.inputBox, { flex: 1 }]}>
                  <TextInput testID={`qty-tier-min-${i}`} value={t.min_qty} keyboardType="number-pad" style={styles.input}
                    onChangeText={(v) => setTiers((rows) => rows.map((r, j) => (j === i ? { ...r, min_qty: v } : r)))} />
                  <Text style={styles.suffix}>pcs</Text>
                </View>
                <View style={[styles.inputBox, { flex: 1 }]}>
                  <TextInput testID={`qty-tier-pct-${i}`} value={t.discount_percent} keyboardType="decimal-pad" style={styles.input}
                    onChangeText={(v) => setTiers((rows) => rows.map((r, j) => (j === i ? { ...r, discount_percent: v } : r)))} />
                  <Text style={styles.suffix}>%</Text>
                </View>
                <Pressable testID={`qty-tier-remove-${i}`} hitSlop={8} style={styles.iconBtn} onPress={() => setTiers((rows) => rows.filter((_, j) => j !== i))}>
                  <Icon name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </View>
            ))}
            <Pressable testID="qty-tier-add" style={styles.addBtn} onPress={() => setTiers((r) => [...r, { min_qty: "", discount_percent: "" }])}>
              <Icon name="add" size={18} color={colors.brandPrimary} />
              <Text style={styles.addText}>Tambah aturan jumlah</Text>
            </Pressable>
          </View>
          {msg ? <Text style={[styles.msg, { color: msg.ok ? colors.success : colors.error }]} testID="pricing-msg">{msg.text}</Text> : null}
        </KeyboardAwareScrollView>
      )}
      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.lg, insets.bottom + spacing.sm) }]}>
        <Pressable testID="pricing-save-btn" style={styles.saveBtn} onPress={save} disabled={saving || loading}>
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>Simpan</Text>}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  section: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500" },
  help: { fontSize: fontSize.sm, color: colors.muted },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  inputRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  tierRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  label: { fontSize: fontSize.sm, color: colors.onSurface },
  inputBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.sm, minWidth: 0, minHeight: 44 },
  input: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: fontSize.base, paddingVertical: 8 },
  suffix: { color: colors.muted, fontSize: fontSize.sm, marginLeft: 4 },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44 },
  addText: { color: colors.brandPrimary, fontWeight: "500" },
  msg: { fontSize: fontSize.sm },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  saveBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, minHeight: 48, alignItems: "center", justifyContent: "center" },
  saveText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },
});
