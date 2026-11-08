import React from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useStore } from "@/src/store-context";
import { useCart } from "@/src/cart-context";
import { ScreenHeader } from "@/src/components/screen-header";

export default function PickStore() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { stores, storeId, choose } = useStore();
  const { refresh } = useCart();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="pick-store-screen">
      <ScreenHeader title="Pilih Toko" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
        <Text style={styles.sub}>Pilih toko terdekat. Stok, harga, pesanan, dan pengiriman mengikuti toko yang dipilih.</Text>
        {!stores.length ? <ActivityIndicator color={colors.brandPrimary} /> : stores.map((s) => {
          const on = s.store_id === storeId;
          return (
            <Pressable key={s.store_id} testID={`pick-store-${s.store_id}`} style={[styles.card, on && styles.cardOn]}
              onPress={async () => {
                await choose(s.store_id);
                refresh();
                if (router.canGoBack()) router.back();
                else router.replace("/" as any);
              }}>
              <View style={[styles.icon, on && { backgroundColor: colors.brandPrimary }]}>
                <Icon name="storefront" size={22} color={on ? colors.onBrandPrimary : colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{s.name}</Text>
                <Text style={styles.city}>{s.city}</Text>
              </View>
              <Icon name={on ? "radio-button-on" : "radio-button-off"} size={22} color={on ? colors.brandPrimary : colors.muted} />
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  sub: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, minHeight: 72 },
  cardOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  icon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  name: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  city: { fontSize: 12, color: colors.muted },
});
