import React, { useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, spacing, formatIDR } from "@/src/theme";
import { api, type BranchCopyPreview } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, Field, PrimaryButton } from "@/src/components/admin-form";

const BRANCHES = [{ id: "pgs-jombang", name: "Mitra PGS Jombang", add: 2000, sub: 3 }, { id: "pgs-jember", name: "Mitra PGS Jember", add: 1000, sub: 5 }];
const num = (t: string) => Number(t.replace(/[^0-9]/g, "")) || 0;

/** Super Admin: salin semua harga & stok PGS Sidoarjo ke cabang mitra dengan selisih harga & pengurang stok; pratinjau → konfirmasi. */
export default function BranchCopy() {
  const insets = useSafeAreaInsets();
  const [rules, setRules] = useState(BRANCHES.map((b) => ({ store_id: b.id, name: b.name, price_add: b.add, stock_sub: b.sub })));
  const [pv, setPv] = useState<BranchCopyPreview | null>(null);
  const [busy, setBusy] = useState("");
  const [ask, setAsk] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const edit = (i: number, k: "price_add" | "stock_sub", v: number) => { setPv(null); setRules((r) => r.map((x, n) => (n === i ? { ...x, [k]: v } : x))); };

  const preview = async () => {
    setBusy("pv"); setMsg(null);
    try { setPv(await api.branchCopyPreview(rules.map(({ store_id, price_add, stock_sub }) => ({ store_id, price_add, stock_sub })))); }
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

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="branch-copy-screen">
      <ScreenHeader title="Salin Harga & Stok ke Cabang" />
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}>
        <Text style={adminStyles.muted}>
          Semua produk PGS Sidoarjo disalin ke cabang mitra: harga (termasuk tiap tingkat harga grosir) ditambah selisih, stok dikurangi pengurang.
          Stok tidak pernah minus (paling kecil 0). Harga & stok cabang yang sudah ada ditimpa. Harga cabang berdiri sendiri: perubahan harga Sidoarjo nanti tidak ikut.
        </Text>
        {rules.map((r, i) => (
          <Card key={r.store_id}>
            <Text style={styles.h}>{r.name}</Text>
            <View style={styles.row}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Field testID={`bc-add-${r.store_id}`} label="Harga ditambah (Rp)" keyboardType="number-pad" value={r.price_add ? String(r.price_add) : ""} onChangeText={(t) => edit(i, "price_add", Math.min(1000000, num(t)))} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Field testID={`bc-sub-${r.store_id}`} label="Stok dikurangi" keyboardType="number-pad" value={r.stock_sub ? String(r.stock_sub) : ""} onChangeText={(t) => edit(i, "stock_sub", Math.min(100000, num(t)))} />
              </View>
            </View>
          </Card>
        ))}
        <PrimaryButton testID="bc-preview" label={pv ? "Hitung ulang pratinjau" : "Lihat pratinjau"} variant="outline" loading={busy === "pv"} onPress={preview} />
        {pv ? pv.branches.map((b) => (
          <Card key={b.store_id}>
            <Text style={styles.h} testID={`bc-sum-${b.store_id}`}>{b.store_name}: {(b.total - b.unchanged).toLocaleString("id-ID")} dari {b.total.toLocaleString("id-ID")} produk berubah</Text>
            <Text style={adminStyles.muted}>Harga berubah {b.price_changed.toLocaleString("id-ID")} · stok berubah {b.stock_changed.toLocaleString("id-ID")} · stok jadi 0: {b.zero_stock.toLocaleString("id-ID")}</Text>
            {b.sample.slice(0, 8).map((x) => (
              <View key={x.product_id} style={styles.sample} testID="bc-sample">
                <Text style={styles.name} numberOfLines={1}>{x.name}</Text>
                <Text style={adminStyles.muted}>Harga {formatIDR(x.old_price)} → {formatIDR(x.new_price)} · Stok {x.old_stock} → {x.new_stock} (Sidoarjo {x.sidoarjo_stock})</Text>
              </View>
            ))}
          </Card>
        )) : null}
        {pv ? <PrimaryButton testID="bc-apply" label="Terapkan ke cabang" loading={busy === "apply"} onPress={() => setAsk(true)} /> : null}
        {msg ? <Text style={msg.ok ? adminStyles.ok : adminStyles.err} testID={msg.ok ? "bc-msg-ok" : "bc-msg-error"}>{msg.text}</Text> : null}
      </KeyboardAwareScrollView>
      <ConfirmDialog visible={ask} title="Terapkan harga & stok?" confirmLabel="Ya, terapkan" danger={false}
        message={pv ? pv.branches.map((b) => `${b.store_name}: ${(b.total - b.unchanged).toLocaleString("id-ID")} produk ditimpa`).join("\n") + "\nHarga & stok lama cabang diganti dan tercatat di Riwayat." : ""}
        onCancel={() => setAsk(false)} onConfirm={apply} />
    </View>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  row: { flexDirection: "row", gap: spacing.md },
  sample: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: 6, gap: 2 },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
});
