import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, spacing } from "@/src/theme";
import { api, type PushStatus } from "@/src/api";
import { fmtDate } from "@/src/utils/date";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, ToggleRow } from "@/src/components/admin-form";

const RESULT: Record<string, string> = {
  sent: "terkirim", "key-invalid": "kunci push belum aktif", insufficient_credits: "kredit Emergent habis",
  integration_disabled: "integrasi dimatikan di Emergent", daily_limit_reached: "batas harian tercapai", error: "gagal", "no-recipients": "tanpa penerima",
};

/** Super Admin: nyalakan / matikan push HP untuk ringkasan info produk. Default nonaktif. */
export default function AdminPush() {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<PushStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api.adminPush().then(setS).catch((e) => setErr(e.message)); }, []);
  const toggle = async (v: boolean) => {
    setBusy(true); setErr("");
    try { setS(await api.adminSetPush(v)); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-push-screen">
      <ScreenHeader title="Notifikasi Push HP" />
      {!s ? (err ? <Text style={[adminStyles.err, { margin: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
          <Text style={adminStyles.muted}>
            Ringkasan info produk (produk baru, harga, stok, keterangan — maks. 1x per jam) juga dikirim sebagai notifikasi push ke HP pembeli.
            Push hanya bekerja di aplikasi versi Android/iOS hasil build, bukan di preview web atau Expo Go.
          </Text>
          <Card>
            <ToggleRow testID="push-enabled" label="Kirim push info produk" sub={busy ? "Menyimpan…" : s.enabled ? "Aktif" : "Nonaktif — lonceng & email tetap jalan"}
              value={s.enabled} onChange={toggle} />
            <Text style={s.key_ready ? adminStyles.muted : adminStyles.err} testID="push-key-status">
              {s.key_ready ? "Kunci layanan push sudah aktif." : "Kunci layanan push belum aktif — otomatis aktif setelah aplikasi dirilis (Publish → Deploy)."}
            </Text>
            <Text style={adminStyles.muted} testID="push-devices">HP terdaftar: {s.devices}</Text>
            {s.last_send ? (
              <Text style={adminStyles.muted} testID="push-last">
                Terakhir: {fmtDate(s.last_send.at)} · {s.last_send.title} · {Object.entries(s.last_send.result).map(([k, n]) => `${n} ${RESULT[k] ?? k}`).join(", ")}
              </Text>
            ) : null}
          </Card>
          <Card>
            <Text style={adminStyles.section}>Langkah sebelum mengaktifkan</Text>
            <Text style={adminStyles.muted}>1. Buat akun & proyek Firebase (gratis) di console.firebase.google.com, tambahkan aplikasi Android dengan nama paket com.emergent.rumahapp.mqe765, lalu unduh google-services.json dan kirim ke saya di chat.</Text>
            <Text style={adminStyles.muted}>2. Klik Publish → Deploy, lalu buat versi Android/iOS. Saat itu Anda diminta mengunggah Google service account JSON (Android) dan kunci Apple .p8 (iOS) — panduannya ada di layar build.</Text>
            <Text style={adminStyles.muted}>3. Setelah aplikasi terpasang di HP, nyalakan tombol di atas. Pembeli akan diminta izin notifikasi saat membuka aplikasi.</Text>
          </Card>
          {err ? <Text style={adminStyles.err}>{err}</Text> : null}
        </ScrollView>
      )}
    </View>
  );
}
