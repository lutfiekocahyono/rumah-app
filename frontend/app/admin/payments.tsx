import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator, Linking, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type KeyStatus, type PaymentSettings } from "@/src/api";
import { fmtDate } from "@/src/utils/date";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Chips, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";
import { ConfirmDialog } from "@/src/components/confirm-dialog";

const NOTIF_URL = `${process.env.EXPO_PUBLIC_BACKEND_URL ?? ""}/api/payments/midtrans/notification`;

export default function AdminPaymentSettings() {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<PaymentSettings | null>(null);
  const [serverKey, setServerKey] = useState("");
  const [clientKey, setClientKey] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState({ err: "", ok: "" });
  const [askRemove, setAskRemove] = useState(false);

  useEffect(() => {
    api.paymentSettings().then((d) => { setS(d); setClientKey(d.client_key); }).catch((e) => setMsg({ err: e.message, ok: "" }));
  }, []);

  const save = async (what: string, server_key: string | null) => {
    if (!s) return;
    setBusy(what);
    setMsg({ err: "", ok: "" });
    try {
      const out = await api.savePaymentSettings({ enabled: s.enabled, production: s.production, server_key, client_key: clientKey.trim() });
      setS(out);
      setServerKey("");
      setMsg({ err: "", ok: server_key ? "Server Key disimpan dan sudah dicek" : server_key === "" ? "Server Key dihapus" : "Pengaturan pembayaran disimpan" });
    } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setBusy(""); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-payments-screen">
      <ScreenHeader title="Pengaturan Pembayaran" />
      {!s ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          <Text style={adminStyles.muted}>
            Pembayaran online Midtrans (QRIS, GoPay, ShopeePay, Virtual Account bank). Selama Server Key belum diisi, pembeli hanya
            melihat COD dan saldo. COD tetap pilihan awal di checkout.
          </Text>

          <Card>
            <Text style={adminStyles.section}>Mode</Text>
            <Chips testID="mt-mode" value={s.production ? "prod" : "sandbox"} onChange={(v) => setS({ ...s, production: v === "prod" })}
              options={[{ id: "sandbox", label: "Sandbox (uji coba)" }, { id: "prod", label: "Production (uang asli)" }]} />
            <Text style={adminStyles.muted}>
              {s.production ? "Production: pembeli membayar dengan uang asli. Pakai key dari dashboard Production." : "Sandbox: tidak ada uang asli. Pakai key dari dashboard Sandbox untuk uji coba."}
            </Text>
            <ToggleRow testID="mt-enabled" label="Tampilkan Midtrans di checkout" value={s.enabled} onChange={(v) => setS({ ...s, enabled: v })} />
          </Card>

          <Card>
            <Text style={adminStyles.section}>Kunci Midtrans</Text>
            <Text style={s.configured ? adminStyles.muted : adminStyles.err} testID="mt-key-status">
              {s.configured ? `Server Key tersimpan (${s.key_hint})` : "Server Key belum diisi — Midtrans belum tampil di checkout"}
            </Text>
            {s.configured ? <KeyStatusCard st={s.key_status} /> : null}
            <Field testID="mt-server-key" label={s.configured ? "Ganti Server Key" : "Server Key"} value={serverKey} onChangeText={setServerKey}
              secureTextEntry autoCapitalize="none" placeholder={s.production ? "Mid-server-…" : "SB-Mid-server-…"} hint="Rahasia. Disimpan terenkripsi dan tidak pernah ditampilkan lagi." />
            <PrimaryButton testID="mt-key-save" label="Simpan Server Key" loading={busy === "key"}
              onPress={() => (serverKey.trim().length < 10 ? setMsg({ err: "Server Key terlalu pendek", ok: "" }) : save("key", serverKey.trim()))} />
            {s.configured ? (
              <PrimaryButton testID="mt-key-verify" label="Cek Kunci Sekarang" variant="outline" loading={busy === "verify"} onPress={async () => {
                setBusy("verify");
                setMsg({ err: "", ok: "" });
                try { setS(await api.verifyMidtrans()); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setBusy(""); }
              }} />
            ) : null}
            {s.configured ? <PrimaryButton testID="mt-key-remove" label="Hapus Server Key" variant="danger" onPress={() => setAskRemove(true)} /> : null}
            {msg.err ? <Text style={adminStyles.err} testID="mt-key-error">{msg.err}</Text> : null}
            {msg.ok ? <Text style={adminStyles.ok} testID="mt-key-ok">{msg.ok}</Text> : null}
            <Field testID="mt-client-key" label="Client Key (opsional)" value={clientKey} onChangeText={setClientKey} autoCapitalize="none"
              placeholder={s.production ? "Mid-client-…" : "SB-Mid-client-…"} hint="Tidak rahasia; disimpan untuk kebutuhan nanti." />
          </Card>

          <Card>
            <Text style={adminStyles.section}>Langkah di dashboard Midtrans</Text>
            <Text style={styles.step}>1. Daftar gratis di dashboard.midtrans.com, lalu pilih environment {s.production ? "Production" : "Sandbox"}.</Text>
            <Text style={styles.step}>2. Buka Settings → Access Keys, salin Server Key ke kolom di atas.</Text>
            <Text style={styles.step}>3. Buka Settings → Configuration, isi Payment Notification URL dengan:</Text>
            <Text selectable style={styles.url} testID="mt-notif-url">{NOTIF_URL}</Text>
            <Pressable style={styles.link} onPress={() => Linking.openURL(s.production ? "https://dashboard.midtrans.com" : "https://dashboard.sandbox.midtrans.com")}>
              <Text style={{ color: colors.brandPrimary, fontSize: 13, fontWeight: "500" }}>Buka dashboard Midtrans {s.production ? "" : "Sandbox"}</Text>
            </Pressable>
          </Card>

          <PrimaryButton testID="mt-save" label="Simpan Pengaturan" loading={busy === "save"} onPress={() => save("save", null)} />
        </ScrollView>
      )}
      <ConfirmDialog visible={askRemove} title="Hapus Server Key Midtrans?" message="Midtrans langsung hilang dari checkout. Pembeli hanya bisa COD/saldo."
        confirmLabel="Hapus" loading={busy === "remove"} onCancel={() => setAskRemove(false)}
        onConfirm={async () => { await save("remove", ""); setAskRemove(false); }} />
    </KeyboardAvoidingView>
  );
}

