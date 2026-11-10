import React, { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, ScrollView, StyleSheet } from "react-native";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Brand } from "@/src/api";
import { SectionHeader } from "@/src/components/home-sections";

/** Merek Unggulan di Beranda: logo (atau huruf depan) yang membuka halaman merek. Diatur Super Admin. */
export function FeaturedBrands({ refreshKey }: { refreshKey: number }) {
  const router = useRouter();
  const [brands, setBrands] = useState<Brand[]>([]);
  const load = useCallback(() => { api.featuredBrands().then(setBrands).catch(() => setBrands([])); }, []);
  useEffect(load, [refreshKey, load]);
  useFocusEffect(load); // back from Admin → Unggulan: show the new order
  if (!brands.length) return null;
  return (
    <View testID="featured-brands">
      <SectionHeader title="Merek Unggulan" icon="ribbon-outline" />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {brands.map((b) => (
          <Pressable key={b.brand_id} testID={`featured-brand-${b.name}`} style={styles.item}
            onPress={() => router.push(`/brand/${encodeURIComponent(b.name)}` as any)}>
            <View style={styles.circle}>
              {b.logo ? <Image source={{ uri: imgUrl(b.logo) }} style={styles.logo} contentFit="contain" />
                : <Text style={styles.initial}>{b.name.slice(0, 1).toUpperCase()}</Text>}
            </View>
            <Text style={styles.name} numberOfLines={1}>{b.name}</Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  item: { width: 72, alignItems: "center", gap: 6 },
  circle: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", overflow: "hidden" },
  logo: { width: 52, height: 52, borderRadius: radius.sm },
  initial: { fontSize: 24, fontWeight: "700", color: colors.brandPrimary },
  name: { fontSize: fontSize.sm, color: colors.onSurface, textAlign: "center" },
});
