import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet } from "react-native";

import { colors, radius } from "@/src/theme";

const pad = (n: number) => String(n).padStart(2, "0");

/** Live "hh : mm : ss" boxes until `endsAt`; calls onEnd once when it reaches zero. */
export function Countdown({ endsAt, onEnd, testID }: { endsAt: string; onEnd?: () => void; testID?: string }) {
  const end = new Date(endsAt).getTime();
  const [left, setLeft] = useState(Math.max(0, end - Date.now()));

  useEffect(() => {
    const t = setInterval(() => {
      const l = Math.max(0, end - Date.now());
      setLeft(l);
      if (l === 0) {
        clearInterval(t);
        onEnd?.();
      }
    }, 1000);
    return () => clearInterval(t);
  }, [end, onEnd]);

  const s = Math.floor(left / 1000);
  const days = Math.floor(s / 86400);
  const parts = [Math.floor((s % 86400) / 3600), Math.floor((s % 3600) / 60), s % 60];
  return (
    <View style={styles.row} testID={testID}>
      {days > 0 ? <Text style={styles.days}>{days} hari</Text> : null}
      {parts.map((p, i) => (
        <React.Fragment key={i}>
          <View style={styles.box}><Text style={styles.num}>{pad(p)}</Text></View>
          {i < 2 ? <Text style={styles.colon}>:</Text> : null}
        </React.Fragment>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 3 },
  days: { color: colors.onSurface, fontSize: 12, fontWeight: "600", marginRight: 3 },
  box: { backgroundColor: colors.surfaceInverse, borderRadius: radius.sm, paddingHorizontal: 5, paddingVertical: 2, minWidth: 24, alignItems: "center" },
  num: { color: colors.onSurfaceInverse, fontSize: 12, fontWeight: "700", fontVariant: ["tabular-nums"] },
  colon: { color: colors.onSurface, fontWeight: "700" },
});
