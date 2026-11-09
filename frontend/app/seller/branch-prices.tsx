import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, TextInput, Pressable, Modal, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type BranchPriceItem } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Chips } from "@/src/components/admin-form";

const BRANCHES = [{ id: "pgs-jombang", label: "Mitra PGS Jombang" }, { id: "pgs-jember", label: "Mitra PGS Jember" }];
const TYPES = [{ id: "langsung", label: "Pembeli Langsung" }, { id: "pengecer", label: "Pengecer" }, { id: "reseller", label: "Reseller" }];
type Tier = { min_qty: string; price: string };
const digits = (t: string) => t.replace(/[^0-9]/g, "");

/** Harga cabang: admin cabang mengubah harga tokonya sendiri; Super Admin memilih cabang. Sidoarjo tidak ikut berubah. */
export default function BranchPrices() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const [branch, setBranch] = useState("pgs-jombang");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<BranchPriceItem[] | null>(null);
  const [storeName, setStoreName] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const [editing, setEditing] = useState<BranchPriceItem | null>(null);
  const reqId = useRef(0);

  const load = useCallback(async (reset: boolean, from: number) => {
    const id = ++reqId.current; // a newer load (branch switch / search) wins; stale answers are dropped
    try {
      const r = await api.branchPrices(admin ? branch : null, q, from);
      if (id !== reqId.current) return;
      setStoreName(r.store_name); setErr("");
      setItems((cur) => (reset ? r.items : [...(cur ?? []), ...r.items.filter((p) => !(cur ?? []).some((c) => c.product_id === p.product_id))]));
      setDone(r.items.length < 40);
    } catch (e: any) { if (id === reqId.current) { setErr(e.message); setItems((c) => c ?? []); } }
  }, [admin, branch, q]);

  useEffect(() => {
    const t = setTimeout(() => { setItems(null); void load(true, 0); }, 300);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="branch-prices-screen">
      <ScreenHeader title="Harga Cabang" />
      <View style={{ paddingHorizontal: spacing.lg, gap: spacing.sm, paddingTop: spacing.sm }}>
        {admin ? <Chips testID="bp-branch" options={BRANCHES} value={branch} onChange={setBranch} /> : null}
        <Text style={adminStyles.muted} testID="bp-store">{storeName ? `${storeName}: ` : ""}harga di sini hanya berlaku untuk cabang ini. Harga PGS Sidoarjo & cabang lain tidak berubah.</Text>
        <View style={styles.search}>
          <Icon name="search" size={16} color={colors.muted} />
          <TextInput testID="bp-search" value={q} onChangeText={setQ} placeholder="Cari produk" placeholderTextColor={colors.muted} style={{ flex: 1, minHeight: 44, color: colors.onSurface }} />
        </View>
        {err ? <Text style={adminStyles.err} testID="bp-error">{err}</Text> : null}
      </View>
      {items === null ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.product_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          onEndReached={() => { if (!done && items.length) void load(false, items.length); }}
          onEndReachedThreshold={0.5}
          ListEmptyComponent={err ? null : <Text style={adminStyles.muted}>Produk tidak ditemukan.</Text>}
          renderItem={({ item }) => (
            <Pressable style={styles.row} testID={`bp-row-${item.product_id}`} onPress={() => setEditing(item)}>
              <Image source={item.image} style={styles.img} contentFit="cover" />
              <View style={{ flex: 1 }}>
                <Text style={styles.name} numberOfLines={2}>{item.name}</Text>
                <Text style={styles.price} testID={`bp-price-${item.product_id}`}>{formatIDR(item.branch.price)}</Text>
                <Text style={adminStyles.muted}>Sidoarjo {formatIDR(item.sidoarjo.price)}{item.own_price ? "" : " · belum punya harga cabang"}</Text>
              </View>
              <Icon name="create-outline" size={20} color={colors.brandPrimary} />
            </Pressable>
          )}
        />
      )}
      <EditDialog item={editing} storeId={admin ? branch : null} onClose={() => setEditing(null)}
        onSaved={(n) => { setItems((cur) => (cur ?? []).map((x) => (x.product_id === n.product_id ? n : x))); setEditing(null); }} />
    </View>
  );
}

