import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Keyboard } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl } from "@/src/api";

type Sugg = Awaited<ReturnType<typeof api.suggest>>;

/** Saran saat mengetik: produk (buka detail), merek & kategori (jadi filter), atau cari kata itu. */
export function SearchSuggestions({ q, onBrand, onCategory, onSearch }: {
  q: string; onBrand: (b: string) => void; onCategory: (id: string, name: string) => void; onSearch: (text: string) => void;
}) {
  const router = useRouter();
  const [s, setS] = useState<Sugg | null>(null);
  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setS(null); return; }
    let live = true;
    const h = setTimeout(() => api.suggest(t).then((r) => { if (live) setS(r); }).catch(() => {}), 200);
    return () => { live = false; clearTimeout(h); };
  }, [q]);
  if (!s || (!s.products.length && !s.brands.length && !s.categories.length)) return null;
  const close = () => Keyboard.dismiss();
  return (
    <View style={styles.box} testID="search-suggestions">
      {s.brands.map((b) => (
        <Pressable key={`b-${b}`} testID={`sugg-brand-${b}`} style={styles.row} onPress={() => { close(); onBrand(b); }}>
          <Icon name="pricetag-outline" size={18} color={colors.brandPrimary} />
          <Text style={styles.text} numberOfLines={1}>Merek <Text style={styles.bold}>{b}</Text></Text>
        </Pressable>
      ))}
      {s.categories.map((c) => (
        <Pressable key={`c-${c.category_id}`} testID={`sugg-cat-${c.category_id}`} style={styles.row} onPress={() => { close(); onCategory(c.category_id, c.name); }}>
          <Icon name="grid-outline" size={18} color={colors.brandPrimary} />
          <Text style={styles.text} numberOfLines={1}>Kategori <Text style={styles.bold}>{c.name}</Text></Text>
        </Pressable>
      ))}
      {s.products.map((p) => (
        <Pressable key={p.product_id} testID={`sugg-product-${p.product_id}`} style={styles.row} onPress={() => { close(); router.push(`/product/${p.product_id}` as any); }}>
          {p.image ? <Image source={imgUrl(p.image)} style={styles.thumb} contentFit="cover" /> : <Icon name="cube-outline" size={18} color={colors.muted} />}
          <Text style={styles.text} numberOfLines={2}>{p.name}</Text>
        </Pressable>
      ))}
      <Pressable testID="sugg-search-all" style={styles.row} onPress={() => { close(); onSearch(q.trim()); }}>
        <Icon name="search" size={18} color={colors.muted} />
        <Text style={styles.text} numberOfLines={1}>Cari semua “{q.trim()}”</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { marginHorizontal: spacing.lg, marginBottom: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, paddingHorizontal: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  thumb: { width: 32, height: 32, borderRadius: radius.sm },
  text: { flex: 1, fontSize: fontSize.sm, color: colors.onSurface },
  bold: { fontWeight: "700" },
});
