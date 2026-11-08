import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, FlatList, Dimensions, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;

export default function Search() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ q?: string }>();
  const [q, setQ] = useState(params.q ?? "");
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      if (!q.trim()) { setResults([]); return; }
      setLoading(true);
      api.products({ q: q.trim() }).then((p) => { setResults(p); setLoading(false); }).catch(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="search-screen">
      <View style={styles.header}>
        <Pressable testID="search-back" hitSlop={8} onPress={() => router.back()}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <View style={styles.input}>
          <Icon name="search" size={18} color={colors.muted} />
          <TextInput
            testID="search-input"
            placeholder="Cari produk…"
            placeholderTextColor={colors.muted}
            value={q} onChangeText={setQ} autoFocus
            style={{ flex: 1, color: colors.onSurface, paddingVertical: 10 }}
          />
          {q ? <Pressable hitSlop={8} onPress={() => setQ("")}><Icon name="close-circle" size={18} color={colors.muted} /></Pressable> : null}
        </View>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : !q.trim() ? (
        <View style={styles.empty}>
          <Icon name="search-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Cari furniture, elektronik, dapur, dan lainnya</Text>
        </View>
      ) : results.length === 0 ? (
        <View style={styles.empty}>
          <Icon name="sad-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Produk tidak ditemukan</Text>
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(p) => p.product_id}
          numColumns={2}
          columnWrapperStyle={{ gap: CARD_GAP, paddingHorizontal: spacing.lg }}
          contentContainerStyle={{ gap: CARD_GAP, paddingVertical: spacing.md }}
          renderItem={({ item }) => <ProductCard product={item} style={{ width: CARD_WIDTH }} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  input: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.md },
  empty: { alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm, flex: 1 },
  emptyText: { color: colors.muted, fontSize: fontSize.sm, textAlign: "center" },
});
