import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type FlashSale, type HomeSettings, type Product, type Voucher } from "@/src/api";
import { ProductCard } from "@/src/components/product-card";
import { Countdown } from "@/src/components/countdown";

export function SectionHeader({ title, icon, right, testID }: { title: string; icon?: string; right?: React.ReactNode; testID?: string }) {
  return (
    <View style={styles.sectionHeader} testID={testID}>
      <View style={styles.titleRow}>
        {icon ? <Icon name={icon as any} size={18} color={colors.brandPrimary} /> : null}
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {right}
    </View>
  );
}

export const voucherValue = (v: Voucher) =>
  v.mode === "percent" ? `${v.value}%` : v.value >= 1000 ? `Rp${Math.round(v.value / 1000)}rb` : formatIDR(v.value);

/** `{kota}` in the subtitle becomes the city of the buyer's chosen branch. */
export function FreeShippingBanner({ s, city }: { s: HomeSettings["free_shipping"]; city?: string }) {
  if (!s.enabled) return null;
  const subtitle = s.subtitle.replace(/\{kota\}/gi, city || "cabang pilihan");
  return (
    <View style={styles.ongkir} testID="free-shipping-banner">
      <View style={styles.ongkirIcon}><Icon name="car-outline" size={22} color={colors.onSuccess} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.ongkirTitle}>{s.title}</Text>
        {subtitle ? <Text style={styles.ongkirSub} testID="free-shipping-subtitle">{subtitle}</Text> : null}
      </View>
    </View>
  );
}

export function FlashSaleSection({ flash, onEnd }: { flash: FlashSale; onEnd: () => void }) {
  const router = useRouter();
  if (!flash.active || !flash.items.length || !flash.ends_at) return null;
  return (
    <View style={styles.flashWrap} testID="flash-sale-section">
      <View style={styles.flashHead}>
        <View style={styles.titleRow}>
          <Icon name="flash" size={20} color={colors.brandPrimary} />
          <Text style={styles.flashTitle}>{flash.title}</Text>
        </View>
        <Countdown endsAt={flash.ends_at} onEnd={onEnd} testID="flash-countdown" />
      </View>
      <FlatList
        horizontal
        data={flash.items}
        keyExtractor={(p) => p.product_id}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.lg }}
        renderItem={({ item }) => {
          const fp = item.flash_price ?? item.my_price;
          const off = item.price > fp ? Math.round(((item.price - fp) / item.price) * 100) : 0;
          return (
            <Pressable testID={`flash-item-${item.product_id}`} style={styles.flashCard} onPress={() => router.push(`/product/${item.product_id}` as any)}>
              <View>
                <Image source={item.image} style={styles.flashImg} contentFit="cover" transition={150} />
                {off > 0 ? <View style={styles.offBadge}><Text style={styles.offText}>-{off}%</Text></View> : null}
              </View>
              <View style={{ padding: spacing.sm, gap: 2 }}>
                <Text style={styles.flashName} numberOfLines={2}>{item.name}</Text>
                <Text style={styles.flashPrice}>{formatIDR(fp)}</Text>
                {off > 0 ? <Text style={styles.strike}>{formatIDR(item.price)}</Text> : null}
              </View>
            </Pressable>
          );
        }}
      />
    </View>
  );
}

