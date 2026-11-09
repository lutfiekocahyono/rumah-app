import React from "react";
import { Pressable } from "react-native";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors } from "@/src/theme";

/** Camera icon inside every search box: opens "Cari dengan Foto". */
export function PhotoSearchButton({ testID = "photo-search-btn" }: { testID?: string }) {
  const router = useRouter();
  return (
    <Pressable testID={testID} hitSlop={10} accessibilityLabel="Cari dengan foto" onPress={() => router.push("/cari-foto" as any)}
      style={{ minWidth: 36, minHeight: 36, alignItems: "center", justifyContent: "center" }}>
      <Icon name="camera-outline" size={20} color={colors.brandPrimary} />
    </Pressable>
  );
}
