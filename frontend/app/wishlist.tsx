import React from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Dimensions } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, spacing } from "@/src/theme";
import { useCart } from "@/src/cart-context";
import { ProductCard } from "@/src/components/product-card";

const { width: screenW } = Dimensions.get("window");
const CARD_GAP = spacing.md;
const CARD_WIDTH = (screenW - spacing.lg * 2 - CARD_GAP) / 2;

export default function Wishlist() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { wishlist } = useCart();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="wishlist-screen">
      <View style={styles.header}>
        <Pressable testID="wl-back" hitSlop={8} onPress={() => router.back()}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Wishlist</Text>
        <View style={{ width: 24 }} />
      </View>
      {wishlist.length === 0 ? (
        <View style={styles.empty}>
          <Icon name="heart-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyText}>Belum ada produk disimpan</Text>
          <Pressable testID="wl-shop" style={styles.cta} onPress={() => router.replace("/(tabs)" as any)}>
            <Text style={styles.ctaText}>Mulai Belanja</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={wishlist}
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
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.xl },
  emptyText: { color: colors.muted, fontSize: fontSize.sm },
  cta: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: 12, borderRadius: 999, marginTop: spacing.sm },
  ctaText: { color: colors.onBrandPrimary, fontWeight: "500" },
});