export function VoucherStrip({ vouchers, onChange }: { vouchers: Voucher[]; onChange: (v: Voucher) => void }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  if (!vouchers.length) return null;
  const claim = async (v: Voucher) => {
    setBusy(v.code);
    setErr("");
    try {
      onChange(await api.claimVoucher(v.code));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy("");
    }
  };
  return (
    <View>
      <SectionHeader title="Voucher Diskon" icon="ticket-outline" testID="voucher-section" />
      <FlatList
        horizontal
        data={vouchers}
        keyExtractor={(v) => v.code}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.lg }}
        renderItem={({ item: v }) => (
          <View style={styles.voucher} testID={`voucher-${v.code}`}>
            <View style={styles.voucherLeft}>
              <Text style={styles.voucherValue}>{voucherValue(v)}</Text>
              <Text style={styles.voucherOff}>OFF</Text>
            </View>
            <View style={styles.voucherBody}>
              <Text style={styles.voucherTitle} numberOfLines={1}>{v.title}</Text>
              <Text style={styles.voucherMeta} numberOfLines={1}>
                {v.min_purchase ? `Min. belanja ${formatIDR(v.min_purchase)}` : v.description || "Tanpa minimal belanja"}
              </Text>
              <View style={styles.voucherFoot}>
                <Text style={styles.voucherCode}>{v.code}</Text>
                <Pressable
                  hitSlop={8}
                  testID={`voucher-claim-${v.code}`}
                  disabled={v.claimed || busy === v.code}
                  onPress={() => claim(v)}
                  style={[styles.claimBtn, v.claimed && styles.claimedBtn]}
                >
                  {busy === v.code ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : (
                    <Text style={[styles.claimText, v.claimed && styles.claimedText]}>{v.claimed ? "Diklaim" : "Klaim"}</Text>
                  )}
                </Pressable>
              </View>
            </View>
          </View>
        )}
      />
      {err ? <Text style={styles.err}>{err}</Text> : null}
    </View>
  );
}

export function ProductRail({ title, icon, items, testID, onEndReached, loadingMore }: {
  title: string; icon: string; items: Product[]; testID: string; onEndReached?: () => void; loadingMore?: boolean;
}) {
  if (!items.length) return null;
  return (
    <View testID={testID}>
      <SectionHeader title={title} icon={icon} />
      <FlatList
        horizontal
        data={items}
        keyExtractor={(p) => p.product_id}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.lg }}
        renderItem={({ item }) => <ProductCard product={item} style={{ width: 160 }} />}
        onEndReached={onEndReached}
        onEndReachedThreshold={0.5}
        ListFooterComponent={loadingMore ? <View style={{ width: 60, alignSelf: "center" }}><ActivityIndicator color={colors.brandPrimary} /></View> : null}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  sectionHeader: {
    paddingHorizontal: spacing.lg, marginTop: spacing.xl, marginBottom: spacing.md,
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
  },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sectionTitle: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  err: { color: colors.error, fontSize: fontSize.sm, paddingHorizontal: spacing.lg, marginTop: spacing.sm },

  ongkir: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, marginHorizontal: spacing.lg, marginTop: spacing.lg,
    padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary,
    borderLeftWidth: 4, borderLeftColor: colors.success,
  },
  ongkirIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.success, alignItems: "center", justifyContent: "center" },
  ongkirTitle: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  ongkirSub: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },

  flashWrap: { marginTop: spacing.xl, paddingVertical: spacing.md, backgroundColor: colors.brandTertiary },
  flashHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  flashTitle: { fontSize: fontSize.lg, fontWeight: "700", color: colors.brandPrimary, fontStyle: "italic" },
  flashCard: { width: 130, backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden" },
  flashImg: { width: 130, height: 130, backgroundColor: colors.surfaceTertiary },
  offBadge: { position: "absolute", top: 6, left: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2 },
  offText: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "700" },
  flashName: { fontSize: 12, color: colors.onSurface, minHeight: 32 },
  flashPrice: { fontSize: fontSize.base, color: colors.brandPrimary, fontWeight: "700" },
  strike: { fontSize: 11, color: colors.muted, textDecorationLine: "line-through" },

  voucher: { width: 260, flexDirection: "row", backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary, overflow: "hidden" },
  voucherLeft: { width: 72, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingVertical: spacing.md },
  voucherValue: { color: colors.onBrandPrimary, fontSize: fontSize.lg, fontWeight: "700" },
  voucherOff: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "600" },
  voucherBody: { flex: 1, padding: spacing.sm, gap: 2 },
  voucherTitle: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  voucherMeta: { fontSize: 11, color: colors.muted },
  voucherFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  voucherCode: { fontSize: 11, fontWeight: "700", color: colors.brandPrimary, letterSpacing: 0.5 },
  claimBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 30, justifyContent: "center", minWidth: 64, alignItems: "center" },
  claimedBtn: { backgroundColor: colors.surfaceTertiary },
  claimText: { color: colors.onBrandPrimary, fontSize: 12, fontWeight: "600" },
  claimedText: { color: colors.muted },
});
