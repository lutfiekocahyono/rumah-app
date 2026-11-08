import React from "react";
import { View, Text, TextInput, StyleSheet } from "react-native";
import { colors, fontSize, spacing } from "@/src/theme";
import { co } from "./styles";

export function Input(props: { label: string; value: string; onChangeText: (v: string) => void; keyboardType?: any; multiline?: boolean; testID?: string }) {
  return (
    <View style={{ marginBottom: spacing.sm }}>
      <Text style={co.label}>{props.label}</Text>
      <TextInput
        testID={props.testID}
        value={props.value}
        onChangeText={props.onChangeText}
        placeholder={props.label}
        placeholderTextColor={colors.muted}
        keyboardType={props.keyboardType}
        multiline={props.multiline}
        style={[co.input, props.multiline && { minHeight: 60, textAlignVertical: "top" }]}
      />
    </View>
  );
}

export function Row({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.rowLabel, big && { color: colors.onSurface, fontWeight: "500", fontSize: fontSize.base }]}>{label}</Text>
      <Text style={[styles.rowValue, big && { color: colors.brandPrimary, fontSize: fontSize.lg, fontWeight: "500" }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  rowLabel: { color: colors.muted, fontSize: fontSize.sm },
  rowValue: { color: colors.onSurface, fontSize: fontSize.sm },
});
