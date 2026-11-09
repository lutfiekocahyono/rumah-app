import React, { useEffect, useMemo, useState } from "react";
import { Modal, View, Text, Pressable, ActivityIndicator, FlatList, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, spacing } from "@/src/theme";
import { api, type EstimateKind, type WeightPreview } from "@/src/api";
import { digitsOf } from "./ui";
import { s } from "./bulk-dialog";

const parseDims = (t: string) => t.split(/[^0-9]+/).filter(Boolean).slice(0, 3).map(Number);
const dimsOk = (d: number[]) => d.length === 3 && d.every((x) => x >= 1 && x <= 500);

/** Usulan berat / ukuran dus untuk produk yang belum punya: pratinjau, ubah/buang per baris, lalu simpan setelah konfirmasi. */
export function WeightEstimateDialog({ visible, kind = "weight", storeId, onClose, onDone }: { visible: boolean; kind?: EstimateKind; storeId: string | null; onClose: () => void; onDone: () => void }) {
  const dimsKind = kind === "dims";
  const [pv, setPv] = useState<WeightPreview | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [over, setOver] = useState<Record<string, number>>({});
  const [overDims, setOverDims] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    if (!visible) return;
    setPv(null); setSkip(new Set()); setOver({}); setOverDims({}); setQ(""); setErr(""); setSaved(null); setConfirm(false); setBusy("load");
    api.weightPreview(storeId, kind).then(setPv).catch((e) => setErr(e.message)).finally(() => setBusy(""));
  }, [visible, storeId, kind]);

  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (pv?.items ?? []).filter((i) => !t || i.name.toLowerCase().includes(t) || i.rule.toLowerCase().includes(t));
  }, [pv, q]);
  const valid = (i: WeightPreview["items"][number]) =>
    dimsKind ? dimsOk(overDims[i.product_id] != null ? parseDims(overDims[i.product_id]) : i.dims ?? []) : (over[i.product_id] ?? i.grams ?? 0) > 0;
  const chosen = (pv?.items ?? []).filter((i) => !skip.has(i.product_id) && valid(i)).length;

  const apply = async () => {
    if (!pv) return;
    setBusy("save"); setErr("");
    const overrides: Record<string, number | number[]> = dimsKind
      ? Object.fromEntries(Object.entries(overDims).map(([k, v]) => [k, parseDims(v)]).filter(([, d]) => dimsOk(d as number[])))
      : over;
    try { setSaved((await api.weightApply(pv.preview_id, [...skip, ...pv.items.filter((i) => !valid(i)).map((i) => i.product_id)], overrides, kind)).saved); onDone(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); setConfirm(false); }
  };
  const toggle = (id: string) => setSkip((x) => { const n = new Set(x); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.backdrop}>
        <View style={[s.box, { maxHeight: "90%" }]} testID="weight-estimate-dialog">
          <Text style={s.title}>{dimsKind ? "Perkiraan Ukuran Dus Otomatis" : "Perkiraan Berat Otomatis"}</Text>
          <Text style={s.sub}>Usulan dari nama & kategori produk (mis. AC, TV, dispenser, speaker). Cek, ubah angka{dimsKind ? " (P×L×T cm)" : ""}, atau buang centang sebelum disimpan. Produk akan ditandai “{dimsKind ? "Ukuran perkiraan" : "Berat perkiraan"}” sampai dikoreksi.</Text>
          {busy === "load" ? <ActivityIndicator color={colors.brandPrimary} /> : null}
          {saved !== null ? (
            <Text style={s.ok} testID="weight-saved">{saved.toLocaleString("id-ID")} produk diberi {dimsKind ? "ukuran dus" : "berat"} perkiraan. Filter “{dimsKind ? "Ukuran perkiraan" : "Berat perkiraan"}” untuk mengoreksinya.</Text>
          ) : pv ? (
            <>
              <Text style={s.sub} testID="weight-summary">{pv.total.toLocaleString("id-ID")} produk tanpa {dimsKind ? "ukuran dus" : "berat"} · {chosen.toLocaleString("id-ID")} akan disimpan</Text>
              <Text style={s.sub} numberOfLines={3}>{pv.groups.slice(0, 8).map((g) => `${g.rule} ${g.count}`).join(" · ")}</Text>
              <TextInput testID="weight-search" value={q} onChangeText={setQ} placeholder="Cari nama / jenis (mis. tv)" placeholderTextColor={colors.muted}
                style={{ minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: spacing.md, color: colors.onSurface }} />
              <FlatList
                style={{ maxHeight: 340 }}
                data={rows}
                keyExtractor={(i) => i.product_id}
                initialNumToRender={20}
                keyboardShouldPersistTaps="handled"
                renderItem={({ item }) => {
                  const on = !skip.has(item.product_id);
                  return (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 52, borderTopWidth: 0.5, borderTopColor: colors.border }} testID={`weight-row-${item.product_id}`}>
                      <Pressable hitSlop={8} onPress={() => toggle(item.product_id)} testID={`weight-check-${item.product_id}`}>
                        <Icon name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.brandPrimary : colors.muted} />
                      </Pressable>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 13, color: colors.onSurface }} numberOfLines={2}>{item.name}</Text>
                        <Text style={s.sub} numberOfLines={1}>{item.rule}</Text>
                      </View>
                      {dimsKind ? (
                        <TextInput testID={`weight-input-${item.product_id}`} editable={on} autoCapitalize="none"
                          value={overDims[item.product_id] ?? (item.dims ?? []).join("×")} onChangeText={(t) => setOverDims((o) => ({ ...o, [item.product_id]: t }))}
                          style={{ width: 110, minHeight: 40, borderWidth: 1, borderColor: dimsOk(parseDims(overDims[item.product_id] ?? (item.dims ?? []).join("×"))) ? colors.border : colors.error, borderRadius: 8, textAlign: "right", paddingHorizontal: 6, color: colors.onSurface }} />
                      ) : (
                        <TextInput testID={`weight-input-${item.product_id}`} keyboardType="number-pad" editable={on}
                          value={String(over[item.product_id] ?? item.grams)} onChangeText={(t) => setOver((o) => ({ ...o, [item.product_id]: Math.min(500000, digitsOf(t)) }))}
                          style={{ width: 84, minHeight: 40, borderWidth: 1, borderColor: colors.border, borderRadius: 8, textAlign: "right", paddingHorizontal: 6, color: colors.onSurface }} />
                      )}
                      <Text style={s.sub}>{dimsKind ? "cm" : "g"}</Text>
                    </View>
                  );
                }}
              />
            </>
          ) : null}
          {confirm && saved === null ? <Text style={s.errText} testID="weight-confirm-text">Simpan {dimsKind ? "ukuran dus" : "berat"} perkiraan untuk {chosen.toLocaleString("id-ID")} produk? Ini mempengaruhi ongkir; produk tetap bertanda perkiraan.</Text> : null}
          {err ? <Text style={s.errText} testID="weight-error">{err}</Text> : null}
          <View style={s.row}>
            <Pressable testID="weight-close" style={[s.btn, s.cancel]} onPress={confirm && saved === null ? () => setConfirm(false) : onClose} disabled={busy === "save"}>
              <Text style={s.cancelText}>{saved !== null ? "Tutup" : confirm ? "Kembali" : "Batal"}</Text>
            </Pressable>
            {saved === null && pv && chosen > 0 ? (
              <Pressable testID={confirm ? "weight-confirm" : "weight-apply"} style={[s.btn, { backgroundColor: colors.brandPrimary }]} onPress={confirm ? apply : () => setConfirm(true)} disabled={!!busy}>
                {busy === "save" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.okText}>{confirm ? "Ya, simpan" : `Simpan ${chosen.toLocaleString("id-ID")}`}</Text>}
              </Pressable>
            ) : null}
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
