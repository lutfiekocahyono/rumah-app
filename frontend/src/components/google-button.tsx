import React, { useState } from "react";
import { Text, Pressable, StyleSheet, ActivityIndicator, View } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useAuth } from "@/src/auth-context";

/** One-tap Google sign-in / sign-up (new Google users get an account automatically). */
export function GoogleButton({ onDone, label = "Masuk dengan Google", testID = "google-login-btn" }: { onDone?: () => void; label?: string; testID?: string }) {
  const { loginWithGoogle } = useAuth();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const press = async () => {
    setErr("");
    setLoading(true);
    try {
      if (await loginWithGoogle()) onDone?.();
    } catch (e: any) {
      setErr(e?.message || "Login Google gagal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ gap: 4 }}>
      <Pressable testID={testID} style={({ pressed }) => [styles.btn, pressed && { opacity: 0.85 }]} onPress={press} disabled={loading}>
        {loading ? <ActivityIndicator color={colors.onSurface} /> : (
          <>
            <Icon name="logo-google" size={18} color="#EA4335" />
            <Text style={styles.text}>{label}</Text>
          </>
        )}
      </Pressable>
      {err ? <Text style={styles.err}>{err}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  btn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.borderStrong, backgroundColor: colors.surface,
  },
  text: { color: colors.onSurface, fontWeight: "500", fontSize: fontSize.base },
  err: { color: colors.error, fontSize: fontSize.sm, textAlign: "center" },
});
