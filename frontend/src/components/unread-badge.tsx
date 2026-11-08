import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import { useFocusEffect } from "expo-router";

import { colors } from "@/src/theme";
import { api } from "@/src/api";

/** Unread chat counts (buyer side + own store side), refreshed whenever the screen gains focus. */
export function useChatUnread(enabled: boolean) {
  const [counts, setCounts] = useState({ buyer: 0, store: 0 });
  useFocusEffect(useCallback(() => {
    if (!enabled) { setCounts({ buyer: 0, store: 0 }); return; }
    api.chatUnread().then(setCounts).catch(() => {});
  }, [enabled]));
  return counts;
}

export function UnreadBadge({ count, testID }: { count: number; testID?: string }) {
  if (!count) return null;
  return (
    <View style={styles.badge} testID={testID}>
      <Text style={styles.text}>{count > 99 ? "99+" : count}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { minWidth: 20, height: 20, borderRadius: 10, paddingHorizontal: 6, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  text: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "700" },
});
