import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, ActivityIndicator } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, spacing } from "@/src/theme";
import { api, type FonnteStatus, type FonnteTest } from "@/src/api";
import { fmtDate } from "@/src/utils/date";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Field, PrimaryButton } from "@/src/components/admin-form";

const testText = (t: FonnteTest) => t.ok
  ? `Terhubung · perangkat ${t.device || "-"} (${t.device_status || "-"}) · kuota ${t.quota || "-"} · aktif s/d ${t.expired || "-"}`
  : `Gagal: ${t.reason || "token ditolak"}`;

/** Super Admin: token WhatsApp Fonnte untuk OTP & notifikasi pesanan, dengan uji koneksi dan uji kirim OTP. */
export default function AdminFonnte() {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<FonnteStatus | null>(null);
  const [token, setToken] = useState("");
  const [owner, setOwner] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [test, setTest] = useState<FonnteTest | null>(null);

  useEffect(() => { api.adminFonnte().then((x) => { setS(x); setOwner(x.owner_whatsapp); setPhone(x.owner_whatsapp); }).catch((e) => setMsg({ ok: false, text: e.message })); }, []);
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setMsg(null);
    try { await fn(); } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(""); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-fonnte-screen">
      <ScreenHeader title="WhatsApp Fonnte" />
      {!s ? (msg ? <Text style={[adminStyles.err, { margin: spacing.lg }]}>{msg.text}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />) : (
        <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
          <Card>
            <Text style={s.otp_mode === "asli" ? adminStyles.ok : adminStyles.err} testID="fonnte-mode">
              {s.otp_mode === "asli" ? "OTP dikirim sungguhan lewat WhatsApp." : "OTP masih mode uji: kode tampil di layar pembeli, tidak dikirim ke WhatsApp."}
            </Text>
            <Text style={adminStyles.muted} testID="fonnte-token-status">
              {s.has_token ? `Token tersimpan ${s.token_hint}${s.source === "env" ? " (dari pengaturan server)" : ""}` : "Token belum diisi."}
              {s.updated_at ? ` · diubah ${fmtDate(s.updated_at)}` : ""}
            </Text>
            {s.last_test ? <Text style={s.last_test.ok ? adminStyles.ok : adminStyles.err} testID="fonnte-last-test">Uji terakhir: {testText(s.last_test)}</Text> : null}
          </Card>
          <Card>
            <Field testID="fonnte-token" label="Token Fonnte" value={token} onChangeText={setToken} autoCapitalize="none" autoCorrect={false} secureTextEntry
              placeholder={s.has_token ? "Kosongkan bila tidak diganti" : "Tempel token dari fonnte.com → Device"}
              hint="Ambil di md.fonnte.com → menu Device → Token. Disimpan terenkripsi." />
            <Field testID="fonnte-owner" label="Nomor WhatsApp pemilik (notifikasi pesanan baru)" value={owner} onChangeText={setOwner} keyboardType="phone-pad" placeholder="08xxxxxxxxxx" />
            <PrimaryButton testID="fonnte-test" label="Uji koneksi" variant="outline" loading={busy === "test"} onPress={() => run("test", async () => {
              const t = await api.adminTestFonnte(token.trim());
              setTest(t);
              if (!token.trim()) setS(await api.adminFonnte());
            })} />
            {test ? <Text style={test.ok ? adminStyles.ok : adminStyles.err} testID="fonnte-test-result">{testText(test)}</Text> : null}
            <PrimaryButton testID="fonnte-save" label="Simpan" loading={busy === "save"} onPress={() => run("save", async () => {
              const body: { token?: string; owner_whatsapp?: string } = { owner_whatsapp: owner };
              if (token.trim()) body.token = token.trim();
              const x = await api.adminSetFonnte(body);
              setS(x); setToken(""); setOwner(x.owner_whatsapp);
              setMsg({ ok: true, text: "Pengaturan Fonnte disimpan" });
            })} />
            {s.has_token && s.source === "admin" ? (
              <PrimaryButton testID="fonnte-clear" label="Hapus token (kembali ke mode uji)" variant="danger" loading={busy === "clear"} onPress={() => run("clear", async () => {
                setS(await api.adminSetFonnte({ token: "" })); setTest(null);
                setMsg({ ok: true, text: "Token dihapus" });
              })} />
            ) : null}
          </Card>
          <Card>
            <Text style={adminStyles.section}>Uji kirim OTP</Text>
            <Field testID="fonnte-test-phone" label="Nomor WhatsApp tujuan" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="08xxxxxxxxxx" />
            <PrimaryButton testID="fonnte-test-otp" label="Kirim OTP uji" variant="outline" loading={busy === "otp"} onPress={() => run("otp", async () => {
              const r = await api.adminTestFonnteOtp(phone);
              setMsg({ ok: true, text: r.message });
            })} />
          </Card>
          {msg ? <Text style={msg.ok ? adminStyles.ok : adminStyles.err} testID={msg.ok ? "fonnte-msg-ok" : "fonnte-msg-error"}>{msg.text}</Text> : null}
        </KeyboardAwareScrollView>
      )}
    </View>
  );
}
