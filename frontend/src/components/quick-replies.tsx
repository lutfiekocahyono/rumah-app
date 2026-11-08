import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Modal, TextInput, ActivityIndicator } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type QuickReply } from "@/src/api";
import { ConfirmDialog } from "@/src/components/confirm-dialog";

export const PLACEHOLDERS = "{produk} {harga} {pembeli} {toko}";

const FALLBACK: Record<string, string> = { produk: "produk ini", harga: "sesuai yang tertera di halaman produk", pembeli: "", toko: "toko kami" };

export function fillTemplate(text: string, vars: Record<string, string>) {
  return text.replace(/\{(produk|harga|pembeli|toko)\}/g, (_all, k: string) => vars[k] || FALLBACK[k])
    .replace(/Kak ,/g, "Kak,").replace(/ {2,}/g, " ");
}

/** Template balasan siap pakai untuk admin cabang di chat. Ketuk = isi kolom pesan (bisa diubah sebelum dikirim). */
export function QuickReplies({ onPick }: { onPick: (text: string) => void }) {
  const [items, setItems] = useState<QuickReply[] | null>(null);
  const [manage, setManage] = useState(false);
  const load = useCallback(() => { api.quickReplies().then((r) => setItems(r.items)).catch(() => setItems([])); }, []);
  useEffect(load, [load]);

  return (
    <>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.chips} testID="quick-replies">
        <Pressable style={[styles.chip, styles.chipManage]} onPress={() => setManage(true)} testID="quick-replies-manage">
          <Icon name="create-outline" size={14} color={colors.brandPrimary} />
          <Text style={[styles.chipText, { color: colors.brandPrimary }]}>{items?.length ? "Atur" : "Buat balasan cepat"}</Text>
        </Pressable>
        {(items ?? []).map((q) => (
          <Pressable key={q.reply_id} style={styles.chip} onPress={() => onPick(q.text)} testID={`quick-reply-${q.reply_id}`}>
            <Text style={styles.chipText} numberOfLines={1}>{q.title}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <ManageSheet visible={manage} items={items ?? []} onClose={() => setManage(false)} onChanged={setItems} />
    </>
  );
}

function ManageSheet({ visible, items, onClose, onChanged }: { visible: boolean; items: QuickReply[]; onClose: () => void; onChanged: (x: QuickReply[]) => void }) {
  const insets = useSafeAreaInsets();
  const [edit, setEdit] = useState<QuickReply | "new" | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [del, setDel] = useState<QuickReply | null>(null);

  const open = (q: QuickReply | "new") => {
    setEdit(q); setErr("");
    setTitle(q === "new" ? "" : q.title); setText(q === "new" ? "" : q.text);
  };
  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (edit === "new") onChanged([...items, await api.addQuickReply(title.trim(), text.trim())]);
      else if (edit) { const r = await api.editQuickReply(edit.reply_id, title.trim(), text.trim()); onChanged(items.map((i) => (i.reply_id === r.reply_id ? r : i))); }
      setEdit(null);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!del) return;
    const q = del;
    setDel(null);
    try { await api.deleteQuickReply(q.reply_id); onChanged(items.filter((i) => i.reply_id !== q.reply_id)); if (edit !== "new" && edit?.reply_id === q.reply_id) setEdit(null); }
    catch (e: any) { setErr(e.message); }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior="padding" style={styles.backdrop}>
        <Pressable style={{ flex: 1 }} onPress={onClose} />
        <View style={[styles.sheet, { paddingBottom: Math.max(spacing.lg, insets.bottom) }]} testID="quick-replies-sheet">
          <View style={styles.sheetHead}>
            <Text style={styles.h}>{edit ? (edit === "new" ? "Balasan Cepat Baru" : "Ubah Balasan Cepat") : "Balasan Cepat"}</Text>
            <Pressable onPress={edit ? () => setEdit(null) : onClose} hitSlop={12} testID="quick-replies-close">
              <Icon name={edit ? "arrow-back" : "close"} size={22} color={colors.onSurface} />
            </Pressable>
          </View>
          {edit ? (
            <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: spacing.sm }}>
              <Text style={styles.label}>Judul tombol</Text>
              <TextInput testID="quick-reply-title" value={title} onChangeText={setTitle} maxLength={40} placeholder="mis. Stok tersedia"
                placeholderTextColor={colors.muted} style={styles.input} />
              <Text style={styles.label}>Isi pesan</Text>
              <TextInput testID="quick-reply-text" value={text} onChangeText={setText} maxLength={1000} multiline placeholder="Tulis balasan…"
                placeholderTextColor={colors.muted} style={[styles.input, { minHeight: 120, textAlignVertical: "top", paddingTop: spacing.sm }]} />
              <Text style={styles.small}>Kata otomatis: {PLACEHOLDERS} — diganti nama produk yang ditanyakan, harganya, nama pembeli, dan nama cabang.</Text>
              {err ? <Text style={[styles.small, { color: colors.error }]} testID="quick-reply-error">{err}</Text> : null}
              <Pressable testID="quick-reply-save" style={[styles.primary, (!title.trim() || !text.trim()) && { opacity: 0.5 }]} onPress={save}
                disabled={busy || !title.trim() || !text.trim()}>
                {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Simpan</Text>}
              </Pressable>
              {edit !== "new" ? (
                <Pressable testID="quick-reply-delete" style={styles.danger} onPress={() => setDel(edit)}>
                  <Text style={{ color: colors.error, fontWeight: "600" }}>Hapus</Text>
                </Pressable>
              ) : null}
            </ScrollView>
          ) : (
            <ScrollView contentContainerStyle={{ gap: spacing.xs }}>
              <Text style={styles.small}>Berlaku untuk semua admin cabang ini. Ketuk untuk mengubah.</Text>
              {items.map((q) => (
                <Pressable key={q.reply_id} style={styles.row} onPress={() => open(q)} testID={`quick-reply-row-${q.reply_id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>{q.title}</Text>
                    <Text style={styles.small} numberOfLines={2}>{q.text}</Text>
                  </View>
                  <Icon name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>
              ))}
              {err ? <Text style={[styles.small, { color: colors.error }]}>{err}</Text> : null}
              <Pressable testID="quick-reply-add" style={styles.outline} onPress={() => open("new")}>
                <Icon name="add" size={18} color={colors.brandPrimary} />
                <Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Tambah Balasan Cepat</Text>
              </Pressable>
            </ScrollView>
          )}
        </View>
      </KeyboardAvoidingView>
      <ConfirmDialog visible={!!del} title="Hapus balasan cepat?" confirmLabel="Hapus" message={del ? `"${del.title}" akan dihapus untuk semua admin cabang ini.` : ""}
        onConfirm={remove} onCancel={() => setDel(null)} />
    </Modal>
  );
}

const styles = StyleSheet.create({
  chips: { gap: spacing.xs, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  chip: { minHeight: 36, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, maxWidth: 200 },
  chipManage: { borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, maxHeight: "85%" },
  sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 44 },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  label: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  small: { fontSize: 13, color: colors.onSurfaceSecondary },
  input: { minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, color: colors.onSurface, backgroundColor: colors.surface },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 56, paddingVertical: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  primary: { minHeight: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600" },
  outline: { minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 4, marginTop: spacing.sm },
  danger: { minHeight: 44, alignItems: "center", justifyContent: "center" },
});
