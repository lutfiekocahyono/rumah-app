import React, { useState } from "react";
import { View, Text, Pressable, StyleSheet, TextInput, Switch, ScrollView, Modal } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { imgUrl, type ProductForm, type VariantOption, type VariantRow } from "@/src/api";
import { FieldError, Section, digitsOf, rupiah, ui } from "./ui";
import { combos, syncRows, vkey, type Errors } from "./form";

const PRESETS = ["Warna", "Ukuran", "Model"];

function OptionEditor({ o, i, onChange, onRemove, error }: { o: VariantOption; i: number; onChange: (o: VariantOption) => void; onRemove: () => void; error?: string }) {
  const [val, setVal] = useState("");
  const add = () => {
    const v = val.trim();
    if (!v) return;
    if (o.values.some((x) => x.toLowerCase() === v.toLowerCase())) return setVal("");
    onChange({ ...o, values: [...o.values, v].slice(0, 20) });
    setVal("");
  };
  return (
    <View style={styles.opt} testID={`pe-opt-${i}`}>
      <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
        <TextInput testID={`pe-opt-name-${i}`} value={o.name} onChangeText={(t) => onChange({ ...o, name: t.slice(0, 20) })} placeholder="Nama variasi, mis. Warna"
          placeholderTextColor={colors.muted} style={[ui.inputWrap, ui.input, { flex: 1 }]} />
        <Pressable testID={`pe-opt-remove-${i}`} onPress={onRemove} hitSlop={6} style={styles.iconBtn}><Icon name="trash-outline" size={18} color={colors.error} /></Pressable>
      </View>
      <View style={styles.values}>
        {o.values.map((v) => (
          <View key={v} style={styles.valChip} testID={`pe-opt-${i}-val-${v}`}>
            <Text style={styles.valText}>{v}</Text>
            <Pressable testID={`pe-opt-${i}-del-${v}`} hitSlop={8} onPress={() => onChange({ ...o, values: o.values.filter((x) => x !== v) })}>
              <Icon name="close" size={14} color={colors.onSurfaceSecondary} />
            </Pressable>
          </View>
        ))}
        <View style={[ui.inputWrap, { minWidth: 180, flex: 1 }]}>
          <TextInput testID={`pe-opt-input-${i}`} value={val} onChangeText={setVal} onSubmitEditing={add} blurOnSubmit={false} returnKeyType="done"
            placeholder={`Tambah pilihan ${o.name || ""}`.trim()} placeholderTextColor={colors.muted} style={ui.input} />
          <Pressable testID={`pe-opt-add-${i}`} onPress={add} style={styles.iconBtn}><Icon name="add-circle" size={22} color={colors.brandPrimary} /></Pressable>
        </View>
      </View>
      <FieldError msg={error} testID={`pe-opt-error-${i}`} />
    </View>
  );
}

