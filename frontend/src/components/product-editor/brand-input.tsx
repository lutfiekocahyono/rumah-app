import React, { useEffect, useState } from "react";
import { View, Text, Pressable, Modal, TextInput, FlatList, StyleSheet } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Brand } from "@/src/api";
import { FieldError, ui } from "./ui";

/** Merek: pilih dari daftar merek (dibuat Super Admin di menu Merek & Kategori), bukan ketikan bebas. */
export function BrandInput({ value, onChange, error }: { value: string; onChange: (t: string) => void; error?: string }) {
  const insets = useSafeAreaInsets();
  const [brands, setBrands] = useState<Brand[]>([]);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => { api.brands().then(setBrands).catch(() => {}); }, [open]); // fresh list each time the picker opens
  const t = q.trim().toLowerCase();
  const shown = t ? brands.filter((b) => b.name.toLowerCase().includes(t)) : brands;
  const logo = brands.find((b) => b.name === value)?.logo;
  const pick = (name: string) => { onChange(name); setOpen(false); setQ(""); };

  return (
    <View style={{ flex: 1, minWidth: 140, gap: 6 }}>
      <Text style={ui.label}>Merek</Text>
      <Pressable testID="pe-brand" onPress={() => setOpen(true)} style={[ui.inputWrap, styles.select]}>
        {logo ? <Image source={{ uri: imgUrl(logo) }} style={styles.logo} contentFit="contain" /> : null}
        <Text style={[styles.selText, !value && { color: colors.muted }]} numberOfLines={1}>{value || "Tanpa merek"}</Text>
        <Icon name="chevron-down" size={16} color={colors.muted} />
      </Pressable>
      <FieldError msg={error} />
      <Text style={ui.hint}>Dipakai untuk filter merek di pencarian</Text>

      <Modal visible={open} animationType="slide" transparent onRequestClose={() => setOpen(false)}>
        <View style={styles.overlay}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.md }]} testID="pe-brand-sheet">
            <View style={ui.head}>
              <Text style={[ui.title, { flex: 1 }]}>Pilih merek</Text>
              <Pressable testID="pe-brand-close" hitSlop={8} onPress={() => setOpen(false)}><Icon name="close" size={22} color={colors.onSurface} /></Pressable>
            </View>
            <View style={ui.inputWrap}>
              <Icon name="search" size={16} color={colors.muted} style={{ marginLeft: spacing.md }} />
              <TextInput testID="pe-brand-search" value={q} onChangeText={setQ} placeholder="Cari merek…" placeholderTextColor={colors.muted} style={ui.input} autoFocus />
            </View>
            <FlatList data={shown} keyExtractor={(b) => b.brand_id} keyboardShouldPersistTaps="handled" style={{ maxHeight: 420 }}
              ListHeaderComponent={t ? null : (
                <Pressable testID="pe-brand-none" style={styles.row} onPress={() => pick("")}>
                  <Text style={[styles.rowText, { color: colors.muted }]}>Tanpa merek</Text>
                  {!value ? <Icon name="checkmark" size={18} color={colors.brandPrimary} /> : null}
                </Pressable>
              )}
              ListEmptyComponent={<Text style={[ui.hint, { padding: spacing.lg }]}>Merek tidak ditemukan. Merek baru dibuat Super Admin di menu Admin → Merek & Kategori.</Text>}
              renderItem={({ item }) => (
                <Pressable testID={`pe-brand-opt-${item.name}`} style={styles.row} onPress={() => pick(item.name)}>
                  {item.logo ? <Image source={{ uri: imgUrl(item.logo) }} style={styles.logo} contentFit="contain" /> : <View style={styles.logo} />}
                  <Text style={styles.rowText}>{item.name}</Text>
                  <Text style={ui.hint}>{item.count} produk</Text>
                  {value === item.name ? <Icon name="checkmark" size={18} color={colors.brandPrimary} /> : null}
                </Pressable>
              )} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  select: { minHeight: 44, paddingHorizontal: spacing.md, gap: spacing.sm },
  selText: { flex: 1, color: colors.onSurface, fontSize: fontSize.sm },
  logo: { width: 24, height: 24, borderRadius: 4 },
  overlay: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.35)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 640, alignSelf: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, paddingHorizontal: spacing.sm },
  rowText: { flex: 1, color: colors.onSurface, fontSize: fontSize.sm },
});
