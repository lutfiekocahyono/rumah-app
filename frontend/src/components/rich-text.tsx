import React from "react";
import { Text, View, type TextStyle } from "react-native";
import { colors, fontSize, spacing } from "@/src/theme";

/** Renders the product description format: "## judul", "- poin", "1. nomor", **tebal**, _miring_. Plain text shows as-is. */
function inline(line: string, key: string) {
  const parts = line.split(/(\*\*[^*]+\*\*|_[^_]+_)/g).filter(Boolean);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <Text key={`${key}-${i}`} style={{ fontWeight: "700" }}>{p.slice(2, -2)}</Text>
      : p.length > 2 && p.startsWith("_") && p.endsWith("_") ? <Text key={`${key}-${i}`} style={{ fontStyle: "italic" }}>{p.slice(1, -1)}</Text>
        : p);
}

export function RichText({ text, style }: { text: string; style?: TextStyle }) {
  const lines = (text || "").split("\n");
  return (
    <View style={{ gap: 4 }} testID="rich-text">
      {lines.map((l, i) => {
        const k = `l${i}`;
        if (!l.trim()) return <View key={k} style={{ height: spacing.xs }} />;
        const h = l.match(/^#{1,3}\s+(.*)/);
        if (h) return <Text key={k} style={[style, { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface, marginTop: 4 }]}>{inline(h[1], k)}</Text>;
        const b = l.match(/^\s*[-•]\s+(.*)/);
        const n = l.match(/^\s*(\d+)\.\s+(.*)/);
        if (b || n) {
          return (
            <View key={k} style={{ flexDirection: "row", gap: 6, paddingLeft: 4 }}>
              <Text style={style}>{b ? "•" : `${n![1]}.`}</Text>
              <Text style={[style, { flex: 1 }]}>{inline(b ? b[1] : n![2], k)}</Text>
            </View>
          );
        }
        return <Text key={k} style={style}>{inline(l, k)}</Text>;
      })}
    </View>
  );
}
