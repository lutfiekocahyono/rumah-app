import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import { Image } from "expo-image";
import { GoogleButton } from "@/src/components/google-button";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useAuth } from "@/src/auth-context";

export default function Login() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const done = () => {
    if (router.canGoBack()) router.back();
    else router.replace("/(tabs)/akun" as any);
  };

  const submit = async () => {
    setErr("");
    setLoading(true);
    try {
      await login(email.trim(), password);
      done();
    } catch (e: any) {
      setErr(e?.message || "Gagal masuk");
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

        <Image source={require("../assets/images/pgs-logo-small.png")} style={styles.logoImg} contentFit="contain" />
        <Text style={styles.subtitle}>Belanja lebih mudah, aman, dan penuh promo.</Text>

        <View style={styles.inputWrap}>
          <Icon name="mail-outline" size={18} color={colors.muted} />
          <TextInput
            testID="email-input"
            placeholder="Email"
            placeholderTextColor={colors.muted}
            autoCapitalize="none" keyboardType="email-address"
            style={styles.input} value={email} onChangeText={setEmail}
          />
        </View>
        <View style={styles.inputWrap}>
          <Icon name="lock-closed-outline" size={18} color={colors.muted} />
          <TextInput
            testID="password-input"
            placeholder="Password"
            placeholderTextColor={colors.muted}
            secureTextEntry={!show}
            style={styles.input} value={password} onChangeText={setPassword}
          />
          <Pressable hitSlop={8} onPress={() => setShow((s) => !s)}>
            <Icon name={show ? "eye-off-outline" : "eye-outline"} size={18} color={colors.muted} />
          </Pressable>
        </View>

        {err ? <Text style={styles.err} testID="login-error">{err}</Text> : null}

        <Pressable testID="forgot-password-link" hitSlop={8} onPress={() => router.push("/forgot-password" as any)} style={{ alignSelf: "flex-end", marginBottom: spacing.md }}>
          <Text style={{ color: colors.brandPrimary, fontSize: fontSize.sm }}>Lupa password?</Text>
        </Pressable>
        <Pressable testID="login-submit" style={styles.primaryBtn} onPress={submit} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Masuk</Text>}
        </Pressable>

        <View style={styles.divider}>
          <View style={styles.line} />
          <Text style={styles.dividerText}>atau</Text>
          <View style={styles.line} />
        </View>

        <View style={{ marginBottom: spacing.md }}>
          <GoogleButton onDone={done} />
        </View>

        <Pressable testID="continue-guest" style={styles.outlineBtn} onPress={() => router.replace("/(tabs)" as any)}>
          <Icon name="person-outline" size={18} color={colors.onSurface} />
          <Text style={styles.outlineText}>Lanjut sebagai Tamu</Text>
        </Pressable>

        <Pressable testID="to-register" onPress={() => router.replace("/register" as any)} style={styles.bottomLink}>
          <Text style={styles.bottomLinkText}>Belum punya akun? <Text style={{ color: colors.brandPrimary, fontWeight: "500" }}>Daftar</Text></Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  close: { alignSelf: "flex-end", padding: spacing.sm },
  logoImg: { width: 72, height: 72, marginTop: spacing.md },
  logoBox: { width: 56, height: 56, borderRadius: 16, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.lg },
  title: { fontSize: 22, color: colors.onSurface, fontWeight: "500", marginTop: spacing.lg },
  subtitle: { fontSize: fontSize.sm, color: colors.muted, marginTop: 4, marginBottom: spacing.xl },
  inputWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md, marginBottom: spacing.md,
  },
  input: { flex: 1, paddingVertical: 14, color: colors.onSurface, fontSize: fontSize.base },
  err: { color: colors.error, fontSize: fontSize.sm, marginBottom: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, paddingVertical: 14, borderRadius: radius.pill, alignItems: "center", marginTop: spacing.sm },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: fontSize.base },
  divider: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginVertical: spacing.lg },
  line: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  dividerText: { color: colors.muted, fontSize: fontSize.sm },
  outlineBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
  },
  outlineText: { color: colors.onSurface, fontWeight: "500" },
  bottomLink: { marginTop: spacing.xl, alignItems: "center" },
  bottomLinkText: { color: colors.muted, fontSize: fontSize.sm },
});
