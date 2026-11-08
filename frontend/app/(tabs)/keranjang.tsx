import React from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Linking } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { useCart } from "@/src/cart-context";

const STORE_WHATSAPP = "6281335551252";

export default function Keranjang() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { cart, updateQty, removeItem } = useCart();

  const orderViaWhatsApp = () => {
    const lines = [
      "Halo Pusat Grosir Sidoarjo, saya mau pesan:",
      ...cart.items.map((i) => `- ${i.name} x${i.quantity} @ ${formatIDR(i.price)}`),
      `Subtotal: ${formatIDR(cart.subtotal)}`,
      "",
      "Nama:",
      "Alamat:",
    ];
    Linking.openURL(`https://wa.me/${STORE_WHATSAPP}?text=${encodeURIComponent(lines.join("\n"))}`);
  };

  const empty = cart.items.length === 0;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="keranjang-screen">
      <View style={styles.header}>
        <Text style={styles.title}>Keranjang</Text>
        <Text style={styles.subTitle}>{cart.item_count} item</Text>
      </View>

      {empty ? (
        <View style={styles.empty}>
          <View style={styles.emptyIconWrap}>
            <Icon name="cart-outline" size={48} color={colors.brandPrimary} />
          </View>
          <Text style={styles.emptyTitle}>Keranjang masih kosong</Text>
          <Text style={styles.emptyText}>Yuk mulai belanja kebutuhan rumahmu di Pusat Grosir Sidoarjo.</Text>
          <Pressable testID="empty-shop-btn" style={styles.shopBtn} onPress={() => router.push("/(tabs)" as any)}>
            <Text style={styles.shopBtnText}>Mulai Belanja</Text>
          </Pressable>
        </View>
      ) : (
        <>
          <FlatList
            data={cart.items}
            keyExtractor={(it) => it.product_id}
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 240 }}
            renderItem={({ item }) => (
              <View style={styles.row} testID={`cart-row-${item.product_id}`}>
                <Image source={item.image} style={styles.rowImg} contentFit="cover" />
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={styles.rowName} numberOfLines={2}>{item.name}</Text>
                  <View style={styles.priceLine}>
                    <Text style={styles.rowPrice} testID={`cart-unit-price-${item.product_id}`}>{formatIDR(item.price)}</Text>
                    {item.price < item.base_price ? <Text style={styles.basePrice}>{formatIDR(item.base_price)}</Text> : null}
                  </View>
                  {item.next_tier ? (
                    <Text style={styles.nextTier} testID={`cart-next-tier-${item.product_id}`}>
                      Beli {item.next_tier.min_qty - item.quantity} lagi → {formatIDR(item.next_tier.price)}/pcs
                    </Text>
                  ) : null}
                  <View style={styles.qtyRow}>
                    <Pressable
                      testID={`cart-minus-${item.product_id}`}
                      style={styles.qtyBtn}
                      onPress={() => updateQty(item.product_id, Math.max(0, item.quantity - 1))}
                    >
                      <Icon name="remove" size={14} color={colors.onSurface} />
                    </Pressable>
                    <Text style={styles.qtyText}>{item.quantity}</Text>
                    <Pressable
                      testID={`cart-plus-${item.product_id}`}
                      style={styles.qtyBtn}
                      onPress={() => updateQty(item.product_id, Math.min(item.stock, item.quantity + 1))}
                    >
                      <Icon name="add" size={14} color={colors.onSurface} />
                    </Pressable>
                    <View style={{ flex: 1 }} />
                    <Pressable testID={`cart-remove-${item.product_id}`} hitSlop={8} onPress={() => removeItem(item.product_id)}>
                      <Icon name="trash-outline" size={18} color={colors.muted} />
                    </Pressable>
                  </View>
                </View>
              </View>
            )}
          />
          <View style={[styles.summary, { paddingBottom: Math.max(spacing.lg, insets.bottom + spacing.sm) }]}>
            <View style={styles.sumRow}>
              <Text style={styles.sumLabel}>Subtotal</Text>
              <Text style={styles.sumValue}>{formatIDR(cart.subtotal)}</Text>
            </View>
            {cart.savings > 0 ? (
              <View style={styles.sumRow}>
                <Text style={[styles.sumLabel, { color: colors.success }]}>Sudah termasuk hemat harga bertingkat</Text>
                <Text style={[styles.sumValue, { color: colors.success }]} testID="cart-savings">{formatIDR(cart.savings)}</Text>
              </View>
            ) : null}
            <View style={styles.sumRow}>
              <Text style={styles.sumLabel}>Ongkos kirim</Text>
              <Text style={styles.sumValue}>{formatIDR(25000)}</Text>
            </View>
            <View style={[styles.sumRow, { marginTop: 4 }]}>
              <Text style={styles.totalLabel}>Total</Text>
              <Text style={styles.totalValue}>{formatIDR(cart.subtotal + 25000)}</Text>
            </View>
            <Pressable testID="checkout-btn" style={styles.checkoutBtn} onPress={() => router.push("/checkout" as any)}>
              <Text style={styles.checkoutText}>Checkout ({cart.item_count})</Text>
            </Pressable>
            <Pressable testID="whatsapp-order-btn" style={styles.waBtn} onPress={orderViaWhatsApp}>
              <Icon name="logo-whatsapp" size={18} color={colors.success} />
              <Text style={styles.waText}>Pesan via WhatsApp</Text>
            </Pressable>
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.xl, fontWeight: "500", color: colors.onSurface },
  subTitle: { fontSize: fontSize.sm, color: colors.muted, marginTop: 2 },

  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  emptyIconWrap: {
    width: 96, height: 96, borderRadius: 48,
    backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center",
  },
  emptyTitle: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  emptyText: { color: colors.muted, textAlign: "center", fontSize: fontSize.sm, maxWidth: 260 },
  shopBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.sm },
  shopBtnText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },

  row: { flexDirection: "row", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surface },
  rowImg: { width: 80, height: 80, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  rowName: { fontSize: fontSize.sm, color: colors.onSurface },
  rowPrice: { fontSize: fontSize.base, color: colors.brandPrimary, fontWeight: "500" },
  priceLine: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  basePrice: { fontSize: 11, color: colors.muted, textDecorationLine: "line-through" },
  nextTier: { fontSize: 11, color: colors.success },
  qtyRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: 4 },
  qtyBtn: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  qtyText: { minWidth: 20, textAlign: "center", color: colors.onSurface, fontWeight: "500" },

  summary: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: colors.surface,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border,
    padding: spacing.lg, gap: 6,
  },
  sumRow: { flexDirection: "row", justifyContent: "space-between" },
  sumLabel: { color: colors.muted, fontSize: fontSize.sm },
  sumValue: { color: colors.onSurface, fontSize: fontSize.sm },
  totalLabel: { color: colors.onSurface, fontSize: fontSize.base, fontWeight: "500" },
  totalValue: { color: colors.brandPrimary, fontSize: fontSize.lg, fontWeight: "500" },
  checkoutBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.sm },
  checkoutText: { color: colors.onBrandPrimary, fontSize: fontSize.base, fontWeight: "500" },
  waBtn: { flexDirection: "row", gap: 6, borderRadius: radius.pill, minHeight: 44, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.success },
  waText: { color: colors.success, fontSize: fontSize.base, fontWeight: "500" },
});
