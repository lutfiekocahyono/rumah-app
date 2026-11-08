import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type AccurateItem, type AccurateSettings } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { fmtDate } from "@/src/utils/date";

type Msg = { ok: boolean; text: string } | null;

function Note({ msg, testID }: { msg: Msg; testID: string }) {
  return msg ? <Text style={[styles.small, { color: msg.ok ? colors.success : colors.error }]} testID={`${testID}-${msg.ok ? "ok" : "error"}`}>{msg.text}</Text> : null;
}

/** Pengaturan Accurate Online — Tahap 1: kunci API, uji koneksi, pemetaan gudang, pratinjau barang (baca-saja). */
export default function AccurateSettingsScreen() {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<AccurateSettings | null>(null);
  const [token, setToken] = useState("");
  const [secret, setSecret] = useState("");
  const [dbId, setDbId] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const [stores, setStores] = useState<{ store_id: string; name: string }[]>([]);
  const [whs, setWhs] = useState<{ id: number; name: string }[] | null>(null);
  const [map, setMap] = useState<Record<string, string>>({});
  const [items, setItems] = useState<{ items: AccurateItem[]; page: number; page_count: number; total: number } | null>(null);
  const [wh, setWh] = useState("");
  const [askDelete, setAskDelete] = useState(false);
  const [dataMsg, setDataMsg] = useState<Msg>(null);

  const apply = (x: AccurateSettings) => { setS(x); setDbId(x.database_id); setMap(x.warehouse_map); };
  useEffect(() => {
    api.accurateSettings().then(apply).catch((e) => setMsg({ ok: false, text: e.message }));
    api.editorContext().then((c) => setStores(c.stores.map((x) => ({ store_id: x.store_id, name: x.name })))).catch(() => {});
  }, []);

  const run = async (key: string, fn: () => Promise<void>, set = setMsg) => {
    setBusy(key);
    set(null);
    try { await fn(); } catch (e: any) { set({ ok: false, text: e.message }); } finally { setBusy(""); }
  };
  const save = () => run("save", async () => {
    apply(await api.accurateSave({ api_token: token, signature_secret: secret, database_id: dbId }));
    setToken(""); setSecret("");
    setMsg({ ok: true, text: "Kunci tersimpan terenkripsi. Tekan Uji Koneksi." });
  });
  const test = () => run("test", async () => {
    try { const x = await api.accurateTest(); apply(x); setMsg({ ok: true, text: x.last_test_message }); }
    finally { api.accurateSettings().then(apply).catch(() => {}); }
  });
  const loadWh = () => run("wh", async () => { setWhs((await api.accurateWarehouses()).items); }, setDataMsg);
  const saveMap = () => run("map", async () => { apply(await api.accurateSaveMap(map)); setDataMsg({ ok: true, text: "Pemetaan cabang ↔ gudang tersimpan" }); }, setDataMsg);
  const loadItems = useCallback((page: number) => run("items", async () => { setItems(await api.accurateItems(page, wh)); }, setDataMsg), [wh]);
  const remove = () => { setAskDelete(false); run("del", async () => { apply(await api.accurateDelete()); setWhs(null); setItems(null); setMsg({ ok: true, text: "Kunci Accurate dihapus" }); }); };

  const connected = !!s?.last_test_ok;
  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="accurate-screen">
      <ScreenHeader title="Integrasi Accurate Online" />
      <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + spacing.xl }]} keyboardShouldPersistTaps="handled">
        <View style={styles.banner} testID="accurate-phase">
          <Icon name="shield-checkmark-outline" size={20} color={colors.brandPrimary} />
          <Text style={[styles.small, { flex: 1 }]}>
            Tahap 1 — baca-saja. Aplikasi hanya membaca barang, harga, gudang & stok dari Accurate. Tidak ada stok, harga, atau faktur yang diubah di Accurate.
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.h}>1. Kunci API</Text>
          <Text style={styles.small}>Di Accurate: Accurate Store → Aplikasi Saya → buat API Token untuk aplikasi PGS. Salin API Token dan Signature Secret ke sini. Kunci disimpan terenkripsi di server dan tidak pernah ditampilkan lagi.</Text>
          {s?.configured ? <Text style={styles.small} testID="accurate-hints">Tersimpan: token {s.token_hint} · secret {s.secret_hint}{s.updated_at ? ` · ${fmtDate(s.updated_at)}` : ""}</Text> : null}
          <TextInput testID="accurate-token" value={token} onChangeText={setToken} secureTextEntry autoCapitalize="none" autoCorrect={false}
            placeholder={s?.configured ? "API Token baru (opsional)" : "API Token"} placeholderTextColor={colors.muted} style={styles.input} />
          <TextInput testID="accurate-secret" value={secret} onChangeText={setSecret} secureTextEntry autoCapitalize="none" autoCorrect={false}
            placeholder={s?.configured ? "Signature Secret baru (opsional)" : "Signature Secret"} placeholderTextColor={colors.muted} style={styles.input} />
          <TextInput testID="accurate-db" value={dbId} onChangeText={setDbId} autoCapitalize="none" placeholder="ID Database (opsional)"
            placeholderTextColor={colors.muted} style={styles.input} />
          <View style={styles.row}>
            <Pressable testID="accurate-save" style={styles.primary} onPress={save} disabled={!!busy}>
              {busy === "save" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Simpan Kunci</Text>}
            </Pressable>
            <Pressable testID="accurate-test" style={[styles.outline, !s?.configured && { opacity: 0.5 }]} onPress={test} disabled={!!busy || !s?.configured}>
              {busy === "test" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Uji Koneksi</Text>}
            </Pressable>
          </View>
          {msg && !(s?.last_test_at && msg.text === s.last_test_message) ? <Note msg={msg} testID="accurate-msg" /> : null}
          {s?.last_test_at ? (
            <Text style={[styles.small, { color: s.last_test_ok ? colors.success : colors.error }]} testID="accurate-status">
              {s.last_test_ok ? "● Terhubung" : "● Gagal"} · {fmtDate(s.last_test_at)} · {s.last_test_message}
            </Text>
          ) : null}
          {s?.configured ? (
            <Pressable testID="accurate-delete" onPress={() => setAskDelete(true)} hitSlop={8}><Text style={[styles.small, { color: colors.error }]}>Hapus kunci Accurate</Text></Pressable>
          ) : null}
        </View>

        <View style={[styles.card, !connected && { opacity: 0.6 }]}>
          <Text style={styles.h}>2. Cabang ↔ Gudang Accurate</Text>
          <Text style={styles.small}>Stok tiap cabang PGS akan diambil dari gudang Accurate yang dipilih di sini.</Text>
          <Pressable testID="accurate-load-wh" style={styles.outline} onPress={loadWh} disabled={!connected || !!busy}>
            {busy === "wh" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Muat Daftar Gudang</Text>}
          </Pressable>
          {whs ? stores.map((st) => (
            <View key={st.store_id} style={{ gap: 6 }} testID={`accurate-map-${st.store_id}`}>
              <Text style={styles.label}>{st.name}</Text>
              <View style={styles.pills}>
                {[{ id: 0, name: "" }, ...whs].map((w) => (
                  <Pressable key={w.id} style={[styles.pill, (map[st.store_id] ?? "") === w.name && styles.pillOn]} onPress={() => setMap((m) => ({ ...m, [st.store_id]: w.name }))}>
                    <Text style={[styles.pillText, (map[st.store_id] ?? "") === w.name && { color: colors.onBrandPrimary }]}>{w.name || "Tidak dipetakan"}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          )) : null}
          {whs ? (
            <Pressable testID="accurate-save-map" style={styles.primary} onPress={saveMap} disabled={!!busy}>
              <Text style={styles.primaryText}>Simpan Pemetaan</Text>
            </Pressable>
          ) : null}
        </View>

        <View style={[styles.card, !connected && { opacity: 0.6 }]}>
          <Text style={styles.h}>3. Pratinjau Barang Accurate</Text>
          <Text style={styles.small}>Kode barang Accurate dicocokkan dengan SKU produk PGS. Belum ada data yang disalin ke aplikasi.</Text>
          {whs?.length ? (
            <View style={styles.pills}>
              {[{ id: 0, name: "" }, ...whs].map((w) => (
                <Pressable key={w.id} style={[styles.pill, wh === w.name && styles.pillOn]} onPress={() => setWh(w.name)}>
                  <Text style={[styles.pillText, wh === w.name && { color: colors.onBrandPrimary }]}>{w.name || "Semua gudang"}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          <Pressable testID="accurate-load-items" style={styles.outline} onPress={() => loadItems(1)} disabled={!connected || !!busy}>
            {busy === "items" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Tampilkan Barang</Text>}
          </Pressable>
          {items ? (
            <View style={{ gap: 6 }} testID="accurate-items">
              <Text style={styles.small}>{items.total} barang · halaman {items.page}/{items.page_count}</Text>
              {items.items.map((i) => (
                <View key={i.id} style={styles.item}>
                  <Text style={[styles.label, { flex: 1 }]} numberOfLines={2}>{i.no} · {i.name}</Text>
                  <Text style={styles.small}>{i.price != null ? formatIDR(i.price) : "–"}{i.stock != null ? ` · stok ${i.stock}` : ""}</Text>
                  <Text style={[styles.small, { color: i.pgs_product_id ? colors.success : colors.muted }]}>{i.pgs_product_id ? "✓ cocok di PGS" : "belum ada di PGS"}</Text>
                </View>
              ))}
              <View style={styles.row}>
                <Pressable style={styles.outline} disabled={items.page <= 1 || !!busy} onPress={() => loadItems(items.page - 1)}><Text style={styles.outlineText}>‹ Sebelumnya</Text></Pressable>
                <Pressable style={styles.outline} disabled={items.page >= items.page_count || !!busy} onPress={() => loadItems(items.page + 1)}><Text style={styles.outlineText}>Berikutnya ›</Text></Pressable>
              </View>
            </View>
          ) : null}
          <Note msg={dataMsg} testID="accurate-data-msg" />
        </View>

        <View style={styles.card}>
          <Text style={styles.h}>Tahap berikutnya</Text>
          <Text style={styles.small}>• Ambil produk, harga & stok per cabang dari Accurate ke PGS (dengan pratinjau perubahan sebelum disimpan).</Text>
          <Text style={styles.small}>• Kirim pesanan online sebagai faktur penjualan ke Accurate — hanya setelah Anda konfirmasi.</Text>
        </View>
      </ScrollView>
      <ConfirmDialog visible={askDelete} title="Hapus kunci Accurate?" message="Koneksi ke Accurate akan diputus. Data di Accurate tidak berubah."
        confirmLabel="Hapus" onConfirm={remove} onCancel={() => setAskDelete(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  body: { padding: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 720, alignSelf: "center" },
  banner: { flexDirection: "row", gap: spacing.sm, alignItems: "center", padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandTertiary },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  small: { fontSize: 13, color: colors.onSurfaceSecondary },
  label: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  input: { minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, color: colors.onSurface, backgroundColor: colors.surface },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  primary: { minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600" },
  outline: { minHeight: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  outlineText: { color: colors.brandPrimary, fontWeight: "600" },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  pill: { minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, justifyContent: "center" },
  pillOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillText: { fontSize: 13, color: colors.onSurface },
  item: { gap: 2, paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
});
