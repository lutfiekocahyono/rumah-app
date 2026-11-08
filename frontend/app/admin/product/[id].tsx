import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { Image } from "expo-image";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, CUSTOMER_TYPE_LABEL, type CustomerType, type ProductTiers } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

const TYPES: CustomerType[] = ["langsung", "pengecer", "reseller"];
type Row = { min_qty: string; price: string };

export default function AdminProductTiers() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [product, setProduct] = useState<ProductTiers | null>(null);
  const [rows, setRows] = useState<Record<CustomerType, Row[]>>({ langsung: [], pengecer: [], reseller: [] });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const fromApi = (p: ProductTiers) =>
    Object.fromEntries(TYPES.map((t) => [t, (p.tier_prices[t] ?? []).map((r) => ({ min_qty: String(r.min_qty), price: String(r.price) }))])) as Record<CustomerType, Row[]>;

  useEffect(() => {
    if (!id) return;
    api.adminProductTiers(id).then((p) => { setProduct(p); setRows(fromApi(p)); }).catch((e) => setMsg({ ok: false, text: e.message }));
  }, [id]);

  const update = (t: CustomerType, i: number, patch: Partial<Row>) =>
    setRows((r) => ({ ...r, [t]: r[t].map((row, j) => (j === i ? { ...row, ...patch } : row)) }));

  const save = async () => {
    if (!id) return;
    setMsg(null);
    const payload = Object.fromEntries(TYPES.map((t) => [t, rows[t].map((r) => ({ min_qty: parseInt(r.min_qty, 10), price: parseInt(r.price.replace(/\D/g, ""), 10) }))])) as ProductTiers["tier_prices"];
    if (TYPES.some((t) => payload[t].some((r) => !(r.min_qty >= 1) || !(r.price > 0)))) {
      setMsg({ ok: false, text: "Isi jumlah minimal (≥ 1) dan harga (> 0) di setiap baris" });
      return;
    }
    setSaving(true);
    try {
      const res = await api.adminSaveProductTiers(id, payload);
      setRows(fromApi({ ...(product as ProductTiers), tier_prices: res.tier_prices }));
      setMsg({ ok: true, text: "Harga manual disimpan" });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-product-tiers-screen">
      <ScreenHeader title="Harga Bertingkat Produk" />
      {!product ? (
        msg ? <Text style={[styles.msg, { color: colors.error, margin: spacing.lg }]}>{msg.text}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + 120 }}>
          <View style={styles.productRow}>
            <Image source={product.image} style={styles.img} contentFit="cover" />
            <View style={{ flex: 1 }}>
              <Text style={styles.name} numberOfLines={2}>{product.name}</Text>
              <Text style={styles.help}>Harga eceran website {formatIDR(product.price)}</Text>
            </View>
          </View>
          <Text style={styles.help}>
            Isi harga per pcs berdasarkan jumlah beli. Jika satu kategori pelanggan dikosongkan, harga mengikuti Pengaturan Harga umum.
          </Text>
          {TYPES.map((t) => (
            <View key={t} style={styles.card} testID={`tiers-${t}`}>
              <Text style={styles.section}>{CUSTOMER_TYPE_LABEL[t]}</Text>
              {rows[t].length === 0 ? <Text style={styles.help}>Mengikuti pengaturan umum</Text> : null}
              {rows[t].map((r, i) => (
                <View key={i} style={styles.tierRow}>
                  <View style={[styles.inputBox, { flex: 2 }]}>
                    <Text style={styles.prefix}>≥</Text>
                    <TextInput testID={`tier-${t}-qty-${i}`} value={r.min_qty} keyboardType="number-pad" style={styles.input} onChangeText={(v) => update(t, i, { min_qty: v })} />
                    <Text style={styles.suffix}>pcs</Text>
                  </View>
                  <View style={[styles.inputBox, { flex: 3 }]}>
                    <Text style={styles.prefix}>Rp</Text>
                    <TextInput testID={`tier-${t}-price-${i}`} value={r.price} keyboardType="number-pad" style={styles.input} onChangeText={(v) => update(t, i, { price: v })} />
                  </View>
                  <Pressable testID={`tier-${t}-remove-${i}`} style={styles.iconBtn} onPress={() => setRows((s) => ({ ...s, [t]: s[t].filter((_, j) => j !== i) }))}>
                    <Icon name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                </View>
              ))}
              <Pressable testID={`tier-${t}-add`} style={styles.addBtn}
                onPress={() => setRows((s) => ({ ...s, [t]: [...s[t], { min_qty: s[t].length ? "" : "1", price: s[t].length ? "" : String(product.price) }] }))}>
                <Icon name="add" size={18} color={colors.brandPrimary} />
                <Text style={styles.addText}>Tambah baris</Text>
              </Pressable>
            </View>
          ))}
          {msg ? <Text style={[styles.msg, { color: msg.ok ? colors.success : colors.error }]} testID="tiers-msg">{msg.text}</Text> : null}
        </KeyboardAwareScrollView>
      )}
      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.lg, insets.bottom + spacing.sm) }]}>
        <Pressable testID="tiers-save-btn" style={styles.saveBtn} onPress={save} disabled={saving || !product}>
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>Simpan</Text>}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  productRow: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  img: { width: 64, height: 64, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.base, color: colors.onSurface },
  help: { fontSize: fontSize.sm, color: colors.muted },
  section: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500" },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  tierRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  inputBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.sm, minHeight: 44 },
  input: { flex: 1, color: colors.onSurface, fontSize: fontSize.base, paddingVertical: 8, minWidth: 30 },
  prefix: { color: colors.muted, fontSize: fontSize.sm, marginRight: 4 },
  suffix: { color: colors.muted, fontSize: fontSize.sm, marginLeft: 4 },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44 },
  addText: { color: colors.brandPrimary, fontWeight: "500" },
  msg: { fontSize: fontSize.sm },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  saveBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, minHeight: 48, alignItems: "center", justifyContent: "center" },
  saveText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },
});