const STATE_UI: Record<KeyStatus["state"], { icon: string; color: string; title: string }> = {
  valid: { icon: "checkmark-circle", color: colors.success, title: "Kunci valid" },
  invalid: { icon: "close-circle", color: colors.error, title: "Kunci tidak valid" },
  limited: { icon: "alert-circle", color: colors.warning, title: "Dibatasi Midtrans" },
  unknown: { icon: "help-circle", color: colors.muted, title: "Belum bisa dipastikan" },
};

function KeyStatusCard({ st }: { st: KeyStatus | null | undefined }) {
  if (!st) return <Text style={adminStyles.muted} testID="mt-key-check">Belum pernah dicek. Ketuk &quot;Cek Kunci Sekarang&quot;.</Text>;
  const ui = STATE_UI[st.state];
  return (
    <View style={[styles.badge, { borderColor: ui.color }]} testID="mt-key-check">
      <Icon name={ui.icon as any} size={20} color={ui.color} />
      <View style={{ flex: 1 }}>
        <Text style={styles.badgeTitle} testID={`mt-key-state-${st.state}`}>{ui.title}</Text>
        <Text style={adminStyles.muted}>{st.message}</Text>
        <Text style={styles.time}>Dicek {fmtDate(st.checked_at)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  step: { fontSize: fontSize.sm, color: colors.onSurface },
  url: { fontSize: 12, color: colors.onSurface, backgroundColor: colors.surfaceTertiary, padding: spacing.sm, borderRadius: radius.sm },
  link: { minHeight: 44, justifyContent: "center" },
  badge: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", borderWidth: 1, borderRadius: radius.sm, padding: spacing.sm, backgroundColor: colors.surface },
  badgeTitle: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  time: { fontSize: 11, color: colors.muted, marginTop: 2 },
});
