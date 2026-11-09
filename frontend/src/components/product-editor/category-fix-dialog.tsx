import React, { useEffect, useMemo, useState } from "react";
import { Modal, View, Text, Pressable, ActivityIndicator, FlatList, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, spacing } from "@/src/theme";
import { api, type Category, type CategoryPreview } from "@/src/api";
import { s } from "./bulk-dialog";

const CONF_COLOR = { tinggi: colors.success, sedang: colors.warning, rendah: colors.error } as const;
const inputStyle = { minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: spacing.md, color: colors.onSurface } as const;

/** Rapikan produk berkategori "Lainnya": usulan kategori per produk, ubah/buang per baris, simpan setelah konfirmasi. */
export function CategoryFixDialog({ visible, storeId, onClose, onDone }: { visible: boolean; storeId: string | null; onClose: () => void; onDone: () => void }) {
  const [pv, setPv] = useState<CategoryPreview | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [over, setOver] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [picking, setPicking] = useState<string | null>(null);
  const [catQ, setCatQ] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    if (!visible) return;
    setPv(null); setSkip(new Set()); setOver({}); setQ(""); setPicking(null); setErr(""); setSaved(null); setConfirm(false); setBusy("load");
    Promise.all([api.uncatPreview(storeId), api.allCategories()]).then(([p, c]) => { setPv(p); setCats(c); })
      .catch((e) => setErr(e.message)).finally(() => setBusy(""));
  }, [visible, storeId]);

  const byId = useMemo(() => Object.fromEntries(cats.map((c) => [c.category_id, c])), [cats]);
  const label = (id: string) => {
    const c = byId[id];
    if (!c) return "Pilih kategori";
    const p = c.parent ? byId[c.parent] : null;
    return p ? `${p.name} › ${c.name}` : c.name;
  };
  const catOf = (i: CategoryPreview["items"][number]) => over[i.product_id] ?? i.suggested;
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (pv?.items ?? []).filter((i) => !t || i.name.toLowerCase().includes(t) || label(catOf(i)).toLowerCase().includes(t));
  }, [pv, q, over, byId]); // eslint-disable-line react-hooks/exhaustive-deps
  const catRows = useMemo(() => {
    const t = catQ.trim().toLowerCase();
    return cats.filter((c) => !t || label(c.category_id).toLowerCase().includes(t)).sort((a, b) => label(a.category_id).localeCompare(label(b.category_id)));
  }, [cats, catQ, byId]); // eslint-disable-line react-hooks/exhaustive-deps
  const chosen = (pv?.items ?? []).filter((i) => !skip.has(i.product_id) && byId[catOf(i)]).length;

  const apply = async () => {
    if (!pv) return;
    setBusy("save"); setErr("");
    try {
      const sk = [...skip, ...pv.items.filter((i) => !byId[catOf(i)]).map((i) => i.product_id)];
      setSaved((await api.uncatApply(pv.preview_id, sk, over)).saved); onDone();
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); setConfirm(false); }
  };
  const toggle = (id: string) => setSkip((x) => { const n = new Set(x); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const pickedName = picking ? pv?.items.find((i) => i.product_id === picking)?.name : "";

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={picking ? () => setPicking(null) : onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.backdrop}>
        <View style={[s.box, { maxHeight: "90%" }]} testID="catfix-dialog">
          {picking ? (
            <>
              <Text style={s.title}>Pilih kategori</Text>
              <Text style={s.sub} numberOfLines={2}>{pickedName}</Text>
              <TextInput testID="catfix-cat-search" value={catQ} onChangeText={setCatQ} placeholder="Cari kategori" placeholderTextColor={colors.muted} style={inputStyle} />
              <FlatList style={{ maxHeight: 380 }} data={catRows} keyExtractor={(c) => c.category_id} keyboardShouldPersistTaps="handled"
                renderItem={({ item }) => (
                  <Pressable testID={`catfix-cat-${item.category_id}`} style={{ minHeight: 44, justifyContent: "center", borderTopWidth: 0.5, borderTopColor: colors.border }}
                    onPress={() => { setOver((o) => ({ ...o, [picking]: item.category_id })); setSkip((x) => { const n = new Set(x); n.delete(picking); return n; }); setPicking(null); setCatQ(""); }}>
                    <Text style={{ fontSize: 14, color: colors.onSurface }}>{label(item.category_id)}</Text>
                  </Pressable>
                )} />
              <View style={s.row}>
                <Pressable testID="catfix-cat-back" style={[s.btn, s.cancel]} onPress={() => setPicking(null)}><Text style={s.cancelText}>Kembali</Text></Pressable>
              </View>
            </>
          ) : (
            <>
              <Text style={s.title}>Rapikan Kategori “Lainnya”</Text>
              <Text style={s.sub}>Usulan kategori dari nama produk. Ketuk kategori untuk mengganti, atau buang centang. Tidak ada yang disimpan sebelum Anda konfirmasi.</Text>
              {busy === "load" ? <ActivityIndicator color={colors.brandPrimary} /> : null}
              {saved !== null ? (
                <Text style={s.ok} testID="catfix-saved">{saved.toLocaleString("id-ID")} produk dipindahkan ke kategori yang tepat.</Text>
              ) : pv ? (
                <>
                  <Text style={s.sub} testID="catfix-summary">{pv.total.toLocaleString("id-ID")} produk di “Lainnya” · {chosen.toLocaleString("id-ID")} akan dipindahkan</Text>
                  <TextInput testID="catfix-search" value={q} onChangeText={setQ} placeholder="Cari nama / kategori" placeholderTextColor={colors.muted} style={inputStyle} />
                  <View style={{ flexDirection: "row", gap: spacing.md }}>
                    <Pressable testID="catfix-check-all" style={{ minHeight: 36, justifyContent: "center" }}
                      onPress={() => setSkip((x) => { const n = new Set(x); rows.forEach((i) => n.delete(i.product_id)); return n; })}>
                      <Text style={{ color: colors.brandPrimary, fontWeight: "600", fontSize: 13 }}>Centang semua yang tampil</Text>
                    </Pressable>
                    <Pressable testID="catfix-uncheck-all" style={{ minHeight: 36, justifyContent: "center" }}
                      onPress={() => setSkip((x) => { const n = new Set(x); rows.forEach((i) => n.add(i.product_id)); return n; })}>
                      <Text style={{ color: colors.brandPrimary, fontWeight: "600", fontSize: 13 }}>Buang semua centang</Text>
                    </Pressable>
                  </View>
                  <FlatList style={{ maxHeight: 360 }} data={rows} keyExtractor={(i) => i.product_id} initialNumToRender={20} keyboardShouldPersistTaps="handled"
                    renderItem={({ item }) => {
                      const on = !skip.has(item.product_id);
                      const cid = catOf(item);
                      const changed = over[item.product_id] != null;
                      return (
                        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 60, paddingVertical: 4, borderTopWidth: 0.5, borderTopColor: colors.border }} testID={`catfix-row-${item.product_id}`}>
                          <Pressable hitSlop={8} onPress={() => toggle(item.product_id)} testID={`catfix-check-${item.product_id}`}>
                            <Icon name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.brandPrimary : colors.muted} />
                          </Pressable>
                          <View style={{ flex: 1, gap: 2 }}>
                            <Text style={{ fontSize: 13, color: colors.onSurface }} numberOfLines={2}>{item.name}</Text>
                            <Pressable testID={`catfix-pick-${item.product_id}`} onPress={() => setPicking(item.product_id)} disabled={!on}
                              style={{ flexDirection: "row", alignItems: "center", gap: 4, minHeight: 32, alignSelf: "flex-start", borderWidth: 1, borderColor: byId[cid] ? colors.brandPrimary : colors.error, borderRadius: 16, paddingHorizontal: 10, opacity: on ? 1 : 0.5 }}>
                              <Text style={{ fontSize: 12, color: byId[cid] ? colors.brandPrimary : colors.error, fontWeight: "600" }} numberOfLines={1}>{label(cid)}</Text>
                              <Icon name="chevron-down" size={14} color={colors.brandPrimary} />
                            </Pressable>
                            <Text style={[s.sub, { fontSize: 11 }]} numberOfLines={1}>
                              {changed ? "Diubah manual" : <Text style={{ color: CONF_COLOR[item.confidence] }}>Usulan {item.confidence}</Text>}{changed ? "" : ` · ${item.reason}`}
                            </Text>
                          </View>
                        </View>
                      );
                    }} />
                </>
              ) : null}
              {confirm && saved === null ? <Text style={s.errText} testID="catfix-confirm-text">Pindahkan {chosen.toLocaleString("id-ID")} produk ke kategori yang dipilih? Pembeli tidak menerima notifikasi untuk perubahan ini.</Text> : null}
              {err ? <Text style={s.errText} testID="catfix-error">{err}</Text> : null}
              <View style={s.row}>
                <Pressable testID="catfix-close" style={[s.btn, s.cancel]} onPress={confirm && saved === null ? () => setConfirm(false) : onClose} disabled={busy === "save"}>
                  <Text style={s.cancelText}>{saved !== null ? "Tutup" : confirm ? "Kembali" : "Batal"}</Text>
                </Pressable>
                {saved === null && pv && chosen > 0 ? (
                  <Pressable testID={confirm ? "catfix-confirm" : "catfix-apply"} style={[s.btn, { backgroundColor: colors.brandPrimary }]} onPress={confirm ? apply : () => setConfirm(true)} disabled={!!busy}>
                    {busy === "save" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.okText}>{confirm ? "Ya, simpan" : `Simpan ${chosen.toLocaleString("id-ID")}`}</Text>}
                  </Pressable>
                ) : null}
              </View>
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
