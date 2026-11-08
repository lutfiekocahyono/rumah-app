import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Product } from "@/src/api";

/** Inline product search used by admin screens: type a name, tap a result. */
export function ProductPicker({ onPick, testID = "product-picker" }: { onPick: (p: Product) => void; testID?: string }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) { setItems([]); return; }
    const t = setTimeout(() => {
      setLoading(true);
      api.products({ q: q.trim(), limit: 8 }).then(setItems).catch(() => {}).finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <View style={{ gap: spacing.sm }}>
      <View style={styles.search}>
        <Icon name="search" size={16} color={colors.muted} />
        <TextInput testID={testID} value={q} onChangeText={setQ} placeholder="Cari nama produk (min. 2 huruf)"
          placeholderTextColor={colors.muted} style={styles.input} />
        {loading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
      </View>
      {items.map((p) => (
        <Pressable key={p.product_id} testID={`${testID}-result-${p.product_id}`} style={styles.row} onPress={() => { onPick(p); setQ(""); }}>
          <Image source={p.image} style={styles.img} contentFit="cover" />
          <View style={{ flex: 1 }}>
            <Text style={styles.name} numberOfLines={1}>{p.name}</Text>
            <Text style={styles.price}>Eceran {formatIDR(p.price)}</Text>
          </View>
          <Icon name="add-circle" size={22} color={colors.brandPrimary} />
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md },
  input: { flex: 1, color: colors.onSurface, paddingVertical: 10, fontSize: fontSize.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4, minHeight: 48 },
  img: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  price: { fontSize: 11, color: colors.muted },
});
