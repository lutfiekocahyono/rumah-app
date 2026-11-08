import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, Linking } from "react-native";
import * as Clipboard from "expo-clipboard";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";

const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL ?? "").replace(/\/$/, "");
const DEV_AREA = "https://account.accurate.id/developer/application.do";

function CopyRow({ label, value, testID }: { label: string; value: string; testID: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => { await Clipboard.setStringAsync(value); setDone(true); setTimeout(() => setDone(false), 1500); };
  return (
    <View style={styles.copyRow}>
      <Text style={styles.copyLabel}>{label}</Text>
      <View style={styles.copyBox}>
        <Text style={styles.copyValue} selectable numberOfLines={2} testID={`${testID}-value`}>{value}</Text>
        <Pressable testID={testID} style={styles.copyBtn} onPress={copy} accessibilityLabel={`Salin ${label}`}>
          <Icon name={done ? "checkmark" : "copy-outline"} size={16} color={colors.onBrandPrimary} />
          <Text style={styles.copyBtnText}>{done ? "Tersalin" : "Salin"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

/** Langkah mendaftarkan aplikasi PGS di Area Developer Accurate, dengan alamat yang bisa disalin. */
export function AccurateGuide() {
  const [open, setOpen] = useState(true);
  const steps = [
    "Daftar aplikasi: buka Area Developer Accurate → Buat Aplikasi. Isi nama \"PGS Marketplace\", lalu tempel Alamat Aplikasi dan Alamat Callback di bawah.",
    "Pasang di Accurate Store: masuk sebagai Administrator database Anda → Accurate Store → Aplikasi Saya → pasang aplikasi PGS. Centang izin baca barang, gudang, harga & stok.",
    "Buat API Token: di Aplikasi Saya pilih aplikasi PGS → Buat API Token. Salin API Token dan Signature Secret.",
    "Tempel di halaman ini (bagian 1. Kunci API) → Simpan Kunci → Uji Koneksi.",
  ];
  return (
    <View style={styles.card} testID="accurate-guide">
      <Pressable style={styles.head} onPress={() => setOpen((o) => !o)} testID="accurate-guide-toggle">
        <Text style={styles.h}>Panduan pendaftaran aplikasi</Text>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
      </Pressable>
      {open ? (
        <>
          {steps.map((t, i) => (
            <View key={i} style={styles.step}>
              <View style={styles.num}><Text style={styles.numText}>{i + 1}</Text></View>
              <Text style={[styles.small, { flex: 1 }]}>{t}</Text>
            </View>
          ))}
          <CopyRow label="Alamat Aplikasi (App URL)" value={BASE} testID="accurate-copy-app" />
          <CopyRow label="Alamat Callback (Redirect URI)" value={`${BASE}/api/accurate/callback`} testID="accurate-copy-callback" />
          <Pressable testID="accurate-open-dev" onPress={() => Linking.openURL(DEV_AREA)} style={styles.link}>
            <Icon name="open-outline" size={16} color={colors.brandPrimary} />
            <Text style={styles.linkText}>Buka Area Developer Accurate</Text>
          </Pressable>
          <View style={styles.warn} testID="accurate-guide-note">
            <Icon name="alert-circle-outline" size={18} color={colors.warning} />
            <Text style={[styles.small, { flex: 1 }]}>
              Alamat di atas adalah alamat preview saat ini. Setelah aplikasi diluncurkan (Publish), halaman ini akan menampilkan alamat baru — ganti Alamat Aplikasi & Callback di Area Developer Accurate dengan alamat tersebut.
            </Text>
          </View>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 32 },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  small: { fontSize: 13, color: colors.onSurfaceSecondary },
  step: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  num: { width: 22, height: 22, borderRadius: 11, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  numText: { color: colors.onBrandPrimary, fontSize: 12, fontWeight: "700" },
  copyRow: { gap: 4, marginTop: spacing.xs },
  copyLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  copyBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingLeft: spacing.md, paddingVertical: 4, paddingRight: 4 },
  copyValue: { flex: 1, flexShrink: 1, minWidth: 0, fontSize: 12, color: colors.onSurface },
  copyBtn: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 40, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  copyBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  link: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 40 },
  linkText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  warn: { flexDirection: "row", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
});
