import React from "react";
import { View, Text, TextInput, StyleSheet, Pressable, type TextInputProps } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";
import { colors, fontSize, radius, spacing } from "@/src/theme";

export function Section({ title, icon, subtitle, children, testID, right }: {
  title: string; icon: string; subtitle?: string; children: React.ReactNode; testID?: string; right?: React.ReactNode;
}) {
  return (
    <View style={ui.card} testID={testID}>
      <View style={ui.head}>
        <View style={ui.iconWrap}><Icon name={icon as any} size={18} color={colors.brandPrimary} /></View>
        <View style={{ flex: 1 }}>
          <Text style={ui.title}>{title}</Text>
          {subtitle ? <Text style={ui.sub}>{subtitle}</Text> : null}
        </View>
        {right}
      </View>
      <View style={{ gap: spacing.md }}>{children}</View>
    </View>
  );
}

export function FieldError({ msg, testID }: { msg?: string; testID?: string }) {
  return msg ? (
    <View style={ui.errRow} testID={testID}>
      <Icon name="alert-circle" size={14} color={colors.error} />
      <Text style={ui.err}>{msg}</Text>
    </View>
  ) : null;
}

export function Input({ label, required, error, hint, counter, prefix, testID, compact, ...p }: TextInputProps & {
  label: string; required?: boolean; error?: string; hint?: string; counter?: string; prefix?: string; testID: string; compact?: boolean;
}) {
  return (
    <View style={{ gap: 4, flex: 1, minWidth: compact ? 0 : 140 }}>
      <View style={{ flexDirection: "row" }}>
        <Text style={[ui.label, { flex: 1 }]}>{label}{required ? <Text style={{ color: colors.error }}> *</Text> : null}</Text>
        {counter ? <Text style={ui.hint}>{counter}</Text> : null}
      </View>
      <View style={[ui.inputWrap, !!error && ui.inputErr, p.editable === false && { opacity: 0.6 }]}>
        {prefix ? <Text style={ui.prefix}>{prefix}</Text> : null}
        <TextInput testID={testID} placeholderTextColor={colors.muted} {...p}
          style={[ui.input, p.multiline && { minHeight: 140, textAlignVertical: "top" }, p.style]} />
      </View>
      {hint && !error ? <Text style={ui.hint}>{hint}</Text> : null}
      <FieldError msg={error} testID={`${testID}-error`} />
    </View>
  );
}

export function Pill({ label, on, onPress, testID, icon }: { label: string; on: boolean; onPress: () => void; testID: string; icon?: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[ui.pill, on && ui.pillOn]}>
      {icon ? <Icon name={icon as any} size={14} color={on ? colors.brandPrimary : colors.onSurfaceSecondary} /> : null}
      <Text style={[ui.pillText, on && ui.pillTextOn]}>{label}</Text>
    </Pressable>
  );
}

export const digitsOf = (t: string) => Number(t.replace(/\D/g, "").slice(0, 10)) || 0;
export const rupiah = (n: number) => (n ? n.toLocaleString("id-ID") : "");

export const ui = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, gap: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  iconWrap: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  sub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  label: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, fontWeight: "500" },
  hint: { fontSize: 12, color: colors.muted },
  inputWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border },
  inputErr: { borderColor: colors.error },
  prefix: { paddingLeft: spacing.md, color: colors.muted, fontSize: fontSize.sm },
  input: { flex: 1, minWidth: 0, width: "100%", paddingHorizontal: spacing.md, paddingVertical: 10, minHeight: 44, color: colors.onSurface, fontSize: fontSize.sm },
  errRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  err: { color: colors.error, fontSize: 12, flex: 1 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  pill: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 40 },
  pillOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  pillText: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  pillTextOn: { color: colors.brandPrimary, fontWeight: "600" },
});
