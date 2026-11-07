import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Dimensions } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Product } from "@/src/api";
import { useCart } from "@/src/cart-context";

const { width: screenW } = Dimensions.get("window");

export default function ProductDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { addToCart, toggleWishlist, isWished } = useCart();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [qty, setQty] = useState(1);
  const [imgIdx, setImgIdx] = useState(0);
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (!id) return;
    api.product(id).then((p) => { setProduct(p); setLoading(false); }).catch(() => setLoading(false));
  }, [id]);

  const handleAdd = async (goCart: boolean) => {
    if (!product) return;
    setAdding(true);
    try {
      await addToCart(product.product_id, qty);
      Haptics.notificationAsync?.(Haptics.NotificationFeedbackType.Success).catch(() => {});
      if (goCart) router.push("/(tabs)/keranjang" as any);
      else {
        setToast("Ditambahkan ke keranjang");
        setTimeout(() => setToast(""), 1500);
      }
    } finally {
      setAdding(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center} testID="product-loading"><ActivityIndicator color={colors.brandPrimary} /></View>
    );
  }
  if (!product) {
    return (
      <View style={[styles.center, { gap: spacing.md }]} testID="product-not-found">
        <Icon name="alert-circle-outline" size={48} color={colors.muted} />
        <Text style={styles.name}>Produk tidak ditemukan</Text>
        <Pressable testID="not-found-back" style={[styles.primaryBtn, { flex: 0, paddingHorizontal: spacing.xl }]} onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)" as any))}>
          <Text style={styles.primaryText}>Kembali</Text>
        </Pressable>
      </View>
    );
  }

  const images = product.images?.length ? product.images : [product.image];
  const wished = isWished(product.product_id);

  return (
    <View style={styles.root} testID="product-detail">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 120 }}>
        <View>
          <ScrollView
            horizontal
            pagingEnabled
            showsHorizontalScrollIndicator={false}
            onMomentumScrollEnd={(e) => setImgIdx(Math.round(e.nativeEvent.contentOffset.x / screenW))}
          >
            {images.map((src, i) => (
              <Image key={i} source={src} style={{ width: screenW, height: screenW }} contentFit="cover" />
            ))}
          </ScrollView>
          <View style={[styles.topRow, { top: insets.top + spacing.sm }]}>
            <Pressable testID="back-btn" hitSlop={8} onPress={() => router.back()} style={styles.topBtn}>
              <Icon name="chevron-back" size={22} color={colors.onSurface} />
            </Pressable>
            <View style={{ flex: 1 }} />
            <Pressable testID="pd-wishlist-btn" hitSlop={8} onPress={() => toggleWishlist(product.product_id)} style={styles.topBtn}>
              <Icon name={wished ? "heart" : "heart-outline"} size={20} color={wished ? colors.brandPrimary : colors.onSurface} />
            </Pressable>
          </View>
          {images.length > 1 ? (
            <View style={styles.imgDots}>{images.map((_, i) => <View key={i} style={[styles.imgDot, i === imgIdx && styles.imgDotActive]} />)}</View>
          ) : null}
        </View>

        <View style={styles.body}>
          <View style={styles.priceRow}>
            <Text style={styles.price}>{formatIDR(product.price)}</Text>
            {product.discount > 0 ? (
              <View style={styles.discountBadge}>
                <Text style={styles.discountText}>-{product.discount}%</Text>
              </View>
            ) : null}
            {product.original_price > product.price ? (
              <Text style={styles.oldPrice}>{formatIDR(product.original_price)}</Text>
            ) : null}
          </View>
          <Text style={styles.name}>{product.name}</Text>
          <View style={styles.meta}>
            <Icon name="star" size={14} color="#F59E0B" />
            <Text style={styles.metaText}>{product.rating.toFixed(1)}</Text>
            <Text style={styles.metaDot}>·</Text>
            <Text style={styles.metaText}>{product.sold} terjual</Text>
            <Text style={styles.metaDot}>·</Text>
            <Text style={styles.metaText}>Stok {product.stock}</Text>
          </View>

          <View style={styles.sep} />
          <Text style={styles.sectionTitle}>Deskripsi</Text>
          <Text style={styles.desc}>{product.description}</Text>

          <View style={styles.sep} />
          <Text style={styles.sectionTitle}>Jumlah</Text>
          <View style={styles.qtyRow}>
            <Pressable testID="qty-minus" style={styles.qtyBtn} onPress={() => setQty((q) => Math.max(1, q - 1))}>
              <Icon name="remove" size={16} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.qtyText}>{qty}</Text>
            <Pressable testID="qty-plus" style={styles.qtyBtn} onPress={() => setQty((q) => Math.min(product.stock, q + 1))}>
              <Icon name="add" size={16} color={colors.onSurface} />
            </Pressable>
          </View>

          <View style={styles.sep} />
          <View style={styles.infoRow}>
            <View style={styles.infoItem}>
              <Icon name="rocket" size={18} color={colors.brandPrimary} />
              <Text style={styles.infoText}>Pengiriman cepat dari Sidoarjo</Text>
            </View>
            <View style={styles.infoItem}>
              <Icon name="shield-checkmark" size={18} color={colors.brandPrimary} />
              <Text style={styles.infoText}>Garansi asli dari toko</Text>
            </View>
            <View style={styles.infoItem}>
              <Icon name="refresh" size={18} color={colors.brandPrimary} />
              <Text style={styles.infoText}>Pengembalian 7 hari</Text>
            </View>
          </View>
        </View>
      </ScrollView>

      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.md, insets.bottom + spacing.sm) }]}>
        <Pressable testID="add-to-cart-btn" style={styles.secondaryBtn} disabled={adding} onPress={() => handleAdd(false)}>
          <Icon name="cart-outline" size={20} color={colors.brandPrimary} />
          <Text style={styles.secondaryText}>Keranjang</Text>
        </Pressable>
        <Pressable testID="buy-now-btn" style={styles.primaryBtn} disabled={adding} onPress={() => handleAdd(true)}>
          <Text style={styles.primaryText}>Beli Sekarang</Text>
        </Pressable>
      </View>

      {toast ? (
        <View style={[styles.toast, { bottom: insets.bottom + 110 }]} testID="toast">
          <Icon name="checkmark-circle" size={18} color={colors.onSuccess} />
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },

  topRow: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", alignItems: "center" },
  topBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.95)",
    alignItems: "center", justifyContent: "center",
  },
  imgDots: { position: "absolute", bottom: spacing.sm, left: 0, right: 0, flexDirection: "row", justifyContent: "center", gap: 4 },
  imgDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "rgba(255,255,255,0.6)" },
  imgDotActive: { backgroundColor: colors.brandPrimary, width: 16 },

  body: { padding: spacing.lg },
  priceRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  price: { fontSize: 22, color: colors.brandPrimary, fontWeight: "500" },
  discountBadge: { backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2 },
  discountText: { color: colors.brandPrimary, fontSize: 11, fontWeight: "500" },
  oldPrice: { fontSize: fontSize.sm, color: colors.muted, textDecorationLine: "line-through" },
  name: { fontSize: fontSize.lg, color: colors.onSurface, marginTop: spacing.sm },
  meta: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.sm },
  metaText: { fontSize: fontSize.sm, color: colors.muted },
  metaDot: { color: colors.muted, marginHorizontal: 2 },

  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.lg },
  sectionTitle: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500", marginBottom: spacing.sm },
  desc: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, lineHeight: 20 },

  qtyRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  qtyBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  qtyText: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500", minWidth: 24, textAlign: "center" },

  infoRow: { gap: spacing.sm },
  infoItem: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  infoText: { color: colors.onSurfaceSecondary, fontSize: fontSize.sm },

  bottom: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: colors.surface,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border,
    padding: spacing.md, flexDirection: "row", gap: spacing.sm,
  },
  secondaryBtn: {
    flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center",
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
  },
  secondaryText: { color: colors.brandPrimary, fontWeight: "500" },
  primaryBtn: { flex: 1, backgroundColor: colors.brandPrimary, paddingVertical: 12, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },

  toast: {
    position: "absolute", alignSelf: "center",
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.success, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill,
  },
  toastText: { color: colors.onSuccess, fontSize: fontSize.sm, fontWeight: "500" },
});