export function VariantsSection({ form, set, errors, maxCombos }: { form: ProductForm; set: (p: Partial<ProductForm>) => void; errors: Errors; maxCombos: number }) {
  const [bulk, setBulk] = useState({ price: 0, stock: 0 });
  const [photoFor, setPhotoFor] = useState<string | null>(null);
  const defaults = { price: form.discount_price || form.price, stock: 0 };
  const setOptions = (opts: VariantOption[]) => set({ variant_options: opts, variants: syncRows(opts, form.variants, defaults) });
  const setRow = (key: string, p: Partial<VariantRow>) => set({ variants: form.variants.map((r) => (vkey(r.values) === key ? { ...r, ...p } : r)) });
  const total = combos(form.variant_options).length;

  return (
    <Section title="Variasi Produk" icon="color-palette-outline" testID="pe-variants"
      subtitle="Warna, ukuran, atau model. Setiap kombinasi punya harga, stok, SKU, dan foto sendiri."
      right={<Switch testID="pe-variants-toggle" value={form.variants_enabled} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor={colors.surface}
        onValueChange={(v) => set(v ? { variants_enabled: true, variant_options: form.variant_options.length ? form.variant_options : [{ name: "Warna", values: [] }] } : { variants_enabled: false })} />}>
      {!form.variants_enabled ? <Text style={ui.hint}>Aktifkan jika produk punya pilihan warna, ukuran, atau model.</Text> : (
        <>
          {form.variant_options.map((o, i) => (
            <OptionEditor key={i} o={o} i={i} error={errors[`variant_options.${i}`]}
              onChange={(n) => setOptions(form.variant_options.map((x, j) => (j === i ? n : x)))}
              onRemove={() => setOptions(form.variant_options.filter((_, j) => j !== i))} />
          ))}
          {form.variant_options.length < 3 ? (
            <View style={ui.row}>
              {[...PRESETS.filter((p) => !form.variant_options.some((o) => o.name === p)), "Lainnya"].map((p) => (
                <Pressable key={p} testID={`pe-opt-new-${p}`} style={styles.addOpt} onPress={() => setOptions([...form.variant_options, { name: p === "Lainnya" ? "" : p, values: [] }])}>
                  <Icon name="add" size={16} color={colors.brandPrimary} /><Text style={styles.addOptText}>{p === "Lainnya" ? "Variasi lain" : p}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          <FieldError msg={errors.variants} testID="pe-variants-error" />
          {total > maxCombos ? <FieldError msg={`Kombinasi ${total} melebihi batas ${maxCombos}. Kurangi pilihan.`} /> : null}

          {form.variants.length ? (
            <>
              <View style={styles.bulk} testID="pe-bulk">
                <Text style={[ui.label, { width: "100%" }]}>Atur sekaligus</Text>
                <View style={[ui.inputWrap, { flex: 1, minWidth: 120 }]}><Text style={ui.prefix}>Rp</Text>
                  <TextInput testID="pe-bulk-price" keyboardType="number-pad" value={rupiah(bulk.price)} onChangeText={(t) => setBulk((b) => ({ ...b, price: digitsOf(t) }))} placeholder="Harga" placeholderTextColor={colors.muted} style={ui.input} /></View>
                <View style={[ui.inputWrap, { flex: 1, minWidth: 100 }]}>
                  <TextInput testID="pe-bulk-stock" keyboardType="number-pad" value={bulk.stock ? String(bulk.stock) : ""} onChangeText={(t) => setBulk((b) => ({ ...b, stock: digitsOf(t) }))} placeholder="Stok" placeholderTextColor={colors.muted} style={ui.input} /></View>
                <Pressable testID="pe-bulk-apply" style={styles.applyBtn} onPress={() => set({ variants: form.variants.map((r) => ({ ...r, ...(bulk.price ? { price: bulk.price } : {}), ...(bulk.stock ? { stock: bulk.stock } : {}) })) })}>
                  <Text style={styles.applyText}>Terapkan ke semua</Text>
                </Pressable>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ minWidth: "100%" }}>
                <View style={styles.table} testID="pe-variant-table">
                  <View style={[styles.tr, styles.th]}>
                    <Text style={[styles.cName, styles.thText]}>Variasi</Text><Text style={[styles.cPrice, styles.thText]}>Harga *</Text>
                    <Text style={[styles.cStock, styles.thText]}>Stok *</Text><Text style={[styles.cSku, styles.thText]}>SKU</Text>
                    <Text style={[styles.cImg, styles.thText]}>Foto</Text><Text style={[styles.cOn, styles.thText]}>Aktif</Text>
                  </View>
                  {form.variants.map((r) => {
                    const k = vkey(r.values);
                    const perr = errors[`variant.${k}.price`];
                    return (
                      <View key={k} style={[styles.tr, !r.active && { opacity: 0.5 }]} testID={`pe-vrow-${k}`}>
                        <Text style={[styles.cName, styles.td]} numberOfLines={2}>{r.values.join(" / ")}</Text>
                        <View style={styles.cPrice}>
                          <TextInput testID={`pe-vprice-${k}`} keyboardType="number-pad" value={rupiah(r.price)} onChangeText={(t) => setRow(k, { price: digitsOf(t) })}
                            style={[styles.cell, !!perr && { borderColor: colors.error }]} placeholder="0" placeholderTextColor={colors.muted} />
                          {perr ? <Text style={styles.cellErr}>{perr}</Text> : null}
                        </View>
                        <TextInput testID={`pe-vstock-${k}`} keyboardType="number-pad" value={String(r.stock)} onChangeText={(t) => setRow(k, { stock: Math.min(999999, digitsOf(t)) })} style={[styles.cell, styles.cStock]} />
                        <TextInput testID={`pe-vsku-${k}`} value={r.sku} onChangeText={(t) => setRow(k, { sku: t.toUpperCase().slice(0, 40) })} style={[styles.cell, styles.cSku]} placeholder="SKU" placeholderTextColor={colors.muted} autoCapitalize="characters" />
                        <Pressable testID={`pe-vimg-${k}`} style={[styles.cImg, styles.imgCell]} onPress={() => setPhotoFor(k)}>
                          {r.image ? <Image source={imgUrl(r.image)} style={styles.thumb} contentFit="cover" /> : <Icon name="image-outline" size={20} color={colors.muted} />}
                        </Pressable>
                        <View style={styles.cOn}><Switch testID={`pe-von-${k}`} value={r.active} onValueChange={(v) => setRow(k, { active: v })} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor={colors.surface} /></View>
                      </View>
                    );
                  })}
                </View>
              </ScrollView>
              <Text style={ui.hint}>{form.variants.filter((r) => r.active).length} dari {form.variants.length} variasi aktif · total stok {form.variants.filter((r) => r.active).reduce((t, r) => t + r.stock, 0)}</Text>
            </>
          ) : null}
        </>
      )}
      <Modal visible={!!photoFor} transparent animationType="fade" onRequestClose={() => setPhotoFor(null)}>
        <Pressable style={styles.overlay} onPress={() => setPhotoFor(null)}>
          <View style={styles.photoSheet} testID="pe-vimg-sheet">
            <Text style={ui.title}>Foto variasi {photoFor?.replace(/\//g, " / ")}</Text>
            {!form.images.length ? <Text style={ui.hint}>Unggah foto produk dulu di bagian Foto & Video.</Text> : null}
            <View style={ui.row}>
              {form.images.map((u, i) => (
                <Pressable key={u + i} testID={`pe-vimg-pick-${i}`} onPress={() => { setRow(photoFor!, { image: u }); setPhotoFor(null); }}>
                  <Image source={imgUrl(u)} style={styles.pick} contentFit="cover" />
                </Pressable>
              ))}
              <Pressable testID="pe-vimg-none" style={[styles.pick, styles.none]} onPress={() => { setRow(photoFor!, { image: "" }); setPhotoFor(null); }}>
                <Text style={ui.hint}>Tanpa foto</Text>
              </Pressable>
            </View>
          </View>
        </Pressable>
      </Modal>
    </Section>
  );
}

const styles = StyleSheet.create({
  opt: { gap: spacing.sm, padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  values: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },
  valChip: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 36 },
  valText: { fontSize: fontSize.sm, color: colors.onSurface },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  addOpt: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderStyle: "dashed", borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 40 },
  addOptText: { color: colors.brandPrimary, fontSize: fontSize.sm, fontWeight: "600" },
  bulk: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center", padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.brandTertiary },
  applyBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: spacing.md, minHeight: 44, justifyContent: "center" },
  applyText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  table: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, overflow: "hidden", flex: 1 },
  tr: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.sm, paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: colors.surface },
  th: { backgroundColor: colors.surfaceSecondary },
  thText: { fontSize: 12, fontWeight: "600", color: colors.onSurfaceSecondary },
  td: { fontSize: fontSize.sm, color: colors.onSurface },
  cName: { width: 130 }, cPrice: { width: 120 }, cStock: { width: 80 }, cSku: { width: 110 }, cImg: { width: 52 }, cOn: { width: 56, alignItems: "center" },
  cell: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: 8, minHeight: 40, fontSize: fontSize.sm, color: colors.onSurface, backgroundColor: colors.surfaceSecondary },
  cellErr: { color: colors.error, fontSize: 10, marginTop: 2 },
  imgCell: { height: 44, borderRadius: radius.sm, borderWidth: 1, borderStyle: "dashed", borderColor: colors.border, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  thumb: { width: 50, height: 44 },
  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "center", padding: spacing.lg },
  photoSheet: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, gap: spacing.md, maxWidth: 520, width: "100%", alignSelf: "center" },
  pick: { width: 72, height: 72, borderRadius: radius.sm },
  none: { borderWidth: 1, borderStyle: "dashed", borderColor: colors.border, alignItems: "center", justifyContent: "center" },
});