function EditDialog({ item, storeId, onClose, onSaved }: { item: BranchPriceItem | null; storeId: string | null; onClose: () => void; onSaved: (n: BranchPriceItem) => void }) {
  const [price, setPrice] = useState("");
  const [orig, setOrig] = useState("");
  const [tiers, setTiers] = useState<Record<string, Tier[]>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!item) return;
    setPrice(String(item.branch.price)); setOrig(item.branch.original_price > item.branch.price ? String(item.branch.original_price) : ""); setErr("");
    setTiers(Object.fromEntries(TYPES.map((t) => [t.id, (item.branch.tier_prices[t.id] ?? []).map((r) => ({ min_qty: String(r.min_qty), price: String(r.price) }))])));
  }, [item]);

  const setRow = (t: string, i: number, k: keyof Tier, v: string) => { setErr(""); setTiers((x) => ({ ...x, [t]: x[t].map((r, n) => (n === i ? { ...r, [k]: digits(v) } : r)) })); };
  const save = async () => {
    if (!item) return;
    const p = Number(price) || 0;
    if (p <= 0) return setErr("Harga jual wajib diisi");
    const tp: Record<string, { min_qty: number; price: number }[]> = {};
    for (const t of TYPES) {
      const rows = (tiers[t.id] ?? []).filter((r) => r.min_qty || r.price);
      if (rows.some((r) => !(Number(r.min_qty) >= 1) || !(Number(r.price) > 0))) return setErr(`Lengkapi jumlah minimal & harga grosir ${t.label}`);
      const qs = rows.map((r) => Number(r.min_qty));
      if (new Set(qs).size !== qs.length) return setErr(`Jumlah minimal grosir ${t.label} dobel`);
      if (rows.length) tp[t.id] = rows.map((r) => ({ min_qty: Number(r.min_qty), price: Number(r.price) }));
    }
    setBusy(true); setErr("");
    try { onSaved(await api.setBranchPrice(item.product_id, { store_id: storeId, price: p, original_price: Math.max(p, Number(orig) || p), tier_prices: tp })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <Modal visible={!!item} transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.backdrop}>
        <View style={styles.box} testID="bp-dialog">
          <ScrollView contentContainerStyle={{ gap: spacing.sm }} keyboardShouldPersistTaps="handled">
            <Text style={styles.title} numberOfLines={2}>{item?.name}</Text>
            <Text style={adminStyles.muted}>Harga Sidoarjo {formatIDR(item?.sidoarjo.price ?? 0)} (tidak ikut berubah)</Text>
            <View style={styles.pair}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.label}>Harga jual cabang (Rp)</Text>
                <TextInput testID="bp-input-price" value={price} onChangeText={(t) => { setErr(""); setPrice(digits(t)); }} keyboardType="number-pad" style={[styles.input, styles.full]} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.label}>Harga coret (opsional)</Text>
                <TextInput testID="bp-input-orig" value={orig} onChangeText={(t) => { setErr(""); setOrig(digits(t)); }} keyboardType="number-pad" placeholder="—" placeholderTextColor={colors.muted} style={[styles.input, styles.full]} />
              </View>
            </View>
            {TYPES.map((t) => (
              <View key={t.id} style={{ gap: 6 }} testID={`bp-tiers-${t.id}`}>
                <Text style={styles.label}>Grosir {t.label}</Text>
                {(tiers[t.id] ?? []).length ? (
                  <View style={styles.pair}>
                    <Text style={[styles.colHead, { flex: 2 }]}>Min. beli</Text>
                    <Text style={[styles.colHead, { flex: 3 }]}>Harga satuan (Rp)</Text>
                    <View style={{ width: 44 }} />
                  </View>
                ) : null}
                {(tiers[t.id] ?? []).map((r, i) => (
                  <View key={i} style={styles.pair}>
                    <TextInput testID={`bp-tier-${t.id}-${i}-qty`} value={r.min_qty} onChangeText={(v) => setRow(t.id, i, "min_qty", v)} keyboardType="number-pad" placeholder="Min. qty" placeholderTextColor={colors.muted} style={[styles.input, { flex: 2 }]} />
                    <TextInput testID={`bp-tier-${t.id}-${i}-price`} value={r.price} onChangeText={(v) => setRow(t.id, i, "price", v)} keyboardType="number-pad" placeholder="Harga" placeholderTextColor={colors.muted} style={[styles.input, { flex: 3 }]} />
                    <Pressable hitSlop={8} style={styles.iconBtn} testID={`bp-tier-${t.id}-${i}-del`} onPress={() => setTiers((x) => ({ ...x, [t.id]: x[t.id].filter((_, n) => n !== i) }))}>
                      <Icon name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                  </View>
                ))}
                {(tiers[t.id] ?? []).length < 10 ? (
                  <Pressable testID={`bp-tier-${t.id}-add`} style={styles.add} onPress={() => setTiers((x) => ({ ...x, [t.id]: [...(x[t.id] ?? []), { min_qty: "", price: "" }] }))}>
                    <Text style={styles.addText}>+ Tambah tingkat</Text>
                  </Pressable>
                ) : null}
              </View>
            ))}
          </ScrollView>
          {err ? <Text style={adminStyles.err} testID="bp-dialog-error">{err}</Text> : null}
          <View style={styles.pair}>
            <Pressable testID="bp-cancel" style={[styles.btn, styles.cancel]} onPress={onClose} disabled={busy}><Text style={styles.cancelText}>Batal</Text></Pressable>
            <Pressable testID="bp-save" style={[styles.btn, { backgroundColor: colors.brandPrimary }]} onPress={save} disabled={busy}>
              {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>Simpan</Text>}
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, minHeight: 64, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  img: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  price: { fontSize: fontSize.base, fontWeight: "700", color: colors.brandPrimary },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: spacing.lg },
  box: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, maxHeight: "90%", width: "100%", maxWidth: 520, alignSelf: "center" },
  title: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  label: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, fontWeight: "500" },
  pair: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  input: { flex: 1, minWidth: 0, width: 10, minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.sm, color: colors.onSurface, backgroundColor: colors.surfaceSecondary },
  full: { flex: 0, width: "100%" },
  colHead: { fontSize: 11, color: colors.muted },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  add: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  addText: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  btn: { flex: 1, minHeight: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  cancel: { borderWidth: 1, borderColor: colors.border },
  cancelText: { color: colors.onSurface, fontWeight: "600" },
  saveText: { color: colors.onBrandPrimary, fontWeight: "600" },
});
