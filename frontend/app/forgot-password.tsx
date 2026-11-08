import React, { useState } from "react";
import { Text, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing } from "@/src/theme";
import { api } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Field, PrimaryButton } from "@/src/components/admin-form";

export default function ForgotPassword() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg({ err: "", ok: "" });
    try { await fn(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setBusy(false); }
  };

  const request = () => run(async () => {
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) throw new Error("Masukkan email yang valid");
    const r = await api.resetRequest(email.trim());
    setStep(2);
    setMsg({ err: "", ok: r.message });
  });

  const confirm = () => run(async () => {
    if (!/^\d{6}$/.test(code)) throw new Error("Kode berisi 6 angka");
    if (pw.length < 8) throw new Error("Password minimal 8 karakter");
    if (pw !== pw2) throw new Error("Konfirmasi password tidak sama");
    await api.resetConfirm(email.trim(), code, pw);
    router.replace("/login" as any);
  });

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="forgot-screen">
      <ScreenHeader title="Lupa Password" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }} keyboardShouldPersistTaps="handled">
        <Card>
          {step === 1 ? (
            <>
              <Text style={adminStyles.muted}>Masukkan email akun Anda. Kami kirim kode 6 angka untuk mengatur ulang password.</Text>
              <Field testID="forgot-email" label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="nama@email.com" />
              <PrimaryButton testID="forgot-send" label="Kirim Kode" onPress={request} loading={busy} />
            </>
          ) : (
            <>
              <Text style={adminStyles.muted}>Cek email {email}. Kode berlaku 10 menit.</Text>
              <Field testID="forgot-code" label="Kode verifikasi" value={code} onChangeText={(t) => setCode(t.replace(/\D/g, "").slice(0, 6))} keyboardType="number-pad" placeholder="123456" />
              <Field testID="forgot-new-pw" label="Password baru (min. 8 karakter)" value={pw} onChangeText={setPw} secureTextEntry />
              <Field testID="forgot-new-pw2" label="Ulangi password baru" value={pw2} onChangeText={setPw2} secureTextEntry />
              <PrimaryButton testID="forgot-confirm" label="Simpan Password Baru" onPress={confirm} loading={busy} />
              <PrimaryButton label="Kirim ulang kode" variant="outline" onPress={request} />
            </>
          )}
          {msg.err ? <Text style={adminStyles.err} testID="forgot-error">{msg.err}</Text> : null}
          {msg.ok ? <Text style={adminStyles.ok} testID="forgot-ok">{msg.ok}</Text> : null}
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
