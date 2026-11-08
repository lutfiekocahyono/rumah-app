import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type StoreInfo } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

export default function Store() {
  const insets = useSafeAreaInsets();
  const [info, setInfo] = useState<StoreInfo | null>(null);

  useEffect(() => { api.store().then(setInfo).catch(() => {}); }, []);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="store-screen">
      <ScreenHeader title="Alamat & Kontak" />
      {!info ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
          <View style={styles.hero}>
            <Text style={styles.heroTitle}>{info.name}</Text>
            <Text style={styles.heroSub}>{info.tagline}</Text>
            <View style={styles.actions}>
              <Pressable testID="store-whatsapp-btn" style={styles.waBtn} onPress={() => Linking.openURL(`https://wa.me/${info.whatsapp}`)}>
                <Icon name="logo-whatsapp" size={18} color={colors.onSuccess} />
                <Text style={styles.waText}>WhatsApp</Text>
              </Pressable>
              <Pressable testID="store-call-btn" style={styles.callBtn} onPress={() => Linking.openURL(`tel:${info.phone.replace(/[^0-9+]/g, "")}`)}>
                <Icon name="call-outline" size={18} color={colors.brandPrimary} />
                <Text style={styles.callText}>{info.phone}</Text>
              </Pressable>
            </View>
          </View>

          <Text style={styles.section}>Jam Kerja</Text>
          <View style={styles.card}>
            {info.hours.map((h) => (
              <View key={h.day} style={styles.row}>
                <Text style={styles.rowLabel}>{h.day}</Text>
                <Text style={styles.rowValue}>{h.time}</Text>
              </View>
            ))}
          </View>

          <Text style={styles.section}>Lokasi Toko</Text>
          {info.branches.map((b, i) => (
            <View key={b.name} style={styles.card} testID={`branch-${i}`}>
              <Text style={styles.branchName}>{b.name}</Text>
              <Text style={styles.branchAddr}>{b.address}</Text>
              <View style={styles.branchActions}>
                <Pressable style={styles.linkBtn} onPress={() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${b.lat},${b.lng}`)}>
                  <Icon name="navigate-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.linkText}>Petunjuk Arah</Text>
                </Pressable>
                <Pressable style={styles.linkBtn} onPress={() => Linking.openURL(`tel:${b.phone.replace(/[^0-9+]/g, "")}`)}>
                  <Icon name="call-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.linkText}>{b.phone}</Text>
                </Pressable>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  hero: { backgroundColor: colors.brandPrimary, borderRadius: radius.md, padding: spacing.lg, gap: 4 },
  heroTitle: { color: colors.onBrandPrimary, fontSize: fontSize.xl, fontWeight: "500" },
  heroSub: { color: colors.onBrandPrimary, fontSize: fontSize.sm, opacity: 0.9 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  waBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.success, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill },
  waText: { color: colors.onSuccess, fontWeight: "500" },
  callBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surface, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill },
  callText: { color: colors.brandPrimary, fontWeight: "500" },
  section: { fontSize: fontSize.sm, color: colors.muted, marginTop: spacing.sm },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", justifyContent: "space-between" },
  rowLabel: { color: colors.onSurfaceSecondary, fontSize: fontSize.sm },
  rowValue: { color: colors.onSurface, fontSize: fontSize.sm, fontWeight: "500" },
  branchName: { color: colors.onSurface, fontSize: fontSize.base, fontWeight: "500" },
  branchAddr: { color: colors.onSurfaceSecondary, fontSize: fontSize.sm, lineHeight: 20 },
  branchActions: { flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 36 },
  linkText: { color: colors.brandPrimary, fontSize: fontSize.sm, fontWeight: "500" },
});
