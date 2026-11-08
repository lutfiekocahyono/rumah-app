import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import type { Product } from "@/src/api";
import { useCart } from "@/src/cart-context";

export function ProductCard({ product, style }: { product: Product; style?: any }) {
  const router = useRouter();
  const { toggleWishlist, isWished } = useCart();
  const wished = isWished(product.product_id);
  return (
    <Pressable
      testID={`product-card-${product.product_id}`}
      style={[styles.card, style]}
      onPress={() => router.push(`/product/${product.product_id}` as any)}
    >
      <View style={styles.imgWrap}>
        <Image source={product.image} style={styles.img} contentFit="cover" transition={150} />
        {product.discount > 0 ? (
          <View style={styles.discountBadge}>
            <Text style={styles.discountText}>-{product.discount}%</Text>
          </View>
        ) : null}
        <Pressable
          testID={`wishlist-toggle-${product.product_id}`}
          style={styles.heart}
          hitSlop={8}
          onPress={() => toggleWishlist(product.product_id)}
        >
          <Icon name={wished ? "heart" : "heart-outline"} size={18} color={wished ? colors.brandPrimary : colors.onSurface} />
        </Pressable>
      </View>
      <View style={styles.info}>
        <Text style={styles.name} numberOfLines={2}>{product.name}</Text>
        <Text style={styles.price}>{formatIDR(product.my_price || product.price)}</Text>
        {product.original_price > (product.my_price || product.price) ? (
          <Text style={styles.oldPrice}>{formatIDR(product.original_price)}</Text>
        ) : null}
        {product.price_max > product.price_min ? (
          <Text style={styles.range} numberOfLines={1} testID={`price-range-${product.product_id}`}>
            {formatIDR(product.price_min)} - {formatIDR(product.price_max)}
          </Text>
        ) : null}
        {!product.in_stock ? <Text style={styles.oos}>Stok habis</Text> : null}
        <View style={styles.meta}>
          <Icon name="star" size={12} color={colors.warning} />
          <Text style={styles.metaText}>{product.rating.toFixed(1)}</Text>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    overflow: "hidden",
  },
  imgWrap: { aspectRatio: 1, width: "100%", backgroundColor: colors.surfaceTertiary, position: "relative" },
  img: { width: "100%", height: "100%" },
  discountBadge: {
    position: "absolute", top: spacing.sm, left: spacing.sm,
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  discountText: { color: colors.onBrandPrimary, fontSize: 10, fontWeight: "500" },
  heart: {
    position: "absolute", top: spacing.sm, right: spacing.sm,
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: "rgba(255,255,255,0.92)",
    alignItems: "center", justifyContent: "center",
  },
  info: { padding: spacing.md, gap: 4 },
  name: { fontSize: fontSize.sm, color: colors.onSurface, minHeight: 32 },
  price: { fontSize: fontSize.base, color: colors.brandPrimary, fontWeight: "500", marginTop: 2 },
  oldPrice: { fontSize: 11, color: colors.muted, textDecorationLine: "line-through" },
  range: { fontSize: 11, color: colors.onSurfaceSecondary },
  oos: { fontSize: 10, color: colors.error, fontWeight: "500" },
  meta: { flexDirection: "row", alignItems: "center", gap: 3, marginTop: 2 },
  metaText: { fontSize: 11, color: colors.muted },
  metaDot: { fontSize: 11, color: colors.muted, marginHorizontal: 2 },
});
