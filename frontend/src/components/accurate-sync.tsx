import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Switch } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type AccuratePreview, type AccurateSyncResult } from "@/src/api";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { fmtDate } from "@/src/utils/date";

const SHOW = 60;

/** Tahap 2A — tarik harga, stok per cabang & barang baru dari Accurate. Pratinjau dulu, simpan hanya setelah Terapkan. */
export function AccurateSync({ connected, lastSyncAt }: { connected: boolean; lastSyncAt?: string | null }) {
  const [opt, setOpt] = useState({ prices: true, stocks: true, new_products: false });
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [pv, setPv] = useState<AccuratePreview | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [skipNew, setSkipNew] = useState<Set<string>>(new Set());
  const [ask, setAsk] = useState(false);
  const [done, setDone] = useState<AccurateSyncResult | null>(null);
  const [more, setMore] = useState(false);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);
  const shownSync = syncedAt ?? lastSyncAt;

  const preview = async () => {
    setBusy("preview"); setErr(""); setDone(null);
    try { setPv(await api.accurateSyncPreview(opt)); setSkip(new Set()); setSkipNew(new Set()); setMore(false); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const apply = async () => {
    if (!pv) return;
    setAsk(false); setBusy("apply"); setErr("");
    try { setDone((await api.accurateSyncApply(pv.preview_id, [...skip], [...skipNew])).result); setPv(null); setSyncedAt(new Date().toISOString()); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const toggle = (set: Set<string>, key: string, upd: (s: Set<string>) => void) => {
    const n = new Set(set);
    if (n.has(key)) n.delete(key); else n.add(key);
    upd(n);
  };

  const chosen = pv ? pv.changes.filter((c) => !skip.has(c.key)).length + pv.new_items.filter((i) => !skipNew.has(i.no)).length : 0;
  const rows = pv ? (more ? pv.changes : pv.changes.slice(0, SHOW)) : [];

  return (
    <View style={[styles.card, !connected && { opacity: 0.6 }]} testID="accurate-sync">
      <Text style={styles.h}>4. Ambil Produk, Harga & Stok dari Accurate</Text>
      <Text style={styles.small}>Kode barang Accurate dicocokkan dengan SKU katalog PGS. Harga jual berlaku untuk semua cabang; stok diambil per cabang dari gudang yang dipetakan. Accurate tidak diubah.</Text>
      {shownSync ? <Text style={styles.small} testID="accurate-last-sync">Terakhir diterapkan: {fmtDate(shownSync)}</Text> : null}
      {([["prices", "Harga jual"], ["stocks", "Stok per cabang"], ["new_products", "Barang baru (dibuat nonaktif)"]] as const).map(([k, label]) => (
        <View key={k} style={styles.switchRow}>
          <Text style={[styles.label, { flex: 1 }]}>{label}</Text>
          <Switch testID={`accurate-opt-${k}`} value={opt[k]} onValueChange={(v) => setOpt((o) => ({ ...o, [k]: v }))}
            trackColor={{ true: colors.brandPrimary, false: colors.border }} />
        </View>
      ))}
      <Pressable testID="accurate-sync-preview" style={styles.outline} onPress={preview} disabled={!connected || !!busy || !(opt.prices || opt.stocks || opt.new_products)}>
        {busy === "preview" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Buat Pratinjau Perubahan</Text>}
      </Pressable>
      {busy === "preview" ? <Text style={styles.small}>Membaca semua barang dari Accurate, bisa sampai 1 menit…</Text> : null}

      {pv ? (
        <View style={{ gap: spacing.sm }} testID="accurate-preview">
          <Text style={styles.small} testID="accurate-preview-summary">
            {pv.accurate_total} barang di Accurate · {pv.matched} cocok · {pv.counts.price} harga · {pv.counts.stock} stok · {pv.counts.new} barang baru
            {pv.counts.skipped ? ` · ${pv.counts.skipped} dilewati (bervariasi)` : ""}
          </Text>
          {!pv.changes.length && !pv.new_items.length ? <Text style={styles.label} testID="accurate-preview-empty">Semua sudah sama, tidak ada perubahan.</Text> : null}
          {rows.map((c) => {
            const on = !skip.has(c.key);
            return (
              <Pressable key={c.key} style={styles.item} onPress={() => toggle(skip, c.key, setSkip)} testID={`accurate-change-${c.key}`}>
                <Icon name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.brandPrimary : colors.muted} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.label} numberOfLines={2}>{c.name}</Text>
                  <Text style={styles.small}>
                    {c.field === "price" ? `Harga: ${formatIDR(c.before)} → ${formatIDR(c.after)}` : `Stok ${c.store_name}: ${c.before} → ${c.after}`} · {c.sku}
                  </Text>
                </View>
              </Pressable>
            );
          })}
          {pv.changes.length > SHOW && !more ? (
            <Pressable onPress={() => setMore(true)} hitSlop={8}><Text style={styles.link}>Tampilkan semua {pv.changes.length} perubahan</Text></Pressable>
          ) : null}
          {pv.new_items.slice(0, SHOW).map((i) => {
            const on = !skipNew.has(i.no);
            return (
              <Pressable key={i.no} style={styles.item} onPress={() => toggle(skipNew, i.no, setSkipNew)} testID={`accurate-new-${i.no}`}>
                <Icon name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.brandPrimary : colors.muted} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.label} numberOfLines={2}>Baru: {i.name}</Text>
                  <Text style={styles.small}>{i.no} · {formatIDR(i.price)} · dibuat nonaktif, lengkapi foto & kategori dulu</Text>
                </View>
              </Pressable>
            );
          })}
          {pv.truncated ? <Text style={styles.small}>Daftar terlalu panjang; hanya sebagian yang ditampilkan dan diterapkan sesuai pratinjau tersimpan.</Text> : null}
          {chosen ? (
            <Pressable testID="accurate-sync-apply" style={styles.primary} onPress={() => setAsk(true)} disabled={!!busy}>
              {busy === "apply" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Terapkan {chosen} Perubahan ke PGS</Text>}
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {done ? (
        <Text style={[styles.small, { color: colors.success }]} testID="accurate-sync-done">
          Tersimpan: {done.price} harga, {done.stock} stok, {done.new} barang baru{done.conflict ? ` · ${done.conflict} dilewati karena sudah diubah di PGS setelah pratinjau` : ""}. Tercatat di Riwayat Perubahan.
        </Text>
      ) : null}
      {err ? <Text style={[styles.small, { color: colors.error }]} testID="accurate-sync-error">{err}</Text> : null}
      <ConfirmDialog visible={ask} title="Terapkan perubahan?" danger={false} confirmLabel="Ya, terapkan"
        message={`${chosen} perubahan harga/stok/barang akan disimpan di PGS dan langsung terlihat pembeli. Data di Accurate tidak berubah.`}
        onConfirm={apply} onCancel={() => setAsk(false)} />
    </View>
  );
}

export const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  small: { fontSize: 13, color: colors.onSurfaceSecondary },
  label: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  link: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  switchRow: { flexDirection: "row", alignItems: "center", minHeight: 44 },
  primary: { minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600" },
  outline: { minHeight: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  outlineText: { color: colors.brandPrimary, fontWeight: "600" },
  item: { flexDirection: "row", gap: spacing.sm, alignItems: "center", paddingVertical: 6, minHeight: 44, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  input: { minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, color: colors.onSurface, backgroundColor: colors.surface },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  pill: { minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center" },
  pillOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
});
