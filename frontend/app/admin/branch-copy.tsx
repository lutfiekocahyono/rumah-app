import React, { useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, spacing, formatIDR } from "@/src/theme";
import { api, type BranchCopyPreview, type BranchCopyRule } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, Chips, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

const BRANCHES = [{ id: "pgs-jombang", name: "Mitra PGS Jombang", add: 2000, pct: 2, sub: 3 }, { id: "pgs-jember", name: "Mitra PGS Jember", add: 1000, pct: 1, sub: 5 }];
const MODES = [{ id: "rp", label: "Rupiah (Rp)" }, { id: "pct", label: "Persen (%)" }] as const;
const num = (t: string) => Number(t.replace(/[^0-9]/g, "")) || 0;
const pctOf = (t: string) => Math.min(100, Number(t.replace(",", ".").replace(/[^0-9.]/g, "")) || 0);
const withPct = (v: number, pct: number) => Math.max(100, Math.ceil((v * (10000 + Math.round(pct * 100))) / 1_000_000) * 100); // same integer math as the server
type R = BranchCopyRule & { name: string; pctText: string };

/** Super Admin: salin harga (Rp atau %) & stok PGS Sidoarjo ke cabang mitra; pratinjau → konfirmasi. Harga yang diubah admin cabang dilindungi. */
export default function BranchCopy() {
  const insets = useSafeAreaInsets();
  const [rules, setRules] = useState<R[]>(BRANCHES.map((b) => ({ store_id: b.id, name: b.name, mode: "rp", price_add: b.add, price_pct: b.pct, pctText: String(b.pct),
    stock_sub: b.sub, copy_price: true, copy_stock: false, overwrite_manual: false })));
  const [pv, setPv] = useState<BranchCopyPreview | null>(null);
  const [busy, setBusy] = useState("");
  const [ask, setAsk] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const edit = (i: number, patch: Partial<R>) => { setPv(null); setRules((r) => r.map((x, n) => (n === i ? { ...x, ...patch } : x))); };

  const preview = async () => {
    setBusy("pv"); setMsg(null);
    try { setPv(await api.branchCopyPreview(rules.map(({ name: _n, pctText: _p, ...r }) => r))); }
    catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(""); }
  };
  const apply = async () => {
    if (!pv) return;
    setAsk(false); setBusy("apply"); setMsg(null);
    try {
      const r = await api.branchCopyApply(pv.preview_id);
      setPv(null);
      setMsg({ ok: true, text: `Selesai: ${r.branches.map((b) => `${b.store_name} ${b.updated.toLocaleString("id-ID")} produk`).join(" · ")}. Tercatat di Riwayat Harga & Stok.` });
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(""); }
  };
  const nothing = rules.every((r) => !r.copy_price && !r.copy_stock);
  const fmt = (n: number) => n.toLocaleString("id-ID");

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="branch-copy-screen">
      <ScreenHeader title="Salin Harga & Stok ke Cabang" />
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
        <Text style={adminStyles.muted}>
          Harga PGS Sidoarjo (termasuk tiap tingkat grosir) disalin ke cabang mitra dengan selisih Rupiah atau Persen. Persen dibulatkan ke atas ke Rp100 terdekat.
          Stok hanya disalin bila dicentang (stok cabang yang sudah berjalan akan ditimpa). Harga yang sudah diubah admin cabang tidak ditimpa kecuali Anda izinkan.
        </Text>
        {rules.map((r, i) => (
          <Card key={r.store_id}>
            <Text style={styles.h}>{r.name}</Text>
            <ToggleRow testID={`bc-copy-price-${r.store_id}`} label="Salin harga" value={r.copy_price} onChange={(v) => edit(i, { copy_price: v })} />
            {r.copy_price ? (
              <>
                <Chips testID={`bc-mode-${r.store_id}`} options={[...MODES]} value={r.mode} onChange={(v) => edit(i, { mode: v })} />
                {r.mode === "rp" ? (
                  <Field testID={`bc-add-${r.store_id}`} label="Harga ditambah (Rp)" keyboardType="number-pad" value={r.price_add ? String(r.price_add) : ""}
                    onChangeText={(t) => edit(i, { price_add: Math.min(1000000, num(t)) })} />
                ) : (
                  <Field testID={`bc-pct-${r.store_id}`} label="Harga ditambah (%)" keyboardType="decimal-pad" value={r.pctText}
                    hint={`Contoh: Rp10.000 → ${formatIDR(withPct(10000, r.price_pct))} · Rp200.000 → ${formatIDR(withPct(200000, r.price_pct))}`}
                    onChangeText={(t) => edit(i, { pctText: pctOf(t) >= 100 ? "100" : t.replace(/[^0-9.,]/g, ""), price_pct: pctOf(t) })} />
                )}
              </>
            ) : null}
            <ToggleRow testID={`bc-copy-stock-${r.store_id}`} label="Salin stok juga" sub="Stok cabang = stok Sidoarjo − pengurang (min 0)" value={r.copy_stock} onChange={(v) => edit(i, { copy_stock: v })} />
            {r.copy_stock ? (
              <Field testID={`bc-sub-${r.store_id}`} label="Stok dikurangi" keyboardType="number-pad" value={r.stock_sub ? String(r.stock_sub) : ""} onChangeText={(t) => edit(i, { stock_sub: Math.min(100000, num(t)) })} />
            ) : null}
          </Card>
        ))}
        <PrimaryButton testID="bc-preview" label={pv ? "Hitung ulang pratinjau" : "Lihat pratinjau"} variant="outline" loading={busy === "pv"} onPress={() => (nothing ? setMsg({ ok: false, text: "Centang Salin harga atau Salin stok dulu" }) : preview())} />
        {pv ? pv.branches.map((b) => {
          const i = rules.findIndex((r) => r.store_id === b.store_id);
          return (
            <Card key={b.store_id}>
              <Text style={styles.h} testID={`bc-sum-${b.store_id}`}>{b.store_name}: {fmt(b.total - b.unchanged)} dari {fmt(b.total)} produk berubah</Text>
              <Text style={adminStyles.muted}>Harga berubah {fmt(b.price_changed)} · stok berubah {fmt(b.stock_changed)}{rules[i]?.copy_stock ? ` · stok jadi 0: ${fmt(b.zero_stock)}` : ""}</Text>
              {b.big_rise ? <Text style={adminStyles.err} testID={`bc-big-${b.store_id}`}>{fmt(b.big_rise)} produk naik 50% atau lebih dari harga Sidoarjo.</Text> : null}
              {b.protected || b.protected_overwritten ? (
                <View style={styles.warn} testID={`bc-protected-${b.store_id}`}>
                  <Text style={styles.name}>
                    {b.protected ? `${fmt(b.protected)} produk sudah diubah admin cabang dan TIDAK ditimpa.` : `${fmt(b.protected_overwritten)} harga yang diubah admin cabang AKAN ditimpa.`}
                  </Text>
                  {b.protected_sample.slice(0, 5).map((x) => (
                    <Text key={x.product_id} style={adminStyles.muted} numberOfLines={2}>{x.name}: tetap {formatIDR(x.branch_price)} (aturan: {formatIDR(x.would_be)})</Text>
                  ))}
                  <ToggleRow testID={`bc-overwrite-${b.store_id}`} label="Timpa juga harga yang diubah admin cabang" value={!!rules[i]?.overwrite_manual}
                    onChange={(v) => { edit(i, { overwrite_manual: v }); setMsg({ ok: true, text: "Tekan Hitung ulang pratinjau untuk melihat hasilnya" }); }} />
                </View>
              ) : null}
              {b.sample.slice(0, 8).map((x) => (
                <View key={x.product_id} style={styles.sample} testID="bc-sample">
                  <Text style={styles.name} numberOfLines={1}>{x.name}</Text>
                  <Text style={adminStyles.muted}>Harga {formatIDR(x.old_price)} → {formatIDR(x.new_price)} (Sidoarjo {formatIDR(x.sidoarjo_price)}) · Stok {x.old_stock} → {x.new_stock}</Text>
                </View>
              ))}
            </Card>
          );
        }) : null}
        {pv ? <PrimaryButton testID="bc-apply" label="Terapkan ke cabang" loading={busy === "apply"} onPress={() => setAsk(true)} /> : null}
        {msg ? <Text style={msg.ok ? adminStyles.ok : adminStyles.err} testID={msg.ok ? "bc-msg-ok" : "bc-msg-error"}>{msg.text}</Text> : null}
      </KeyboardAwareScrollView>
      <ConfirmDialog visible={ask} title="Terapkan ke cabang?" confirmLabel="Ya, terapkan" danger={false}
        message={pv ? pv.branches.map((b) => `${b.store_name}: ${fmt(b.total - b.unchanged)} produk diubah${b.protected ? `, ${fmt(b.protected)} harga admin cabang dilewati` : ""}${b.protected_overwritten ? `, ${fmt(b.protected_overwritten)} harga admin cabang DITIMPA` : ""}`).join("\n") + "\nPerubahan tercatat di Riwayat Harga & Stok." : ""}
        onCancel={() => setAsk(false)} onConfirm={apply} />
    </View>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  sample: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: 6, gap: 2 },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  warn: { backgroundColor: colors.surfaceSecondary, borderRadius: 8, padding: spacing.sm, gap: 4, borderLeftWidth: 3, borderLeftColor: colors.warning },
});
