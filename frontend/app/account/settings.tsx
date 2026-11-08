import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type AccountSettings } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, ToggleRow } from "@/src/components/admin-form";

export default function Settings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [s, setS] = useState<AccountSettings | null>(null);
  const [askLogout, setAskLogout] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api.settings().then(setS).catch((e) => setErr(e.message)); }, []);

  const toggle = async (patch: Partial<AccountSettings>) => {
    if (!s) return;
    const next = { ...s, ...patch };
    setS(next);
    try { await api.saveSettings(next); } catch (e: any) { setErr(e.message); setS(s); }
  };

  const links = [
    { icon: "person-outline", label: "Edit Profil & Verifikasi", to: "/account/profile" },
    { icon: "lock-closed-outline", label: user?.has_password ? "Ubah Password" : "Buat Password", to: "/account/password" },
    { icon: "location-outline", label: "Alamat Pengiriman", to: "/account/addresses" },
    { icon: "time-outline", label: "Riwayat Aktivitas", to: "/account/activity" },
  ];

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="settings-screen">
      <ScreenHeader title="Pengaturan Akun" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
        <View style={styles.list}>
          {links.map((l) => (
            <Pressable key={l.to} testID={`settings-link-${l.to.split("/").pop()}`} style={styles.row} onPress={() => router.push(l.to as any)}>
              <Icon name={l.icon as any} size={20} color={colors.onSurface} />
              <Text style={styles.rowLabel}>{l.label}</Text>
              <Icon name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))}
        </View>
        <Text style={adminStyles.section}>Notifikasi di aplikasi</Text>
        {!s ? <ActivityIndicator color={colors.brandPrimary} /> : (
          <Card>
            <ToggleRow testID="set-notif-order" label="Status pesanan" sub="Pesanan dibuat, diproses, dikirim, selesai" value={s.notif_order} onChange={(v) => toggle({ notif_order: v })} />
            <ToggleRow testID="set-notif-promo" label="Promo & voucher" sub="Voucher baru dan penawaran" value={s.notif_promo} onChange={(v) => toggle({ notif_promo: v })} />
            <ToggleRow testID="set-notif-security" label="Keamanan akun" sub="Perubahan password, verifikasi" value={s.notif_security} onChange={(v) => toggle({ notif_security: v })} />
          </Card>
        )}
        {err ? <Text style={adminStyles.err}>{err}</Text> : null}
        <Pressable testID="settings-logout" style={styles.logout} onPress={() => setAskLogout(true)}>
          <Icon name="log-out-outline" size={20} color={colors.error} />
          <Text style={styles.logoutText}>Keluar dari akun</Text>
        </Pressable>
      </ScrollView>
      <ConfirmDialog visible={askLogout} title="Keluar dari akun?" confirmLabel="Keluar" onCancel={() => setAskLogout(false)}
        onConfirm={async () => { setAskLogout(false); await logout(); router.replace("/(tabs)/akun" as any); }} />
    </View>
  );
}

const styles = StyleSheet.create({
  list: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.md, minHeight: 52, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider },
  rowLabel: { flex: 1, fontSize: fontSize.base, color: colors.onSurface },
  logout: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error },
  logoutText: { color: colors.error, fontWeight: "500" },
});
