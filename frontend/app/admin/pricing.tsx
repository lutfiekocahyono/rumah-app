import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, CUSTOMER_TYPE_LABEL, type CustomerType, type DiscountMode, type Pricing } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

const TYPES: CustomerType[] = ["langsung", "pengecer", "reseller"];
type TierRow = { min_qty: string; mode: DiscountMode; value: string };

const num = (s: string) => parseFloat(s.replace(/\./g, "").replace(",", "."));

/** Small "% | Rp" switch next to an amount input. */
function ModeToggle({ mode, onChange, testID }: { mode: DiscountMode; onChange: (m: DiscountMode) => void; testID: string }) {
  return (
    <View style={styles.toggle}>
      {(["percent", "rupiah"] as const).map((m) => (
        <Pressable key={m} testID={`${testID}-${m}`} style={[styles.toggleBtn, mode === m && styles.toggleActive]} onPress={() => onChange(m)}>
          <Text style={[styles.toggleText, mode === m && styles.toggleTextActive]}>{m === "percent" ? "%" : "Rp"}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function AmountInput({ mode, value, onChangeText, testID }: { mode: DiscountMode; value: string; onChangeText: (v: string) => void; testID: string }) {
  return (
    <View style={[styles.inputBox, { flex: 1 }]}>
      {mode === "rupiah" ? <Text style={styles.prefix}>Rp</Text> : null}
      <TextInput testID={testID} value={value} onChangeText={onChangeText} keyboardType={mode === "rupiah" ? "number-pad" : "decimal-pad"} style={styles.input} />
      {mode === "percent" ? <Text style={styles.suffix}>%</Text> : null}
    </View>
  );
}

export default function AdminPricing() {
  const insets = useSafeAreaInsets();
  const [disc, setDisc] = useState<Record<CustomerType, string>>({ langsung: "0", pengecer: "0", reseller: "0" });
  const [modes, setModes] = useState<Record<CustomerType, DiscountMode>>({ langsung: "percent", pengecer: "percent", reseller: "percent" });
  const [tiers, setTiers] = useState<TierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const applyApi = (p: Pricing) => {
    setDisc(Object.fromEntries(TYPES.map((t) => [t, String(p.type_discounts[t] ?? 0)])) as Record<CustomerType, string>);
    setModes(Object.fromEntries(TYPES.map((t) => [t, p.type_discount_modes?.[t] ?? "percent"])) as Record<CustomerType, DiscountMode>);
    setTiers(p.qty_tiers.map((t) => ({ min_qty: String(t.min_qty), mode: t.mode ?? "percent", value: String(t.value ?? t.discount_percent ?? 0) })));
  };

  useEffect(() => {
    api.adminPricing().then(applyApi).catch((e) => setMsg({ ok: false, text: e.message })).finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setMsg(null);
    const qty = tiers.map((t) => ({ min_qty: parseInt(t.min_qty, 10), mode: t.mode, value: num(t.value) }));
    const td = Object.fromEntries(TYPES.map((t) => [t, num(disc[t]) || 0])) as Record<CustomerType, number>;
    const badPct = (mode: DiscountMode, v: number) => !(v >= 0) || (mode === "percent" && v > 100);
    if (qty.some((t) => !(t.min_qty >= 2) || badPct(t.mode, t.value)) || TYPES.some((t) => badPct(modes[t], td[t]))) {
      setMsg({ ok: false, text: "Jumlah minimal ≥ 2, potongan persen 0–100%, rupiah ≥ 0" });
      return;
    }
    setSaving(true);
    try {
      applyApi(await api.adminSavePricing({ type_discounts: td, type_discount_modes: modes, qty_tiers: qty }));
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
          <Text style={styles.help}>Potongan dari harga eceran (harga website), dalam persen atau rupiah per pcs. Berlaku untuk semua produk.</Text>
          <View style={styles.card}>
            {TYPES.map((t) => (
              <View key={t} style={{ gap: 6 }}>
                <Text style={styles.label}>{CUSTOMER_TYPE_LABEL[t]}</Text>
                <View style={styles.tierRow}>
                  <ModeToggle testID={`type-mode-${t}`} mode={modes[t]} onChange={(m) => setModes((s) => ({ ...s, [t]: m }))} />
                  <AmountInput testID={`type-discount-${t}`} mode={modes[t]} value={disc[t]} onChangeText={(v) => setDisc((d) => ({ ...d, [t]: v }))} />
                </View>
              </View>
            ))}
          </View>

          <Text style={styles.section}>Potongan Tambahan per Jumlah Beli</Text>
          <Text style={styles.help}>Contoh: beli ≥ 12 pcs dapat potongan 4% atau Rp2.000 per pcs lagi. Tiap aturan dihitung dari harga kategori pelanggan (tidak bertumpuk), jadi buat potongan makin besar untuk jumlah makin banyak. Dipakai untuk produk tanpa harga manual.</Text>
          <View style={styles.card}>
            {tiers.length === 0 ? <Text style={styles.help}>Belum ada aturan jumlah.</Text> : null}
            {tiers.map((t, i) => (
              <View key={i} style={styles.tierBlock}>
                <View style={styles.tierRow}>
                  <Text style={styles.label}>Beli ≥</Text>
                  <View style={[styles.inputBox, { flex: 1 }]}>
                    <TextInput testID={`qty-tier-min-${i}`} value={t.min_qty} keyboardType="number-pad" style={styles.input}
                      onChangeText={(v) => setTiers((rows) => rows.map((r, j) => (j === i ? { ...r, min_qty: v } : r)))} />
                    <Text style={styles.suffix}>pcs</Text>
                  </View>
                  <Pressable testID={`qty-tier-remove-${i}`} hitSlop={8} style={styles.iconBtn} onPress={() => setTiers((rows) => rows.filter((_, j) => j !== i))}>
                    <Icon name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                </View>
                <View style={styles.tierRow}>
                  <Text style={styles.label}>Potong</Text>
                  <ModeToggle testID={`qty-tier-mode-${i}`} mode={t.mode} onChange={(m) => setTiers((rows) => rows.map((r, j) => (j === i ? { ...r, mode: m } : r)))} />
                  <AmountInput testID={`qty-tier-pct-${i}`} mode={t.mode} value={t.value}
                    onChangeText={(v) => setTiers((rows) => rows.map((r, j) => (j === i ? { ...r, value: v } : r)))} />
                </View>
              </View>
            ))}
            <Pressable testID="qty-tier-add" style={styles.addBtn} onPress={() => setTiers((r) => [...r, { min_qty: "", mode: "percent", value: "" }])}>
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
  prefix: { color: colors.muted, fontSize: fontSize.sm, marginRight: 4 },
  tierBlock: { gap: spacing.sm, paddingBottom: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  toggle: { flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, padding: 3 },
  toggleBtn: { minWidth: 44, minHeight: 38, alignItems: "center", justifyContent: "center", borderRadius: radius.sm },
  toggleActive: { backgroundColor: colors.brandPrimary },
  toggleText: { fontSize: fontSize.sm, color: colors.onSurfaceTertiary, fontWeight: "500" },
  toggleTextActive: { color: colors.onBrandPrimary },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44 },
  addText: { color: colors.brandPrimary, fontWeight: "500" },
  msg: { fontSize: fontSize.sm },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  saveBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, minHeight: 48, alignItems: "center", justifyContent: "center" },
  saveText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },
});
