import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useAuth } from "@/src/auth-context";

export default function Register() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setErr("");
    if (!name.trim() || !email.trim() || password.length < 6) {
      setErr("Lengkapi nama, email, dan password min. 6 karakter");
      return;
    }
    setLoading(true);
    try {
      await register(email.trim(), password, name.trim());
      if (router.canGoBack()) router.back();
      else router.replace("/(tabs)/akun" as any);
    } catch (e: any) {
      setErr(e?.message || "Gagal daftar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg }} keyboardShouldPersistTaps="handled">
        <Pressable testID="close-btn" hitSlop={8} onPress={() => router.back()} style={styles.close}>
          <Icon name="close" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={styles.logoBox}>
          <Icon name="storefront" size={26} color={colors.onBrandPrimary} />
        </View>
        <Text style={styles.title}>Buat akun baru</Text>
        <Text style={styles.subtitle}>Daftar gratis dan nikmati promo eksklusif.</Text>

        <View style={styles.inputWrap}>
          <Icon name="person-outline" size={18} color={colors.muted} />
          <TextInput testID="name-input" placeholder="Nama lengkap" placeholderTextColor={colors.muted} style={styles.input} value={name} onChangeText={setName} />
        </View>
        <View style={styles.inputWrap}>
          <Icon name="mail-outline" size={18} color={colors.muted} />
          <TextInput testID="email-input" placeholder="Email" placeholderTextColor={colors.muted} autoCapitalize="none" keyboardType="email-address" style={styles.input} value={email} onChangeText={setEmail} />
        </View>
        <View style={styles.inputWrap}>
          <Icon name="lock-closed-outline" size={18} color={colors.muted} />
          <TextInput testID="password-input" placeholder="Password (min. 6)" placeholderTextColor={colors.muted} secureTextEntry style={styles.input} value={password} onChangeText={setPassword} />
        </View>

        {err ? <Text style={styles.err} testID="register-error">{err}</Text> : null}

        <Pressable testID="register-submit" style={styles.primaryBtn} onPress={submit} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Daftar</Text>}
        </Pressable>

        <Pressable testID="to-login" onPress={() => router.replace("/login" as any)} style={styles.bottomLink}>
          <Text style={styles.bottomLinkText}>Sudah punya akun? <Text style={{ color: colors.brandPrimary, fontWeight: "500" }}>Masuk</Text></Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  close: { alignSelf: "flex-end", padding: spacing.sm },
  logoBox: { width: 56, height: 56, borderRadius: 16, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.lg },
  title: { fontSize: 22, color: colors.onSurface, fontWeight: "500", marginTop: spacing.lg },
  subtitle: { fontSize: fontSize.sm, color: colors.muted, marginTop: 4, marginBottom: spacing.xl },
  inputWrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, marginBottom: spacing.md },
  input: { flex: 1, paddingVertical: 14, color: colors.onSurface, fontSize: fontSize.base },
  err: { color: colors.error, fontSize: fontSize.sm, marginBottom: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, paddingVertical: 14, borderRadius: radius.pill, alignItems: "center", marginTop: spacing.sm },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },
  bottomLink: { marginTop: spacing.xl, alignItems: "center" },
  bottomLinkText: { color: colors.muted, fontSize: fontSize.sm },
});
