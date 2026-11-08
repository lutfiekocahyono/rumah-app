import React from "react";
import { View, Text, StyleSheet, Pressable, TextInput, Switch, ActivityIndicator, type TextInputProps } from "react-native";

import { colors, fontSize, radius, spacing } from "@/src/theme";

export function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  return (
    <View style={{ gap: 4 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput placeholderTextColor={colors.muted} {...props} style={[styles.input, props.multiline && { minHeight: 60, textAlignVertical: "top" }]} />
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Chips<T extends string>({ options, value, onChange, testID }: {
  options: { id: T; label: string }[]; value: T; onChange: (v: T) => void; testID?: string;
}) {
  return (
    <View style={styles.chips}>
      {options.map((o) => (
        <Pressable key={o.id} testID={`${testID}-${o.id}`} onPress={() => onChange(o.id)} style={[styles.chip, value === o.id && styles.chipOn]}>
          <Text style={[styles.chipText, value === o.id && styles.chipTextOn]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function ToggleRow({ label, sub, value, onChange, testID }: { label: string; sub?: string; value: boolean; onChange: (v: boolean) => void; testID?: string }) {
  return (
    <View style={styles.toggle}>
      <View style={{ flex: 1 }}>
        <Text style={styles.toggleLabel}>{label}</Text>
        {sub ? <Text style={styles.hint}>{sub}</Text> : null}
      </View>
      <Switch testID={testID} value={value} onValueChange={onChange} trackColor={{ true: colors.brandPrimary, false: colors.border }} />
    </View>
  );
}

export function PrimaryButton({ label, onPress, loading, testID, variant = "solid" }: {
  label: string; onPress: () => void; loading?: boolean; testID?: string; variant?: "solid" | "outline" | "danger";
}) {
  const solid = variant === "solid";
  return (
    <Pressable testID={testID} onPress={onPress} disabled={loading}
      style={[styles.btn, solid ? styles.btnSolid : styles.btnOutline, variant === "danger" && { borderColor: colors.error }]}>
      {loading ? <ActivityIndicator color={solid ? colors.onBrandPrimary : colors.brandPrimary} /> : (
        <Text style={[styles.btnText, { color: solid ? colors.onBrandPrimary : variant === "danger" ? colors.error : colors.brandPrimary }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export const digits = (s: string) => Number(s.replace(/[^0-9.]/g, "")) || 0;

export const adminStyles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  section: { fontSize: fontSize.sm, color: colors.muted, marginTop: spacing.sm },
  err: { color: colors.error, fontSize: fontSize.sm },
  ok: { color: colors.success, fontSize: fontSize.sm },
  muted: { color: colors.muted, fontSize: 12 },
});

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  label: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  hint: { fontSize: 11, color: colors.muted },
  input: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface, fontSize: fontSize.base },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 36, justifyContent: "center" },
  chipOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextOn: { color: colors.onBrandPrimary, fontWeight: "500" },
  toggle: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 44 },
  toggleLabel: { fontSize: fontSize.base, color: colors.onSurface },
  btn: { minHeight: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  btnSolid: { backgroundColor: colors.brandPrimary },
  btnOutline: { borderWidth: 1, borderColor: colors.brandPrimary },
  btnText: { fontWeight: "500", fontSize: fontSize.base },
});
