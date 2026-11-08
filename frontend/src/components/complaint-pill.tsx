import React from "react";
import { View, Text, StyleSheet } from "react-native";

import { colors, radius } from "@/src/theme";
import { COMPLAINT_STATUS_LABEL, type Complaint } from "@/src/api";

export function StatusPill({ status }: { status: Complaint["status"] }) {
  const color = status === "refunded" || status === "resolved" ? colors.success : status === "rejected" ? colors.error : colors.warning;
  return (
    <View style={[styles.pill, { borderColor: color }]}>
      <Text style={[styles.text, { color }]}>{COMPLAINT_STATUS_LABEL[status]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  text: { fontSize: 11, fontWeight: "600" },
});
