import React, { useState } from "react";
import { View, Text, TextInput, Pressable, StyleSheet } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";
import { colors, fontSize, radius, spacing } from "@/src/theme";
import { RichText } from "@/src/components/rich-text";
import { FieldError, ui } from "./ui";
import { MIN_DESC, plainLen } from "./form";

type Sel = { start: number; end: number };

/** Description editor: toolbar adds **tebal**, _miring_, ## judul, - poin, 1. nomor at the cursor; Pratinjau shows the result. */
export function RichEditor({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  const [sel, setSel] = useState<Sel>({ start: value.length, end: value.length });
  const [preview, setPreview] = useState(false);

  const wrap = (mark: string, placeholder: string) => {
    const picked = value.slice(sel.start, sel.end) || placeholder;
    const next = `${value.slice(0, sel.start)}${mark}${picked}${mark}${value.slice(sel.end)}`;
    onChange(next);
    const pos = sel.start + mark.length + picked.length + mark.length;
    setSel({ start: pos, end: pos });
  };
  const linePrefix = (prefix: (i: number) => string) => {
    const lineStart = value.lastIndexOf("\n", sel.start - 1) + 1;
    const blockEnd = value.indexOf("\n", sel.end);
    const end = blockEnd === -1 ? value.length : blockEnd;
    const lines = value.slice(lineStart, end).split("\n").map((l, i) => `${prefix(i)}${l.replace(/^(#{1,3}\s|[-•]\s|\d+\.\s)/, "")}`);
    const block = lines.join("\n");
    onChange(value.slice(0, lineStart) + block + value.slice(end));
    setSel({ start: lineStart + block.length, end: lineStart + block.length });
  };
  const tools = [
    { id: "bold", icon: "text", label: "Tebal", run: () => wrap("**", "teks tebal") },
    { id: "italic", icon: "remove-outline", label: "Miring", run: () => wrap("_", "teks miring") },
    { id: "heading", icon: "reorder-two-outline", label: "Judul", run: () => linePrefix(() => "## ") },
    { id: "bullet", icon: "list-outline", label: "Poin", run: () => linePrefix(() => "- ") },
    { id: "number", icon: "list-circle-outline", label: "Nomor", run: () => linePrefix((i) => `${i + 1}. `) },
  ];
  const n = plainLen(value);
  return (
    <View style={{ gap: 4 }}>
      <View style={{ flexDirection: "row" }}>
        <Text style={[ui.label, { flex: 1 }]}>Deskripsi produk<Text style={{ color: colors.error }}> *</Text></Text>
        <Text style={[ui.hint, n < MIN_DESC && { color: colors.error }]} testID="pe-desc-count">{n}/{MIN_DESC} min · {value.length}/10000</Text>
      </View>
      <View style={[styles.box, !!error && ui.inputErr]}>
        <View style={styles.toolbar}>
          {tools.map((t) => (
            <Pressable key={t.id} testID={`pe-rt-${t.id}`} onPress={t.run} disabled={preview} style={[styles.tool, preview && { opacity: 0.4 }]} accessibilityLabel={t.label}>
              {t.id === "bold" ? <Text style={styles.toolB}>B</Text> : t.id === "italic" ? <Text style={styles.toolI}>I</Text> :
                t.id === "heading" ? <Text style={styles.toolB}>H</Text> : <Icon name={t.icon as any} size={18} color={colors.onSurface} />}
            </Pressable>
          ))}
          <View style={{ flex: 1 }} />
          <Pressable testID="pe-rt-preview" onPress={() => setPreview((p) => !p)} style={[styles.previewBtn, preview && { backgroundColor: colors.brandTertiary }]}>
            <Icon name={preview ? "create-outline" : "eye-outline"} size={16} color={colors.brandPrimary} />
            <Text style={styles.previewText}>{preview ? "Edit" : "Pratinjau"}</Text>
          </Pressable>
        </View>
        {preview ? (
          <View style={styles.preview} testID="pe-desc-preview">
            {value.trim() ? <RichText text={value} style={{ fontSize: fontSize.sm, color: colors.onSurfaceSecondary, lineHeight: 20 }} /> : <Text style={ui.hint}>Belum ada deskripsi</Text>}
          </View>
        ) : (
          <TextInput testID="pe-description" value={value} onChangeText={onChange} multiline maxLength={10000}
            selection={sel} onSelectionChange={(e) => setSel(e.nativeEvent.selection)}
            placeholder={"Jelaskan keunggulan, bahan, ukuran, dan isi paket.\nContoh:\n## Keunggulan\n- Bahan **tebal** dan awet"}
            placeholderTextColor={colors.muted} style={styles.input} />
        )}
      </View>
      <FieldError msg={error} testID="pe-description-error" />
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  toolbar: { flexDirection: "row", alignItems: "center", gap: 2, padding: 4, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  tool: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderRadius: radius.sm },
  toolB: { fontWeight: "800", fontSize: fontSize.base, color: colors.onSurface },
  toolI: { fontStyle: "italic", fontSize: fontSize.base, color: colors.onSurface, fontWeight: "600" },
  previewBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, minHeight: 40, borderRadius: radius.sm },
  previewText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "600" },
  input: { minHeight: 180, padding: spacing.md, color: colors.onSurface, fontSize: fontSize.sm, textAlignVertical: "top", lineHeight: 20 },
  preview: { minHeight: 180, padding: spacing.md },
});
