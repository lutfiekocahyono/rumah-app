import React, { useState } from "react";
import { Text, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Field, PrimaryButton } from "@/src/components/admin-form";

export default function ChangePassword() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, setSession } = useAuth();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setErr("");
    if (user?.has_password && !cur) return setErr("Masukkan password saat ini");
    if (pw.length < 8) return setErr("Password baru minimal 8 karakter");
    if (pw !== pw2) return setErr("Konfirmasi password tidak sama");
    setBusy(true);
    try {
      const r = await api.changePassword(cur, pw);
      await setSession(r.token, r.user);
      if (router.canGoBack()) router.back();
      else router.replace("/account/settings" as any);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="password-screen">
      <ScreenHeader title={user?.has_password ? "Ubah Password" : "Buat Password"} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }} keyboardShouldPersistTaps="handled">
        <Card>
          {user?.has_password ? <Field testID="pw-current" label="Password saat ini" value={cur} onChangeText={setCur} secureTextEntry /> : (
            <Text style={adminStyles.muted}>Akun Google Anda belum punya password. Buat password agar bisa masuk dengan email juga.</Text>
          )}
          <Field testID="pw-new" label="Password baru (min. 8 karakter)" value={pw} onChangeText={setPw} secureTextEntry />
          <Field testID="pw-new2" label="Ulangi password baru" value={pw2} onChangeText={setPw2} secureTextEntry />
          {err ? <Text style={adminStyles.err} testID="pw-error">{err}</Text> : null}
          <PrimaryButton testID="pw-save" label="Simpan Password" onPress={save} loading={busy} />
          <Text style={adminStyles.muted}>Perangkat lain yang sedang login akan otomatis keluar.</Text>
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
