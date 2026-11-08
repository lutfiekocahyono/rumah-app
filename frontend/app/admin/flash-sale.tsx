import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator, TextInput } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type AdminFlashSale } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ProductPicker } from "@/src/components/product-picker";
import { DateTimeField } from "@/src/components/datetime-field";
import { adminStyles, Card, digits, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

export default function AdminFlashSaleScreen() {
  const insets = useSafeAreaInsets();
  const [f, setF] = useState<AdminFlashSale | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  useEffect(() => { api.adminFlashSale().then(setF).catch((e) => setMsg({ err: e.message, ok: "" })); }, []);

  const set = (patch: Partial<AdminFlashSale>) => setF((x) => (x ? { ...x, ...patch } : x));
  const setPrice = (pid: string, v: number) => set({ items: f!.items.map((i) => (i.product_id === pid ? { ...i, flash_price: v } : i)) });

  const save = async () => {
    if (!f) return;
    const bad = f.items.find((i) => !i.flash_price || i.flash_price >= i.price);
    if (bad) return setMsg({ err: `Harga flash "${bad.name}" harus di bawah harga eceran`, ok: "" });
    if (f.active && new Date(f.ends_at).getTime() <= Date.now()) return setMsg({ err: "Waktu berakhir harus di masa depan", ok: "" });
    setSaving(true);
    try {
      setF(await api.adminSaveFlashSale({ title: f.title, active: f.active, ends_at: f.ends_at,
        items: f.items.map((i) => ({ product_id: i.product_id, flash_price: i.flash_price })) }));
      setMsg({ err: "", ok: "Flash Sale disimpan" });
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-flash-screen">
      <ScreenHeader title="Flash Sale" />
      {!f ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          <Card>
            <ToggleRow testID="flash-active" label="Flash Sale aktif" sub="Harga flash berlaku di keranjang sampai waktu habis" value={f.active} onChange={(v) => set({ active: v })} />
            <Field testID="flash-title" label="Judul" value={f.title} onChangeText={(t) => set({ title: t })} />
            <Text style={adminStyles.section}>Berakhir pada</Text>
            <DateTimeField testID="flash-ends" value={f.ends_at} onChange={(v) => v && set({ ends_at: v })} />
          </Card>

          <Card>
            <Text style={styles.h}>Produk Flash Sale ({f.items.length})</Text>
            <ProductPicker testID="flash-picker" onPick={(p) => {
              if (f.items.some((i) => i.product_id === p.product_id)) return;
              set({ items: [...f.items, { product_id: p.product_id, name: p.name, image: p.image, price: p.price, flash_price: Math.round(p.price * 0.9 / 100) * 100 }] });
            }} />
            {f.items.map((i) => {
              const off = i.price > i.flash_price ? Math.round(((i.price - i.flash_price) / i.price) * 100) : 0;
              return (
                <View key={i.product_id} style={styles.item} testID={`flash-row-${i.product_id}`}>
                  <Image source={i.image} style={styles.img} contentFit="cover" />
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text style={styles.name} numberOfLines={2}>{i.name}</Text>
                    <Text style={adminStyles.muted}>Eceran {formatIDR(i.price)}{off ? ` · hemat ${off}%` : ""}</Text>
                    <View style={styles.priceRow}>
                      <Text style={styles.rp}>Rp</Text>
                      <TextInput testID={`flash-price-${i.product_id}`} keyboardType="number-pad" value={String(i.flash_price || "")}
                        onChangeText={(t) => setPrice(i.product_id, digits(t))} style={styles.priceInput} placeholder="Harga flash" placeholderTextColor={colors.muted} />
                    </View>
                  </View>
                  <Pressable testID={`flash-remove-${i.product_id}`} hitSlop={10} onPress={() => set({ items: f.items.filter((x) => x.product_id !== i.product_id) })}>
                    <Icon name="trash-outline" size={20} color={colors.error} />
                  </Pressable>
                </View>
              );
            })}
          </Card>
          {msg.err ? <Text style={adminStyles.err} testID="flash-error">{msg.err}</Text> : null}
          {msg.ok ? <Text style={adminStyles.ok} testID="flash-ok">{msg.ok}</Text> : null}
          <PrimaryButton testID="flash-save" label="Simpan Flash Sale" onPress={save} loading={saving} />
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.base, fontWeight: "500", color: colors.onSurface },
  item: { flexDirection: "row", gap: spacing.sm, alignItems: "center", borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider, paddingTop: spacing.sm },
  img: { width: 52, height: 52, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.sm },
  rp: { color: colors.muted, fontSize: fontSize.sm },
  priceInput: { flex: 1, paddingVertical: 8, color: colors.onSurface, fontSize: fontSize.sm },
});
