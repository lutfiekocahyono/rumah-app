import React, { useMemo, useState } from "react";
import { View, Text, Pressable, StyleSheet, Modal, TextInput, FlatList } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import type { Category, EditorContext, ProductForm } from "@/src/api";
import { FieldError, Input, Pill, Section, ui } from "./ui";
import { RichEditor } from "./rich-editor";
import type { Errors } from "./form";

/** Searchable category list (main categories, or the children of the chosen one). */
function CategoryPicker({ visible, list, title, onPick, onClose }: { visible: boolean; list: Category[]; title: string; onPick: (c: Category) => void; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");
  const shown = list.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.md }]} testID="pe-cat-sheet">
          <View style={ui.head}>
            <Text style={[ui.title, { flex: 1 }]}>{title}</Text>
            <Pressable testID="pe-cat-close" hitSlop={8} onPress={onClose}><Icon name="close" size={22} color={colors.onSurface} /></Pressable>
          </View>
          <View style={ui.inputWrap}>
            <Icon name="search" size={16} color={colors.muted} style={{ marginLeft: spacing.md }} />
            <TextInput testID="pe-cat-search" value={q} onChangeText={setQ} placeholder="Cari kategori…" placeholderTextColor={colors.muted} style={ui.input} autoFocus />
          </View>
          <FlatList data={shown} keyExtractor={(c) => c.category_id} keyboardShouldPersistTaps="handled" style={{ maxHeight: 420 }}
            ListEmptyComponent={<Text style={[ui.hint, { padding: spacing.lg }]}>Kategori tidak ditemukan</Text>}
            renderItem={({ item }) => (
              <Pressable testID={`pe-cat-${item.category_id}`} style={styles.catRow} onPress={() => { onPick(item); setQ(""); }}>
                <Text style={{ flex: 1, color: colors.onSurface, fontSize: fontSize.sm }}>{item.name}</Text>
                <Text style={ui.hint}>{item.count} produk</Text>
              </Pressable>
            )} />
        </View>
      </View>
    </Modal>
  );
}

