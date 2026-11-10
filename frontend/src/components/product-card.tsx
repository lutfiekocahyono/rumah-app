import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { imgUrl, type Product } from "@/src/api";
import { useCart } from "@/src/cart-context";

export function ProductCard({ product, style }: { product: Product; style?: any }) {
  const router = useRouter();
  const { toggleWishlist, isWished } = useCart();
  const wished = isWished(product.product_id);
  const tiers = product.price_tiers ?? [];
  // biggest per-pcs saving the current customer gets from wholesale tiers
  const saving = tiers.length > 1 ? tiers[0].price - Math.min(...tiers.map((t) => t.price)) : 0;
  return (
    <Pressable
      testID={`product-card-${product.product_id}`}
      style={[styles.card, style]}
      onPress={() => router.push(`/product/${product.product_id}` as any)}
    >
      <View style={styles.imgWrap}>
        <Image source={product.image} style={styles.img} contentFit="cover" transition={150} />
        {saving > 0 ? (
          <View style={styles.hematBadge} testID={`hemat-label-${product.product_id}`}>
            <Text style={styles.hematText}>Hemat {formatIDR(saving)}/pcs</Text>
          </View>
        ) : product.discount > 0 ? (
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
        {product.brand_logo ? (
          <View style={styles.meta} testID={`card-brand-${product.product_id}`}>
            <Image source={{ uri: imgUrl(product.brand_logo) }} style={styles.brandLogo} contentFit="contain" />
            <Text style={styles.store} numberOfLines={1}>{product.brand}</Text>
          </View>
        ) : null}
        {product.store_name ? (
          <View style={styles.meta}>
            <Icon name={product.store_id === "pgs-official" ? "shield-checkmark" : "storefront-outline"} size={12} color={colors.brandPrimary} />
            <Text style={styles.store} numberOfLines={1}>{product.store_name}</Text>
          </View>
        ) : null}
        <View style={styles.meta}>
          <Icon name={product.in_stock ? "checkmark" : "close"} size={14} color={product.in_stock ? colors.onSurfaceSecondary : colors.error} />
          <Text style={[styles.metaText, !product.in_stock && { color: colors.error }]} testID={`stock-${product.product_id}`}>
            {!product.in_stock ? "Stok habis" : product.stock >= 9999 ? "Stok tersedia" : `${product.stock} stok tersedia`}
          </Text>
        </View>
        <Text style={styles.range} numberOfLines={1} adjustsFontSizeToFit testID={`price-range-${product.product_id}`}>
          {product.price_max > product.price_min
            ? `${formatIDR(product.price_min)} - ${formatIDR(product.price_max)}`
            : formatIDR(product.my_price || product.price)}
        </Text>
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
  hematBadge: {
    position: "absolute", left: spacing.sm, bottom: spacing.sm,
    backgroundColor: colors.success, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 3,
  },
  hematText: { color: colors.onSuccess, fontSize: 11, fontWeight: "600" },
  heart: {
    position: "absolute", top: spacing.sm, right: spacing.sm,
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: "rgba(255,255,255,0.92)",
    alignItems: "center", justifyContent: "center",
  },
  info: { padding: spacing.md, gap: 4 },
  name: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500", minHeight: 36 },
  range: { fontSize: fontSize.sm, color: colors.priceLink, fontWeight: "500", marginTop: 2 },
  meta: { flexDirection: "row", alignItems: "center", gap: 3, marginTop: 2 },
  metaText: { fontSize: 12, color: colors.onSurfaceSecondary },
  store: { fontSize: 11, color: colors.muted, flex: 1 },
  brandLogo: { width: 16, height: 16, borderRadius: 3 },
});
