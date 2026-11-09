import React, { useEffect, useState } from "react";
import { Modal, View, Text, Pressable, ActivityIndicator, ScrollView, TextInput, StyleSheet, KeyboardAvoidingView, Platform } from "react-native";
import * as DocumentPicker from "expo-document-picker";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type BranchBulkPreview } from "@/src/api";
import { adminStyles, Chips, ToggleRow } from "@/src/components/admin-form";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export type BulkKind = "adjust" | "import";

/** Edit Massal Cabang: naik/turun persen atau rupiah, atau unggah Excel; selalu pratinjau lalu konfirmasi. */
export function BranchBulkDialog({ kind, storeId, storeName, q, onClose, onDone }: {
  kind: BulkKind | null; storeId: string | null; storeName: string; q: string; onClose: () => void; onDone: () => void;
}) {
  const [mode, setMode] = useState<"pct" | "rp">("pct");
  const [dir, setDir] = useState<"up" | "down">("up");
  const [val, setVal] = useState("");
  const [tiers, setTiers] = useState(true);
  const [onlyQ, setOnlyQ] = useState(!!q);
  const [pv, setPv] = useState<BranchBulkPreview | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => { if (kind) { setPv(null); setErr(""); setSaved(null); setConfirm(false); setVal(""); setOnlyQ(!!q); } }, [kind, q]);

  const n = Number(val.replace(",", ".")) || 0;
  const preview = async () => {
    if (n <= 0) return setErr("Isi besar kenaikan / penurunan");
    if (mode === "pct" && (dir === "up" ? n > 100 : n > 90)) return setErr(dir === "up" ? "Maksimal naik 100%" : "Maksimal turun 90%");
    setBusy("pv"); setErr("");
    try { setPv(await api.branchBulkPreview({ store_id: storeId, mode, value: dir === "up" ? n : -n, tiers, q: onlyQ ? q : "" })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ type: [XLSX, "*/*"], copyToCacheDirectory: true });
    if (r.canceled || !r.assets?.[0]) return;
    const a = r.assets[0];
    if (!a.name.toLowerCase().endsWith(".xlsx")) return setErr("Pilih file Excel (.xlsx) hasil Unduh Excel");
    setBusy("pv"); setErr("");
    try { setPv(await api.branchImport({ uri: a.uri, name: a.name, mimeType: a.mimeType || XLSX }, storeId)); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const apply = async () => {
    if (!pv) return;
    setBusy("save"); setErr("");
    try { setSaved((await api.branchBulkApply(pv.preview_id)).saved); onDone(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); setConfirm(false); }
  };

  return (
    <Modal visible={!!kind} transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.backdrop}>
        <View style={styles.box} testID="bb-dialog">
          <ScrollView contentContainerStyle={{ gap: spacing.sm }} keyboardShouldPersistTaps="handled">
            <Text style={styles.title}>{kind === "import" ? "Unggah Excel Harga Cabang" : "Ubah Harga Massal"}</Text>
            <Text style={adminStyles.muted}>{storeName}: hanya harga cabang ini yang berubah. Pratinjau dulu, disimpan setelah Anda konfirmasi.</Text>
            {saved !== null ? <Text style={adminStyles.ok} testID="bb-saved">{saved.toLocaleString("id-ID")} produk diperbarui dan tercatat di Riwayat Harga & Stok.</Text> : !pv ? (
              kind === "import" ? (
                <>
                  <Text style={adminStyles.muted}>Pakai file dari tombol Unduh Excel. Ubah kolom Harga Cabang, Harga Coret, atau Grosir (format 6:20130; 12:19760), lalu unggah.</Text>
                  <Pressable testID="bb-pick" style={styles.outline} onPress={pick} disabled={!!busy}>
                    {busy ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Pilih file Excel</Text>}
                  </Pressable>
                </>
              ) : (
                <>
                  <Chips testID="bb-dir" options={[{ id: "up", label: "Naikkan" }, { id: "down", label: "Turunkan" }]} value={dir} onChange={(v) => { setDir(v); setErr(""); }} />
                  <Chips testID="bb-mode" options={[{ id: "pct", label: "Persen (%)" }, { id: "rp", label: "Rupiah (Rp)" }]} value={mode} onChange={(v) => { setMode(v); setErr(""); }} />
                  <TextInput testID="bb-value" value={val} onChangeText={(t) => { setErr(""); setVal(t.replace(/[^0-9.,]/g, "")); }} keyboardType="decimal-pad"
                    placeholder={mode === "pct" ? "mis. 5" : "mis. 1000"} placeholderTextColor={colors.muted} style={styles.input} />
                  {mode === "pct" ? <Text style={adminStyles.muted}>Persen dibulatkan ke atas ke Rp100 terdekat.</Text> : null}
                  <ToggleRow testID="bb-tiers" label="Ubah juga harga grosir" value={tiers} onChange={setTiers} />
                  {q ? <ToggleRow testID="bb-onlyq" label={`Hanya produk hasil pencarian “${q}”`} sub="Matikan untuk semua produk cabang" value={onlyQ} onChange={setOnlyQ} />
                    : <Text style={adminStyles.muted}>Berlaku untuk semua produk cabang. Cari produk dulu untuk membatasi.</Text>}
                </>
              )
            ) : (
              <View style={{ gap: 6 }} testID="bb-preview">
                <Text style={styles.h} testID="bb-summary">{pv.changed.toLocaleString("id-ID")} produk berubah · naik {pv.up.toLocaleString("id-ID")} · turun {pv.down.toLocaleString("id-ID")}</Text>
                {pv.error_count ? (
                  <View testID="bb-errors">
                    <Text style={adminStyles.err}>{pv.error_count} baris dilewati:</Text>
                    {pv.errors.slice(0, 5).map((e) => <Text key={`${e.row}`} style={adminStyles.muted}>Baris {e.row} ({e.product_id}): {e.reason}</Text>)}
                  </View>
                ) : null}
                {pv.sample.slice(0, 10).map((x) => (
                  <View key={x.product_id} style={styles.sample} testID="bb-sample">
                    <Text style={styles.name} numberOfLines={1}>{x.name}</Text>
                    <Text style={adminStyles.muted}>{formatIDR(x.before.price)} → {formatIDR(x.after.price)}</Text>
                  </View>
                ))}
                {!pv.changed ? <Text style={adminStyles.muted} testID="bb-nochange">Tidak ada harga yang berubah.</Text> : null}
              </View>
            )}
          </ScrollView>
          {confirm && saved === null ? <Text style={adminStyles.err} testID="bb-confirm-text">Simpan harga baru untuk {pv?.changed.toLocaleString("id-ID")} produk di {storeName}?</Text> : null}
          {err ? <Text style={adminStyles.err} testID="bb-error">{err}</Text> : null}
          <View style={styles.row}>
            <Pressable testID="bb-close" style={[styles.btn, styles.cancel]} disabled={busy === "save"}
              onPress={() => (confirm ? setConfirm(false) : pv && saved === null ? setPv(null) : onClose())}>
              <Text style={styles.cancelText}>{saved !== null ? "Tutup" : confirm || pv ? "Kembali" : "Batal"}</Text>
            </Pressable>
            {saved === null && (pv ? pv.changed > 0 : kind === "adjust") ? (
              <Pressable testID={pv ? (confirm ? "bb-confirm" : "bb-apply") : "bb-preview-btn"} style={[styles.btn, { backgroundColor: colors.brandPrimary }]} disabled={!!busy}
                onPress={pv ? (confirm ? apply : () => setConfirm(true)) : preview}>
                {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.okText}>{pv ? (confirm ? "Ya, simpan" : "Simpan") : "Lihat pratinjau"}</Text>}
              </Pressable>
            ) : null}
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: spacing.lg },
  box: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, maxHeight: "90%", width: "100%", maxWidth: 520, alignSelf: "center" },
  title: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  sample: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: 4 },
  input: { minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, color: colors.onSurface, backgroundColor: colors.surfaceSecondary },
  outline: { minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  outlineText: { color: colors.brandPrimary, fontWeight: "600" },
  row: { flexDirection: "row", gap: spacing.sm },
  btn: { flex: 1, minHeight: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  cancel: { borderWidth: 1, borderColor: colors.border },
  cancelText: { color: colors.onSurface, fontWeight: "600" },
  okText: { color: colors.onBrandPrimary, fontWeight: "600" },
});
