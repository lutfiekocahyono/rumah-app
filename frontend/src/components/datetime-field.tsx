import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput } from "react-native";

import { colors, fontSize, radius, spacing } from "@/src/theme";

const WIB = 7 * 3600 * 1000;
const pad = (n: number) => String(n).padStart(2, "0");

/** ISO (UTC) -> "YYYY-MM-DD HH:mm" in WIB */
export function toWib(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() + WIB);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** "YYYY-MM-DD HH:mm" (WIB) -> ISO UTC, or null if invalid */
export function fromWib(s: string): string | null {
  const m = s.trim().match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const t = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) - WIB;
  return isNaN(t) ? null : new Date(t).toISOString();
}

const PRESETS = [
  { label: "+6 jam", h: 6 }, { label: "+12 jam", h: 12 }, { label: "+1 hari", h: 24 },
  { label: "+3 hari", h: 72 }, { label: "+7 hari", h: 168 },
];

/** End-date input in WIB with quick presets. value/onChange use ISO strings (null = empty). */
export function DateTimeField({ value, onChange, allowEmpty, testID }: {
  value: string | null; onChange: (iso: string | null) => void; allowEmpty?: boolean; testID?: string;
}) {
  const [text, setText] = useState(toWib(value));
  useEffect(() => { setText(toWib(value)); }, [value]);
  const invalid = text.trim() !== "" && !fromWib(text);
  return (
    <View style={{ gap: spacing.sm }}>
      <TextInput
        testID={testID}
        value={text}
        onChangeText={(t) => {
          setText(t);
          if (!t.trim() && allowEmpty) onChange(null);
          else if (fromWib(t)) onChange(fromWib(t));
        }}
        placeholder={allowEmpty ? "Tanpa batas (kosongkan)" : "2026-12-31 23:59"}
        placeholderTextColor={colors.muted}
        style={[styles.input, invalid && { borderColor: colors.error, borderWidth: 1 }]}
      />
      <Text style={[styles.hint, invalid && { color: colors.error }]}>Format: TTTT-BB-HH JJ:MM (WIB)</Text>
      <View style={styles.presets}>
        {PRESETS.map((p) => (
          <Pressable key={p.h} testID={`${testID}-preset-${p.h}`} style={styles.chip}
            onPress={() => onChange(new Date(Date.now() + p.h * 3600 * 1000).toISOString())}>
            <Text style={styles.chipText}>{p.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  input: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface, fontSize: fontSize.base },
  hint: { fontSize: 11, color: colors.muted },
  presets: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 34, justifyContent: "center" },
  chipText: { fontSize: 12, color: colors.onSurface },
});
