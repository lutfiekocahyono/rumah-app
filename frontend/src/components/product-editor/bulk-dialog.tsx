import React, { useEffect, useState } from "react";
import { Modal, View, Text, Pressable, StyleSheet, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform } from "react-native";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type BulkEdit } from "@/src/api";
import { Input, Pill, digitsOf, rupiah } from "./ui";

export type BulkKind = "price" | "stock" | "status" | "weight";
const PRICE_MODES = [
  { id: "set", label: "Atur jadi (Rp)" }, { id: "up_pct", label: "Naik %" }, { id: "down_pct", label: "Turun %" },
  { id: "up", label: "Naik Rp" }, { id: "down", label: "Turun Rp" },
] as const;
const STOCK_MODES = [{ id: "set", label: "Atur jadi" }, { id: "add", label: "Tambah" }, { id: "sub", label: "Kurangi" }] as const;
const TITLE: Record<BulkKind, string> = { price: "Ubah Harga Massal", stock: "Ubah Stok Massal", status: "Ubah Status Massal", weight: "Isi Berat Massal" };

/** Apply one change (price, stock or status) to all selected products, then show what was skipped. */
export function BulkDialog({ kind, ids, storeId, onClose, onDone }: {
  kind: BulkKind | null; ids: string[]; storeId: string | null; onClose: () => void; onDone: () => void;
}) {
  const [priceMode, setPriceMode] = useState<NonNullable<BulkEdit["price_mode"]>>("set");
  const [stockMode, setStockMode] = useState<NonNullable<BulkEdit["stock_mode"]>>("set");
  const [status, setStatus] = useState<"active" | "inactive">("active");
  const [value, setValue] = useState(0);
  const [onlyMissing, setOnlyMissing] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<{ updated: number; skipped: { product_id: string; name: string; reason: string }[] } | null>(null);

  useEffect(() => { if (kind) { setValue(0); setErr(""); setResult(null); } }, [kind]);

  const pct = kind === "price" && (priceMode === "up_pct" || priceMode === "down_pct");
  const apply = async () => {
    if (kind === "price" && priceMode === "set" && value < 100) return setErr("Harga minimal Rp100");
    if (pct && (value < 1 || value > (priceMode === "down_pct" ? 99 : 500))) return setErr(priceMode === "down_pct" ? "Isi 1–99%" : "Isi 1–500%");
    if (kind === "price" && !pct && priceMode !== "set" && value < 1) return setErr("Isi nominal perubahan harga");
    if (kind === "stock" && stockMode !== "set" && value < 1) return setErr("Isi jumlah stok");
    if (kind === "weight" && (value < 1 || value > 500000)) return setErr("Isi berat 1–500.000 gram");
    setBusy(true);
    setErr("");
    try {
      const body: BulkEdit = { store_id: storeId, product_ids: ids };
      if (kind === "price") Object.assign(body, { price_mode: priceMode, price_value: value });
      if (kind === "stock") Object.assign(body, { stock_mode: stockMode, stock_value: value });
      if (kind === "status") body.status = status;
      if (kind === "weight") Object.assign(body, { weight_grams: value, weight_only_missing: onlyMissing });
      const out = { updated: 0, skipped: [] as { product_id: string; name: string; reason: string }[] };
      for (let i = 0; i < ids.length; i += 500) { // server accepts 500 per request
        const r = await api.editorBulk({ ...body, product_ids: ids.slice(i, i + 500) });
        out.updated += r.updated;
        out.skipped.push(...r.skipped);
      }
      setResult(out);
      onDone();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <Modal visible={!!kind} transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.backdrop}>
        <View style={s.box} testID="bulk-dialog">
          <Text style={s.title}>{kind ? TITLE[kind] : ""}</Text>
          <Text style={s.sub}>{ids.length} produk dipilih</Text>
          {result ? (
            <ScrollView style={{ maxHeight: 320 }} contentContainerStyle={{ gap: spacing.sm }}>
              <Text style={result.updated ? s.ok : s.errText} testID="bulk-result">{result.updated} produk berhasil diubah</Text>
              {result.skipped.length ? <Text style={s.errText}>{result.skipped.length} dilewati:</Text> : null}
              {result.skipped.map((x) => (
                <Text key={x.product_id} style={s.sub} testID="bulk-skipped">• {x.name || x.product_id}: {x.reason}</Text>
              ))}
            </ScrollView>
          ) : (
            <View style={{ gap: spacing.md }}>
              {kind === "price" ? (
                <>
                  <View style={s.pills}>{PRICE_MODES.map((m) => <Pill key={m.id} testID={`bulk-price-${m.id}`} label={m.label} on={priceMode === m.id} onPress={() => { setPriceMode(m.id); setValue(0); }} />)}</View>
                  <Input testID="bulk-value" label={pct ? "Persentase" : "Nominal"} prefix={pct ? "%" : "Rp"} keyboardType="number-pad"
                    value={pct ? (value ? String(value) : "") : rupiah(value)} onChangeText={(t) => setValue(digitsOf(t))} placeholder="0"
                    hint={priceMode === "set" ? "Harga diskon tetap berlaku jika masih lebih kecil dari harga baru" : "Harga diskon & harga tiap variasi ikut berubah"} />
                </>
              ) : kind === "stock" ? (
                <>
                  <View style={s.pills}>{STOCK_MODES.map((m) => <Pill key={m.id} testID={`bulk-stock-${m.id}`} label={m.label} on={stockMode === m.id} onPress={() => setStockMode(m.id)} />)}</View>
                  <Input testID="bulk-value" label="Jumlah" keyboardType="number-pad" value={value ? String(value) : ""} onChangeText={(t) => setValue(Math.min(999999, digitsOf(t)))}
                    placeholder="0" hint="Produk bervariasi: berlaku untuk setiap variasi" />
                </>
              ) : kind === "weight" ? (
                <>
                  <Input testID="bulk-value" label="Berat kemasan (gram)" keyboardType="number-pad" value={value ? String(value) : ""} onChangeText={(t) => setValue(Math.min(500000, digitsOf(t)))}
                    placeholder="Mis. 1200" hint="Dipakai menghitung ongkir. Berat ini dianggap sudah dicek (tanda perkiraan dihapus)." />
                  <View style={s.pills}>
                    <Pill testID="bulk-weight-missing" label="Hanya yang belum ada berat" on={onlyMissing} onPress={() => setOnlyMissing(true)} />
                    <Pill testID="bulk-weight-all" label="Timpa semua yang dipilih" on={!onlyMissing} onPress={() => setOnlyMissing(false)} />
                  </View>
                </>
              ) : (
                <View style={s.pills}>
                  <Pill testID="bulk-status-active" label="Aktifkan (tampil)" icon="eye-outline" on={status === "active"} onPress={() => setStatus("active")} />
                  <Pill testID="bulk-status-inactive" label="Nonaktifkan (sembunyikan)" icon="eye-off-outline" on={status === "inactive"} onPress={() => setStatus("inactive")} />
                </View>
              )}
              {err ? <Text style={s.errText} testID="bulk-error">{err}</Text> : null}
            </View>
          )}
          <View style={s.row}>
            <Pressable testID="bulk-close" style={[s.btn, s.cancel]} onPress={onClose} disabled={busy}>
              <Text style={s.cancelText}>{result ? "Tutup" : "Batal"}</Text>
            </Pressable>
            {!result ? (
              <Pressable testID="bulk-apply" style={[s.btn, { backgroundColor: colors.brandPrimary }]} onPress={apply} disabled={busy}>
                {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.okText}>Terapkan</Text>}
              </Pressable>
            ) : null}
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

export const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  box: { width: "100%", maxWidth: 480, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md },
  title: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  sub: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  ok: { fontSize: fontSize.base, color: colors.success, fontWeight: "600" },
  errText: { fontSize: fontSize.sm, color: colors.error },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  row: { flexDirection: "row", gap: spacing.md, marginTop: spacing.sm },
  btn: { flex: 1, minHeight: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md },
  cancel: { borderWidth: 1, borderColor: colors.border },
  cancelText: { color: colors.onSurface, fontWeight: "600" },
  okText: { color: colors.onBrandPrimary, fontWeight: "600" },
});