export function BasicInfo({ form, set, errors, cats, ctx, storeId, onStore }: {
  form: ProductForm; set: (p: Partial<ProductForm>) => void; errors: Errors; cats: Category[];
  ctx: EditorContext | null; storeId: string; onStore: (id: string) => void;
}) {
  const [picker, setPicker] = useState<"" | "main" | "sub">("");
  const mains = useMemo(() => cats.filter((c) => !c.parent), [cats]);
  const subs = useMemo(() => cats.filter((c) => c.parent === form.category), [cats, form.category]);
  const nameOf = (id: string) => cats.find((c) => c.category_id === id)?.name;
  return (
    <Section title="Informasi Dasar" icon="information-circle-outline" testID="pe-basic" subtitle="Nama, kategori, dan deskripsi yang jelas membuat produk mudah ditemukan.">
      {ctx?.admin && ctx.stores.length ? (
        <View style={{ gap: 6 }}>
          <Text style={ui.label}>Tambahkan ke toko</Text>
          <View style={ui.row}>
            {ctx.stores.slice(0, 12).map((s) => <Pill key={s.store_id} testID={`pe-store-${s.store_id}`} label={s.name} on={storeId === s.store_id} onPress={() => onStore(s.store_id)} />)}
          </View>
        </View>
      ) : null}
      <Input testID="pe-name" label="Nama produk" required value={form.name} maxLength={150} counter={`${form.name.length}/150`}
        onChangeText={(t) => set({ name: t })} error={errors.name} placeholder="Contoh: Kaos Polos Katun Combed 30s Premium" />
      <View style={ui.row}>
        <View style={{ flex: 1, minWidth: 200, gap: 4 }}>
          <Text style={ui.label}>Kategori utama<Text style={{ color: colors.error }}> *</Text></Text>
          <Pressable testID="pe-category" onPress={() => setPicker("main")} style={[ui.inputWrap, styles.select, !!errors.category && ui.inputErr]}>
            <Text style={[styles.selText, !form.category && { color: colors.muted }]}>{nameOf(form.category) ?? "Pilih kategori"}</Text>
            <Icon name="chevron-down" size={16} color={colors.muted} />
          </Pressable>
          <FieldError msg={errors.category} testID="pe-category-error" />
        </View>
        <View style={{ flex: 1, minWidth: 200, gap: 4 }}>
          <Text style={ui.label}>Subkategori</Text>
          <Pressable testID="pe-subcategory" disabled={!subs.length} onPress={() => setPicker("sub")} style={[ui.inputWrap, styles.select, !subs.length && { opacity: 0.5 }]}>
            <Text style={[styles.selText, !form.subcategory && { color: colors.muted }]}>{nameOf(form.subcategory) ?? (subs.length ? "Pilih subkategori" : "Tidak ada subkategori")}</Text>
            {form.subcategory ? <Pressable testID="pe-subcategory-clear" hitSlop={8} onPress={() => set({ subcategory: "" })}><Icon name="close-circle" size={16} color={colors.muted} /></Pressable> : <Icon name="chevron-down" size={16} color={colors.muted} />}
          </Pressable>
          <FieldError msg={errors.subcategory} />
        </View>
      </View>
      <View style={ui.row}>
        <Input testID="pe-brand" label="Brand / merek" value={form.brand} maxLength={60} onChangeText={(t) => set({ brand: t })} placeholder="Contoh: Advance" />
        <Input testID="pe-sku" label="SKU produk" value={form.sku} maxLength={40} onChangeText={(t) => set({ sku: t.toUpperCase() })} placeholder="Contoh: KAOS-001" autoCapitalize="characters" />
      </View>
      <View style={ui.row}>
        <View style={{ gap: 6, minWidth: 200, flex: 1 }}>
          <Text style={ui.label}>Kondisi produk</Text>
          <View style={ui.row}>
            <Pill testID="pe-cond-new" label="Baru" on={form.condition === "new"} onPress={() => set({ condition: "new" })} />
            <Pill testID="pe-cond-used" label="Bekas" on={form.condition === "used"} onPress={() => set({ condition: "used" })} />
          </View>
        </View>
        <View style={{ gap: 6, minWidth: 200, flex: 1 }}>
          <Text style={ui.label}>Status produk</Text>
          <View style={ui.row}>
            <Pill testID="pe-status-active" icon="eye-outline" label="Aktif (tampil)" on={form.status === "active"} onPress={() => set({ status: "active" })} />
            <Pill testID="pe-status-inactive" icon="eye-off-outline" label="Nonaktif" on={form.status === "inactive"} onPress={() => set({ status: "inactive" })} />
          </View>
        </View>
      </View>
      <View style={{ gap: 6 }}>
        <Input testID="pe-showcase" label="Etalase toko" value={form.showcase} maxLength={40} onChangeText={(t) => set({ showcase: t })} placeholder="Contoh: Elektronik Dapur" hint="Kelompok produk di halaman toko Anda" />
        {ctx?.showcases.length ? (
          <View style={ui.row}>
            {ctx.showcases.slice(0, 10).map((s) => <Pill key={s} testID={`pe-showcase-${s}`} label={s} on={form.showcase === s} onPress={() => set({ showcase: s })} />)}
          </View>
        ) : null}
      </View>
      <RichEditor value={form.description} onChange={(t) => set({ description: t })} error={errors.description} />
      <CategoryPicker visible={!!picker} title={picker === "sub" ? "Pilih subkategori" : "Pilih kategori utama"} list={picker === "sub" ? subs : mains}
        onClose={() => setPicker("")}
        onPick={(c) => { set(picker === "sub" ? { subcategory: c.category_id } : { category: c.category_id, subcategory: "" }); setPicker(""); }} />
    </Section>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.35)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 640, alignSelf: "center" },
  catRow: { flexDirection: "row", alignItems: "center", minHeight: 48, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, paddingHorizontal: spacing.sm },
  select: { minHeight: 44, paddingHorizontal: spacing.md, justifyContent: "space-between" },
  selText: { flex: 1, color: colors.onSurface, fontSize: fontSize.sm },
});
