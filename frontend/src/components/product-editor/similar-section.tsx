import React, { useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, StyleSheet, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, imgUrl, type SimilarBrief } from "@/src/api";
import { Section, ui } from "./ui";

/** Produk Serupa (manual) untuk produk ini: cari, tambah, urutkan, hapus. Kosong = otomatis di halaman produk.
 * Super Admin: berlaku untuk semua cabang; admin cabang: menimpa khusus cabangnya. Disimpan langsung, terpisah dari form. */
export function SimilarSection({ productId, admin }: { productId: string | null; admin: boolean }) {
  const [items, setItems] = useState<SimilarBrief[]>([]);
  const [inherited, setInherited] = useState<SimilarBrief[] | null>(null);
  const [saved, setSaved] = useState("[]");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SimilarBrief[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!productId) return;
    api.editorSimilar(productId).then((r) => { setItems(r.items); setSaved(JSON.stringify(r.items.map((i) => i.product_id))); setInherited(r.inherited); }).catch(() => {});
  }, [productId]);
  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setHits([]); return; }
    const h = setTimeout(() => api.products({ q: t, limit: 8 }).then((ps) => setHits(ps.filter((p) => p.product_id !== productId)
      .map((p) => ({ product_id: p.product_id, name: p.name, image: p.images?.[0] ?? p.image ?? "", price: p.my_price ?? p.price })))).catch(() => {}), 350);
    return () => clearTimeout(h);
  }, [q, productId]);

  const dirty = JSON.stringify(items.map((i) => i.product_id)) !== saved;
  const move = (i: number, d: number) => setItems((x) => { const n = [...x]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n; });
  const save = async () => {
    if (!productId) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.editorSaveSimilar(productId, items.map((i) => i.product_id));
      setItems(r.items); setSaved(JSON.stringify(r.items.map((i) => i.product_id)));
      setMsg({ ok: true, text: r.items.length ? "Produk serupa disimpan" : admin ? "Kosong: halaman produk memakai produk serupa otomatis" : "Kosong: memakai pilihan Super Admin / otomatis" });
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  };

  return (
    <Section title="Produk Serupa" icon="git-compare-outline" testID="pe-similar"
      subtitle={admin ? "Pilihan Anda berlaku untuk semua cabang. Kosong = otomatis (kategori, merek & harga mirip)." : "Khusus cabang Anda. Kosong = pilihan Super Admin, atau otomatis."}>
      {!productId ? <Text style={ui.hint}>Simpan produk dulu, lalu atur produk serupanya di sini.</Text> : (
        <View style={{ gap: spacing.sm }}>
          {!items.length && inherited?.length ? (
            <Text style={ui.hint} testID="pe-similar-inherited">Saat ini memakai {inherited.length} produk pilihan Super Admin: {inherited.slice(0, 3).map((i) => i.name).join(", ")}{inherited.length > 3 ? "…" : ""}</Text>
          ) : !items.length ? <Text style={ui.hint}>Belum ada pilihan manual, halaman produk memakai produk serupa otomatis.</Text> : null}
          {items.map((it, i) => (
            <View key={it.product_id} style={styles.row} testID={`pe-similar-item-${it.product_id}`}>
              <Text style={styles.num}>{i + 1}</Text>
              <Image source={{ uri: imgUrl(it.image) }} style={styles.thumb} contentFit="cover" />
              <View style={{ flex: 1 }}>
                <Text style={styles.name} numberOfLines={2}>{it.name}</Text>
                <Text style={ui.hint}>{formatIDR(it.price)}</Text>
              </View>
              <Pressable testID={`pe-similar-up-${it.product_id}`} disabled={i === 0} hitSlop={4} style={[styles.btn, i === 0 && { opacity: 0.3 }]} onPress={() => move(i, -1)}>
                <Icon name="chevron-up" size={18} color={colors.onSurface} />
              </Pressable>
              <Pressable testID={`pe-similar-down-${it.product_id}`} disabled={i === items.length - 1} hitSlop={4} style={[styles.btn, i === items.length - 1 && { opacity: 0.3 }]} onPress={() => move(i, 1)}>
                <Icon name="chevron-down" size={18} color={colors.onSurface} />
              </Pressable>
              <Pressable testID={`pe-similar-remove-${it.product_id}`} hitSlop={4} style={styles.btn} onPress={() => setItems((x) => x.filter((y) => y.product_id !== it.product_id))}>
                <Icon name="close" size={18} color={colors.error} />
              </Pressable>
            </View>
          ))}
          <View style={ui.inputWrap}>
            <Icon name="search" size={16} color={colors.muted} style={{ marginLeft: spacing.md }} />
            <TextInput testID="pe-similar-search" value={q} onChangeText={setQ} placeholder="Cari produk untuk ditambahkan…" placeholderTextColor={colors.muted} style={ui.input} />
          </View>
          {hits.map((h) => {
            const added = items.some((i) => i.product_id === h.product_id);
            return (
              <Pressable key={h.product_id} testID={`pe-similar-add-${h.product_id}`} disabled={added || items.length >= 30} style={[styles.row, added && { opacity: 0.5 }]}
                onPress={() => { setItems((x) => [...x, h]); setQ(""); }}>
                <Image source={{ uri: imgUrl(h.image) }} style={styles.thumb} contentFit="cover" />
                <Text style={[styles.name, { flex: 1 }]} numberOfLines={2}>{h.name}</Text>
                <Icon name={added ? "checkmark" : "add-circle-outline"} size={20} color={colors.brandPrimary} />
              </Pressable>
            );
          })}
          {msg ? <Text style={[ui.hint, { color: msg.ok ? colors.success : colors.error }]} testID="pe-similar-msg">{msg.text}</Text> : null}
          <Pressable testID="pe-similar-save" disabled={!dirty || busy} onPress={save} style={[styles.save, (!dirty || busy) && { opacity: 0.5 }]}>
            {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>Simpan Produk Serupa</Text>}
          </Pressable>
        </View>
      )}
    </Section>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 56, padding: spacing.sm, borderRadius: radius.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  num: { width: 18, textAlign: "center", color: colors.muted, fontSize: fontSize.sm },
  thumb: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  name: { color: colors.onSurface, fontSize: fontSize.sm },
  btn: { width: 36, height: 44, alignItems: "center", justifyContent: "center" },
  save: { minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  saveText: { color: colors.onBrandPrimary, fontWeight: "600" },
});
