import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, FlatList, Dimensions, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Category, type Product } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;

export default function Kategori() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [cats, setCats] = useState<Category[]>([]);
  const [active, setActive] = useState<string>("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const c = await api.categories();
      setCats(c);
      setActive(c[0]?.category_id ?? "");
    })();
  }, []);

  useEffect(() => {
    if (!active) return;
    setLoading(true);
    api.products({ category: active }).then((p) => { setProducts(p); setLoading(false); }).catch(() => setLoading(false));
  }, [active]);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="kategori-screen">
      <View style={styles.header}>
        <Text style={styles.title}>Kategori</Text>
        <Pressable testID="header-search" onPress={() => router.push("/search" as any)} style={styles.iconBtn}>
          <Icon name="search" size={20} color={colors.onSurface} />
        </Pressable>
      </View>

      <View style={styles.body}>
        <ScrollView
          showsVerticalScrollIndicator={false}
          style={styles.sidebar}
          contentContainerStyle={{ paddingVertical: spacing.sm }}
        >
          {cats.map((c) => {
            const isActive = c.category_id === active;
            return (
              <Pressable
                key={c.category_id}
                testID={`sidebar-cat-${c.category_id}`}
                style={[styles.sideItem, isActive && styles.sideItemActive]}
                onPress={() => setActive(c.category_id)}
              >
                {isActive ? <View style={styles.sideIndicator} /> : null}
                <Icon name={c.icon as any} size={18} color={isActive ? colors.brandPrimary : colors.muted} />
                <Text style={[styles.sideName, isActive && styles.sideNameActive]} numberOfLines={2}>{c.name}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        <View style={styles.content}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
          ) : products.length === 0 ? (
            <View style={styles.empty}>
              <Icon name="bag-handle-outline" size={48} color={colors.muted} />
              <Text style={styles.emptyText}>Belum ada produk di kategori ini</Text>
            </View>
          ) : (
            <FlatList
              data={products}
              keyExtractor={(p) => p.product_id}
              numColumns={2}
              showsVerticalScrollIndicator={false}
              columnWrapperStyle={{ gap: CARD_GAP, paddingHorizontal: spacing.md }}
              contentContainerStyle={{ gap: CARD_GAP, paddingVertical: spacing.md, paddingBottom: spacing.xl }}
              renderItem={({ item }) => <ProductCard product={item} style={{ width: (screenW - 110 - spacing.md * 2 - CARD_GAP) / 2 }} />}
            />
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.xl, color: colors.onSurface, fontWeight: "500" },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  body: { flex: 1, flexDirection: "row" },
  sidebar: { width: 110, flexGrow: 0, flexShrink: 0, backgroundColor: colors.surfaceSecondary, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: colors.border },
  sideItem: {
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    alignItems: "center", gap: 6, position: "relative",
  },
  sideItemActive: { backgroundColor: colors.surface },
  sideIndicator: { position: "absolute", left: 0, top: 0, bottom: 0, width: 3, backgroundColor: colors.brandPrimary },
  sideName: { fontSize: 11, color: colors.muted, textAlign: "center" },
  sideNameActive: { color: colors.brandPrimary, fontWeight: "500" },
  content: { flex: 1 },
  empty: { alignItems: "center", gap: spacing.sm, paddingTop: spacing["2xl"] },
  emptyText: { color: colors.muted, fontSize: fontSize.sm },
});
