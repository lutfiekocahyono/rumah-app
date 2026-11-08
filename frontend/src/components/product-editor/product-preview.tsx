import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ScrollView } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { imgUrl, type Product, type ProductForm } from "@/src/api";
import { RichText } from "@/src/components/rich-text";
import { ProductSpecs } from "@/src/components/product-specs";

/** How the product page will look to buyers, built from the unsaved form. */
export function ProductPreview({ visible, form, storeName, onClose }: { visible: boolean; form: ProductForm; storeName: string; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const [img, setImg] = useState(0);
  const [picked, setPicked] = useState<Record<number, string>>({});
  useEffect(() => { if (visible) { setPicked({}); setImg(0); } }, [visible]); // every preview starts fresh
  const rows = form.variants_enabled ? form.variants.filter((r) => r.active) : [];
  const variant = rows.length && form.variant_options.every((_, i) => picked[i]) ? rows.find((r) => r.values.every((v, i) => v === picked[i])) : undefined;
  const price = variant ? variant.price : rows.length ? Math.min(...rows.map((r) => r.price)) : form.discount_price || form.price;
  const orig = !rows.length && form.discount_price ? form.price : 0;
  const stock = variant ? variant.stock : rows.length ? rows.reduce((t, r) => t + r.stock, 0) : form.stock;
  const images = variant?.image ? [variant.image, ...form.images.filter((x) => x !== variant.image)] : form.images;
  const asProduct = { ...form, store_name: storeName } as unknown as Product;
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={[styles.root, { paddingTop: insets.top }]} testID="pe-preview">
        <View style={styles.top}>
          <Text style={styles.badge}>PRATINJAU · belum tersimpan</Text>
          <Pressable testID="pe-preview-close" onPress={onClose} hitSlop={8} style={styles.close}><Icon name="close" size={24} color={colors.onSurface} /></Pressable>
        </View>
        <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl, maxWidth: 720, width: "100%", alignSelf: "center" }}>
          {images.length ? <Image source={imgUrl(images[Math.min(img, images.length - 1)])} style={styles.hero} contentFit="contain" /> : (
            <View style={[styles.hero, styles.noImg]}><Icon name="image-outline" size={40} color={colors.muted} /><Text style={styles.muted}>Belum ada foto</Text></View>
          )}
          {images.length > 1 ? (
            <ScrollView horizontal contentContainerStyle={{ gap: spacing.sm, padding: spacing.md }}>
              {images.map((u, i) => (
                <Pressable key={u + i} onPress={() => setImg(i)}><Image source={imgUrl(u)} style={[styles.thumb, i === img && { borderColor: colors.brandPrimary }]} /></Pressable>
              ))}
            </ScrollView>
          ) : null}
          <View style={styles.body}>
            <View style={{ flexDirection: "row", alignItems: "baseline", gap: spacing.sm, flexWrap: "wrap" }}>
              <Text style={styles.price} testID="pe-preview-price">{rows.length && !variant ? `Mulai ${formatIDR(price)}` : formatIDR(price)}</Text>
              {orig ? <Text style={styles.orig}>{formatIDR(orig)}</Text> : null}
              {orig ? <Text style={styles.off}>-{Math.round(((orig - price) / orig) * 100)}%</Text> : null}
            </View>
            <Text style={styles.name} testID="pe-preview-name">{form.name || "Nama produk"}</Text>
            <Text style={styles.muted}>{[storeName, `Stok ${stock}`, form.brand && `Merek ${form.brand}`, form.condition === "used" ? "Bekas" : "Baru", form.preorder && `Pre-order ${form.preorder_days} hari`].filter(Boolean).join(" · ")}</Text>
            {rows.length ? form.variant_options.map((o, oi) => (
              <View key={o.name + oi} style={{ gap: spacing.sm }}>
                <Text style={styles.h}>{o.name}{picked[oi] ? `: ${picked[oi]}` : ""}</Text>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                  {o.values.map((v) => (
                    <Pressable key={v} testID={`pe-preview-variant-${oi}-${v}`} onPress={() => { setPicked((p) => ({ ...p, [oi]: p[oi] === v ? "" : v })); setImg(0); }}
                      style={[styles.chip, picked[oi] === v && styles.chipOn]}>
                      <Text style={{ color: picked[oi] === v ? colors.brandPrimary : colors.onSurface, fontSize: fontSize.sm }}>{v}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            )) : null}
            <Text style={styles.h}>Deskripsi</Text>
            {form.description.trim() ? <RichText text={form.description} style={{ fontSize: fontSize.sm, color: colors.onSurfaceSecondary, lineHeight: 20 }} /> : <Text style={styles.muted}>Belum ada deskripsi</Text>}
            <ProductSpecs product={asProduct} />
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, minHeight: 52, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  badge: { flex: 1, color: colors.brandPrimary, fontWeight: "700", fontSize: 12 },
  close: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  hero: { width: "100%", aspectRatio: 1, backgroundColor: colors.surfaceSecondary },
  noImg: { alignItems: "center", justifyContent: "center", gap: 6 },
  thumb: { width: 56, height: 56, borderRadius: radius.sm, borderWidth: 2, borderColor: "transparent" },
  body: { padding: spacing.lg, gap: spacing.md },
  price: { fontSize: 22, fontWeight: "700", color: colors.brandPrimary },
  orig: { fontSize: fontSize.sm, color: colors.muted, textDecorationLine: "line-through" },
  off: { fontSize: 12, color: colors.error, fontWeight: "700" },
  name: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  muted: { fontSize: 13, color: colors.muted },
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, marginTop: spacing.sm },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, minHeight: 40, justifyContent: "center" },
  chipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
});
