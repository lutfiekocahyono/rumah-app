import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, spacing } from "@/src/theme";

export function ScreenHeader({ title, testID, right }: { title: string; testID?: string; right?: React.ReactNode }) {
  const router = useRouter();
  return (
    <View style={styles.header}>
      <Pressable
        testID={testID ?? "header-back"}
        hitSlop={8}
        style={styles.back}
        onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)" as any))}
      >
        <Icon name="chevron-back" size={24} color={colors.onSurface} />
      </Pressable>
      <Text style={styles.title} numberOfLines={1}>{title}</Text>
      <View style={styles.right}>{right}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.sm, minHeight: 52,
    backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { flex: 1, textAlign: "center", fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  right: { width: 44, alignItems: "center" },
});
