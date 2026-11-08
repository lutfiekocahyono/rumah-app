import React, { useEffect, useState } from "react";
import { Modal, View, Text, Pressable, ScrollView, ActivityIndicator } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, spacing } from "@/src/theme";
import { api, type ImportReport, type ImportRow } from "@/src/api";
import type { LocalFile } from "@/src/utils/upload";
import { downloadAuthed } from "@/src/utils/download";
import { s } from "./bulk-dialog";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const ACTION: Record<ImportRow["action"], { label: string; color: string }> = {
  create: { label: "Baru", color: colors.success }, update: { label: "Diubah", color: colors.brandPrimary },
  draft: { label: "Draft", color: colors.warning }, skip: { label: "Dilewati", color: colors.error }, same: { label: "Sama", color: colors.muted },
};

/** Excel import: pick file -> check (nothing saved) -> apply. */
export function ImportDialog({ visible, storeId, storeName, onClose, onDone }: {
  visible: boolean; storeId: string | null; storeName: string; onClose: () => void; onDone: () => void;
}) {
  const [file, setFile] = useState<LocalFile | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"" | "check" | "apply" | "template">("");
  const [err, setErr] = useState("");

  useEffect(() => { if (visible) { setFile(null); setReport(null); setErr(""); } }, [visible]);

  const check = async (f: LocalFile) => {
    setBusy("check");
    setErr("");
    try { setReport(await api.editorImport(f, storeId, false)); } catch (e: any) { setErr(e.message); setReport(null); } finally { setBusy(""); }
  };
  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ type: [XLSX, "application/vnd.ms-excel", "*/*"], copyToCacheDirectory: true });
    if (r.canceled || !r.assets?.[0]) return;
    const a = r.assets[0];
    if (!a.name.toLowerCase().endsWith(".xlsx")) return setErr("Pilih file Excel berformat .xlsx");
    const f = { uri: a.uri, name: a.name, mimeType: a.mimeType || XLSX };
    setFile(f);
    await check(f);
  };
  const apply = async () => {
    if (!file) return;
    setBusy("apply");
    setErr("");
    try { setReport(await api.editorImport(file, storeId, true)); onDone(); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const template = async () => {
    setBusy("template");
    try { await downloadAuthed(api.editorExportUrl(storeId, true), "template-impor-produk.xlsx"); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const c = report?.counts;
  const changes = c ? c.create + c.update + c.draft : 0;
  const rows = report?.rows.filter((r) => r.action !== "same") ?? [];
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.backdrop}>
        <View style={[s.box, { maxWidth: 560 }]} testID="import-dialog">
          <Text style={s.title}>Impor Produk dari Excel</Text>
          {!report ? (
            <View style={{ gap: spacing.md }}>
              <Text style={s.sub}>Toko tujuan: {storeName}. Isi baris tanpa ID Produk untuk menambah produk baru, atau ubah file hasil Ekspor untuk memperbarui produk. Data dicek dulu sebelum disimpan.</Text>
              <Pressable testID="import-template" style={[s.btn, s.cancel, { flexDirection: "row", gap: 6 }]} onPress={template} disabled={!!busy}>
                {busy === "template" ? <ActivityIndicator color={colors.brandPrimary} /> : <Icon name="download-outline" size={18} color={colors.brandPrimary} />}
                <Text style={[s.cancelText, { color: colors.brandPrimary }]}>Unduh Template</Text>
              </Pressable>
              <Pressable testID="import-pick" style={[s.btn, { backgroundColor: colors.brandPrimary, flexDirection: "row", gap: 6 }]} onPress={pick} disabled={!!busy}>
                {busy === "check" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Icon name="document-attach-outline" size={18} color={colors.onBrandPrimary} />}
                <Text style={s.okText}>{busy === "check" ? "Memeriksa file…" : "Pilih File Excel (.xlsx)"}</Text>
              </Pressable>
            </View>
          ) : (
            <View style={{ gap: spacing.sm }}>
              <Text style={report.committed ? s.ok : s.sub} testID={report.committed ? "import-done" : "import-preview"}>
                {report.committed ? "Impor selesai ✓" : `Hasil pemeriksaan ${file?.name ?? ""}`}
              </Text>
              <View style={s.pills} testID="import-counts">
                {(Object.keys(ACTION) as ImportRow["action"][]).map((k) => c![k] ? (
                  <Text key={k} style={[s.sub, { color: ACTION[k].color, fontWeight: "600" }]}>{ACTION[k].label}: {c![k]}</Text>
                ) : null)}
              </View>
              <ScrollView style={{ maxHeight: 300 }} contentContainerStyle={{ gap: 6 }}>
                {rows.slice(0, 200).map((r, i) => (
                  <View key={`${r.row}-${i}`} style={{ flexDirection: "row", gap: spacing.sm }} testID={`import-row-${r.action}`}>
                    <Text style={[s.sub, { width: 62, color: ACTION[r.action].color, fontWeight: "600" }]}>{ACTION[r.action].label}</Text>
                    <Text style={[s.sub, { flex: 1 }]}>Baris {r.row} · {r.name}{r.message ? ` — ${r.message}` : ""}</Text>
                  </View>
                ))}
                {!rows.length ? <Text style={s.sub}>Tidak ada perubahan di file ini.</Text> : null}
              </ScrollView>
            </View>
          )}
          {err ? <Text style={s.errText} testID="import-error">{err}</Text> : null}
          <View style={s.row}>
            <Pressable testID="import-close" style={[s.btn, s.cancel]} onPress={onClose} disabled={busy === "apply"}>
              <Text style={s.cancelText}>{report?.committed ? "Tutup" : "Batal"}</Text>
            </Pressable>
            {report && !report.committed ? (
              <Pressable testID="import-apply" style={[s.btn, { backgroundColor: changes ? colors.brandPrimary : colors.muted }]} onPress={apply} disabled={!changes || !!busy}>
                {busy === "apply" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.okText}>Terapkan ({changes})</Text>}
              </Pressable>
            ) : null}
          </View>
        </View>
      </View>
    </Modal>
  );
}
