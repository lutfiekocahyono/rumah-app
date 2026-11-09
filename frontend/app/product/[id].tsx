import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Dimensions, Platform, Share } from "react-native";
import * as Clipboard from "expo-clipboard";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, CUSTOMER_TYPE_LABEL, type Product } from "@/src/api";
import { useCart } from "@/src/cart-context";
import { useAuth } from "@/src/auth-context";
import { Countdown } from "@/src/components/countdown";
import { BranchAvailability } from "@/src/components/branch-availability";
import { RichText } from "@/src/components/rich-text";
import { ProductSpecs } from "@/src/components/product-specs";
import { useStore } from "@/src/store-context";

const { width: screenW } = Dimensions.get("window");

const OK_TOASTS = ["Ditambahkan ke keranjang", "Toko diganti", "Tautan produk disalin"]; // anything else is an error message

export default function ProductDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { addToCart, toggleWishlist, isWished, refresh } = useCart();
  const { storeId, ready } = useStore();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [qty, setQty] = useState(1);
  const [imgIdx, setImgIdx] = useState(0);
  const [adding, setAdding] = useState(false);
  const [chatting, setChatting] = useState(false);
  // chat with the branch the buyer picked (shared catalogue) or the product's own store
  const openChat = async () => {
    if (!product) return;
    if (!user) { router.push("/login" as any); return; }
    setChatting(true);
    try {
      const c = await api.startChat(product.store_id === "pgs-official" ? storeId : product.store_id, product.product_id);
      router.push(`/chat/${c.conv_id}` as any);
    } catch (e: any) {
      setToast(e.message);
      setTimeout(() => setToast(""), 2500);
    } finally { setChatting(false); }
  };
  const [toast, setToast] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [picked, setPicked] = useState<Record<number, string>>({}); // option index -> chosen value
  const { toko } = useLocalSearchParams<{ toko?: string }>();
  const { choose, stores } = useStore();
  const showToast = (t: string) => { setToast(t); setTimeout(() => setToast(""), 2500); };

  // shared link ?toko=<branch>: open the product with the sender's branch (prices & stock follow it)
  useEffect(() => {
    if (ready && toko && toko !== storeId && stores.some((s) => s.store_id === toko)) void choose(toko).then(() => showToast("Toko diganti"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, toko, stores.length]);

  const share = async () => {
    if (!product) return;
    const base = Platform.OS === "web" ? window.location.origin : process.env.EXPO_PUBLIC_BACKEND_URL;
    const url = `${base}/product/${encodeURIComponent(product.product_id)}?toko=${encodeURIComponent(storeId)}`;
    const text = `${product.name} - ${formatIDR(product.my_price ?? product.price)}`;
    try {
      if (Platform.OS !== "web") { await Share.share({ message: `${text}\n${url}`, url, title: product.name }); return; }
      const nav: any = typeof navigator !== "undefined" ? navigator : null;
      const touch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
      if (touch && nav?.share) { await nav.share({ title: product.name, text, url }); return; }
      await Clipboard.setStringAsync(url);
      showToast("Tautan produk disalin");
    } catch (e: any) {
      if (e?.name !== "AbortError") showToast("Gagal membagikan, coba lagi");
    }
  };

  useEffect(() => {
    if (!id || !ready) return; // wait for the saved branch: prices follow it
    api.product(id).then((p) => {
      setProduct(p); setQty(Math.max(1, p.min_order ?? 1)); setLoading(false);
      // options with a single choice are picked automatically
      setPicked(Object.fromEntries((p.variant_options ?? []).map((o, i) => [i, o.values.length === 1 ? o.values[0] : ""]).filter(([, v]) => v)));
    }).catch(() => setLoading(false));
  }, [id, reloadKey, ready, storeId]);
  useEffect(() => { if (id) api.trackView(id).catch(() => {}); }, [id]);

  const handleAdd = async (goCart: boolean) => {
    if (!product) return;
    if (hasVariants && !variant) {
      setToast("Pilih variasi dulu");
      setTimeout(() => setToast(""), 2000);
      return;
    }
    setAdding(true);
    try {
      const err = await addToCart(product.product_id, qty, variant?.variant_id);
      if (err) {
        setToast(err);
        setTimeout(() => setToast(""), 2000);
        return;
      }
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

  const tiers = product?.variants?.length ? [] : product?.price_tiers ?? [];
  const myType = user?.customer_type ?? "langsung";
  const options = product?.variant_options ?? [];
  const hasVariants = !!product?.variants?.length;
  const variant = hasVariants && options.every((_, i) => picked[i])
    ? product!.variants!.find((v) => v.values.every((x, i) => x === picked[i])) ?? null : null;
  const maxQty = Math.max(1, Math.min(variant ? variant.stock : product?.stock ?? 1, product?.max_order || Infinity));
  const tierUnit = variant ? variant.price : tiers.reduce((p, t) => (qty >= t.min_qty ? t.price : p), product?.my_price ?? product?.price ?? 0);
  const flashPrice = hasVariants ? null : product?.flash_price ?? null;
  // the branch's flash price replaces the normal price; only a grosir tier (buy more) can go lower
  const unit = flashPrice ? Math.min(flashPrice, ...tiers.filter((t) => t.min_qty > 1 && qty >= t.min_qty).map((t) => t.price)) : tierUnit;

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

  const images = variant?.image ? [variant.image, ...(product.images ?? []).filter((x) => x !== variant.image)] : product.images?.length ? product.images : [product.image];
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
            <Pressable testID="pd-share-btn" hitSlop={8} onPress={share} style={styles.topBtn} accessibilityLabel="Bagikan produk">
              <Icon name="share-social-outline" size={20} color={colors.onSurface} />
            </Pressable>
            <Pressable testID="pd-wishlist-btn" hitSlop={8} onPress={() => toggleWishlist(product.product_id)} style={styles.topBtn}>
              <Icon name={wished ? "heart" : "heart-outline"} size={20} color={wished ? colors.brandPrimary : colors.onSurface} />
            </Pressable>
          </View>
          {images.length > 1 ? (
            <View style={styles.imgDots}>{images.map((_, i) => <View key={i} style={[styles.imgDot, i === imgIdx && styles.imgDotActive]} />)}</View>
          ) : null}
        </View>

        {flashPrice && product.flash_ends_at ? (
          <View style={styles.flashBar} testID="pd-flash-bar">
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <Icon name="flash" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.flashBarText}>Flash Sale {formatIDR(flashPrice)}</Text>
            </View>
            <View style={styles.flashTimer}>
              <Text style={styles.flashEnds}>Berakhir</Text>
              <Countdown endsAt={product.flash_ends_at} onEnd={() => setProduct((p) => (p ? { ...p, flash_price: null } : p))} />
            </View>
          </View>
        ) : null}

        <View style={styles.body}>
          <View style={styles.priceRow}>
            <Text style={styles.price} testID="pd-unit-price">{hasVariants && !variant ? `Mulai ${formatIDR(product.price)}` : formatIDR(unit)}</Text>
            {unit < product.price ? (
              <Text style={styles.oldPrice}>{formatIDR(product.price)}</Text>
            ) : null}
          </View>
          <Text style={styles.ctypeText} testID="pd-customer-type">
            Harga untuk {CUSTOMER_TYPE_LABEL[user?.customer_type ?? "langsung"]} · per pcs
          </Text>
          {product.price_max > product.price_min ? (
            <Text style={styles.rangeText} testID="pd-price-range">
              Rentang harga {formatIDR(product.price_min)} - {formatIDR(product.price_max)}
            </Text>
          ) : null}
          <Text style={styles.name}>{product.name}</Text>
          {product.store_name ? (
            <Pressable testID="pd-store-link" style={styles.meta} onPress={() => router.push(`/shop/${product.store_id === "pgs-official" ? storeId : product.store_id}` as any)}>
              <Icon name="storefront-outline" size={14} color={colors.brandPrimary} />
              <Text style={[styles.metaText, { color: colors.brandPrimary }]}>{product.store_name}</Text>
              <Icon name="chevron-forward" size={14} color={colors.brandPrimary} />
            </Pressable>
          ) : null}
          <View style={styles.meta}>
            <Icon name="star" size={14} color={colors.warning} />
            <Text style={styles.metaText}>{product.rating.toFixed(1)}</Text>
            <Text style={styles.metaDot}>·</Text>
            <Text style={[styles.metaText, !product.in_stock && { color: colors.error }]}>
              {variant ? (variant.stock > 0 ? `Stok ${variant.stock}` : "Stok variasi habis") : product.in_stock ? `Stok ${product.stock >= 9999 ? "tersedia" : product.stock}` : "Stok habis"}
            </Text>
          </View>
          {product.brand || product.condition === "used" ? (
            <Text style={styles.metaText} testID="pd-brand">{[product.brand && `Merek ${product.brand}`, product.condition === "used" ? "Bekas" : "Baru"].filter(Boolean).join(" · ")}</Text>
          ) : null}
          {product.preorder ? (
            <Text style={[styles.metaText, { color: colors.brandPrimary, fontWeight: "600" }]} testID="pd-preorder">Pre-order · dikirim dalam {product.preorder_days} hari</Text>
          ) : (product.processing_days ?? 0) > 1 ? (
            <Text style={styles.metaText} testID="pd-processing">Diproses dalam {product.processing_days} hari</Text>
          ) : null}

          {hasVariants ? (
            <View style={{ marginTop: spacing.md, gap: spacing.md }} testID="pd-variants">
              {options.map((o, oi) => (
                <View key={o.name} style={{ gap: spacing.sm }}>
                  <Text style={styles.sectionTitle}>{o.name}{picked[oi] ? `: ${picked[oi]}` : ""}</Text>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                    {o.values.map((val) => {
                      // a value is selectable when some active variant with the other picks has it in stock
                      const ok = product.variants!.some((v) => v.values[oi] === val && v.stock > 0 && v.values.every((x, i) => i === oi || !picked[i] || x === picked[i]));
                      const on = picked[oi] === val;
                      return (
                        <Pressable key={val} testID={`pd-variant-${oi}-${val}`} disabled={!ok && !on}
                          onPress={() => { setPicked((p) => ({ ...p, [oi]: on ? "" : val })); setQty(Math.max(1, product.min_order ?? 1)); setImgIdx(0); }}
                          style={[styles.vChip, on && styles.vChipOn, !ok && !on && { opacity: 0.4 }]}>
                          <Text style={[styles.vChipText, on && { color: colors.brandPrimary, fontWeight: "600" }]}>{val}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>
              ))}
            </View>
          ) : null}

          {product.store_id === "pgs-official" ? (
            <View style={{ marginTop: spacing.md }}>
              <BranchAvailability productId={product.product_id} onSwitched={() => { setQty(1); setReloadKey((k) => k + 1); refresh(); setToast("Toko diganti"); }} />
            </View>
          ) : null}

          {tiers.length > 1 ? (
            <>
              <View style={styles.sep} />
              <Text style={styles.sectionTitle}>Harga Grosir</Text>
              <View style={styles.gTable} testID="price-matrix-table">
                <View style={styles.gRow}>
                  <Text style={[styles.gQty, styles.gHead]}>JUMLAH BELI</Text>
                  <Text style={[styles.gDisc, styles.gHead]}>HEMAT (%)</Text>
                  <Text style={[styles.gPrice, styles.gHead]}>HARGA</Text>
                </View>
                {tiers.map((t, i) => {
                  const next = tiers[i + 1];
                  const active = qty >= t.min_qty && (!next || qty < next.min_qty);
                  const base = tiers[0].price;
                  const pct = base > 0 ? ((base - t.price) / base) * 100 : 0;
                  return (
                    <Pressable key={t.min_qty} testID={`matrix-row-${t.min_qty}`} style={[styles.gRow, active && styles.gRowActive]}
                      onPress={() => setQty(Math.min(product.stock, t.min_qty))}>
                      <Text style={[styles.gQty, styles.gCell, active && styles.gActiveText]}>
                        {next ? (next.min_qty - 1 > t.min_qty ? `${t.min_qty} - ${next.min_qty - 1}` : `${t.min_qty}`) : `${t.min_qty}+`}
                      </Text>
                      <Text style={[styles.gDisc, styles.gCell, active && styles.gActiveText]}>
                        {i === 0 || pct <= 0 ? "—" : `${pct.toFixed(2).replace(/\.?0+$/, "")} %`}
                      </Text>
                      <Text style={[styles.gPrice, styles.gPriceText, active && styles.gActiveText]} numberOfLines={1} adjustsFontSizeToFit>
                        {formatIDR(t.price)}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              <Text style={styles.ctypeText}>Harga untuk {CUSTOMER_TYPE_LABEL[myType]} · ketuk baris untuk pilih jumlah</Text>
            </>
          ) : null}

          <View style={styles.sep} />
          <Text style={styles.sectionTitle}>Deskripsi</Text>
          <RichText text={product.description} style={styles.desc} />
          <ProductSpecs product={product} />

          <View style={styles.sep} />
          <Text style={styles.sectionTitle}>Jumlah</Text>
          <View style={styles.qtyRow}>
            <Pressable testID="qty-minus" style={styles.qtyBtn} onPress={() => setQty((q) => Math.max(product.min_order ?? 1, q - 1))}>
              <Icon name="remove" size={16} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.qtyText} testID="qty-value">{qty}</Text>
            <Pressable testID="qty-plus" style={styles.qtyBtn} onPress={() => setQty((q) => Math.min(maxQty, q + 1))}>
              <Icon name="add" size={16} color={colors.onSurface} />
            </Pressable>
            <View style={{ flex: 1 }} />
            <Text style={styles.subtotal} testID="pd-subtotal">Subtotal {formatIDR(unit * qty)}</Text>
          </View>

          <View style={styles.sep} />
          <View style={styles.infoRow}>
            <View style={styles.infoItem}>
              <Icon name="rocket" size={18} color={colors.brandPrimary} />
              <Text style={styles.infoText}>{product.preorder ? `Pre-order ${product.preorder_days} hari` : `Dikirim dari ${product.store_name}`}</Text>
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
        <Pressable testID="pd-chat-btn" style={styles.chatBtn} disabled={chatting} onPress={openChat} accessibilityLabel="Chat toko">
          {chatting ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="chatbubble-ellipses-outline" size={22} color={colors.brandPrimary} />}
          <Text style={styles.chatText}>Chat</Text>
        </Pressable>
        <Pressable testID="add-to-cart-btn" style={styles.secondaryBtn} disabled={adding} onPress={() => handleAdd(false)}>
          <Icon name="cart-outline" size={20} color={colors.brandPrimary} />
          <Text style={styles.secondaryText}>Keranjang</Text>
        </Pressable>
        <Pressable testID="buy-now-btn" style={styles.primaryBtn} disabled={adding} onPress={() => handleAdd(true)}>
          <Text style={styles.primaryText}>Beli Sekarang</Text>
        </Pressable>
      </View>

      {toast ? (
        <View style={[styles.toast, { bottom: insets.bottom + 110 }, !OK_TOASTS.includes(toast) && { backgroundColor: colors.error }]} testID="toast">
          <Icon name={OK_TOASTS.includes(toast) ? "checkmark-circle" : "alert-circle"} size={18} color={colors.onSuccess} />
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  flashBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  flashBarText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: fontSize.base },
  flashTimer: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surface, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 3 },
  flashEnds: { fontSize: 11, color: colors.onSurface },
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
  price: { fontSize: 22, color: colors.priceLink, fontWeight: "600" },
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
  vChip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, minHeight: 40, justifyContent: "center" },
  vChipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  vChipText: { fontSize: fontSize.sm, color: colors.onSurface },

  qtyRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  subtotal: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  ctypeText: { fontSize: 11, color: colors.muted, marginTop: 2 },
  tierActiveText: { color: colors.brandPrimary },
  rangeText: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  gTable: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  gRow: { flexDirection: "row", alignItems: "center", minHeight: 44, paddingHorizontal: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  gRowActive: { backgroundColor: colors.priceLink, borderBottomColor: colors.priceLink },
  gHead: { fontSize: 12, color: colors.onSurface, fontWeight: "600", letterSpacing: 0.5 },
  gCell: { fontSize: fontSize.sm, color: colors.muted },
  gQty: { flex: 1 },
  gDisc: { flex: 1.3 },
  gPrice: { flex: 1.2 },
  gPriceText: { fontSize: fontSize.sm, color: colors.priceLink, fontWeight: "600" },
  gActiveText: { color: colors.onBrandPrimary },
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
  chatBtn: { width: 56, minHeight: 48, alignItems: "center", justifyContent: "center", gap: 2, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  chatText: { fontSize: 11, color: colors.brandPrimary, fontWeight: "600" },
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
