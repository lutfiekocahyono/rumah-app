import React, { useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, ScrollView, StyleSheet, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, imgUrl, type Brand } from "@/src/api";
import { adminStyles } from "@/src/components/admin-form";

function Logo({ b }: { b: Brand }) {
  return b.logo ? <Image source={{ uri: imgUrl(b.logo) }} style={styles.logo} contentFit="contain" />
    : <View style={[styles.logo, styles.noLogo]}><Text style={styles.initial}>{b.name.slice(0, 1).toUpperCase()}</Text></View>;
}

/** Super Admin: merek yang tampil di "Merek Unggulan" Beranda dan urutannya. Kosongkan = otomatis 10 merek terbanyak. */
export function FeaturedBrandsAdmin({ brands }: { brands: Brand[] }) {
  const [items, setItems] = useState<Brand[]>([]);
  const [custom, setCustom] = useState(false);
  const [saved, setSaved] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const apply = (r: { custom: boolean; items: Brand[] }) => { setItems(r.items); setCustom(r.custom); setSaved(JSON.stringify(r.items.map((b) => b.brand_id))); };
  useEffect(() => { api.adminFeaturedBrands().then(apply).catch((e) => setMsg({ ok: false, text: e.message })); }, []);

  const dirty = JSON.stringify(items.map((b) => b.brand_id)) !== saved || !custom;
  const t = q.trim().toLowerCase();
  const hits = t ? brands.filter((b) => b.name.toLowerCase().includes(t) && !items.some((i) => i.brand_id === b.brand_id)).slice(0, 8) : [];
  const move = (i: number, d: number) => setItems((x) => { const n = [...x]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n; });
  const save = async (ids: string[] | null) => {
    setBusy(true); setMsg(null);
    try { apply(await api.adminSaveFeaturedBrands(ids)); setMsg({ ok: true, text: ids ? "Merek Unggulan disimpan" : "Kembali otomatis: 10 merek dengan produk terbanyak" }); }
    catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap} keyboardShouldPersistTaps="handled" testID="cm-featured">
      <Text style={adminStyles.muted}>
        {custom ? "Urutan di bawah tampil di Beranda." : "Belum diatur: Beranda otomatis menampilkan 10 merek dengan produk terbanyak (di bawah). Ubah lalu simpan untuk mengatur sendiri."}
      </Text>
      {items.map((b, i) => (
        <View key={b.brand_id} style={styles.row} testID={`cm-feat-${b.name}`}>
          <Text style={styles.num}>{i + 1}</Text>
          <Logo b={b} />
          <Text style={styles.name} numberOfLines={1}>{b.name}</Text>
          <Pressable testID={`cm-feat-up-${b.name}`} disabled={i === 0} style={[styles.btn, i === 0 && { opacity: 0.3 }]} onPress={() => move(i, -1)}>
            <Icon name="chevron-up" size={18} color={colors.onSurface} />
          </Pressable>
          <Pressable testID={`cm-feat-down-${b.name}`} disabled={i === items.length - 1} style={[styles.btn, i === items.length - 1 && { opacity: 0.3 }]} onPress={() => move(i, 1)}>
            <Icon name="chevron-down" size={18} color={colors.onSurface} />
          </Pressable>
          <Pressable testID={`cm-feat-remove-${b.name}`} style={styles.btn} onPress={() => setItems((x) => x.filter((y) => y.brand_id !== b.brand_id))}>
            <Icon name="close" size={18} color={colors.error} />
          </Pressable>
        </View>
      ))}
      {!items.length ? <Text style={adminStyles.muted}>Belum ada merek dipilih. Bila disimpan kosong, deretan Merek Unggulan tidak tampil.</Text> : null}
      <View style={styles.search}>
        <Icon name="search" size={16} color={colors.muted} />
        <TextInput testID="cm-feat-search" value={q} onChangeText={setQ} placeholder="Cari merek untuk ditambahkan…" placeholderTextColor={colors.muted} style={styles.input} />
      </View>
      {hits.map((b) => (
        <Pressable key={b.brand_id} testID={`cm-feat-add-${b.name}`} style={styles.row} disabled={items.length >= 30} onPress={() => { setItems((x) => [...x, b]); setQ(""); }}>
          <Logo b={b} />
          <Text style={styles.name} numberOfLines={1}>{b.name}</Text>
          <Text style={adminStyles.muted}>{b.count} produk</Text>
          <Icon name="add-circle-outline" size={20} color={colors.brandPrimary} />
        </Pressable>
      ))}
      {msg ? <Text testID="cm-feat-msg" style={msg.ok ? adminStyles.ok : adminStyles.err}>{msg.text}</Text> : null}
      <Pressable testID="cm-feat-save" disabled={!dirty || busy} onPress={() => save(items.map((b) => b.brand_id))} style={[styles.save, (!dirty || busy) && { opacity: 0.5 }]}>
        {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>Simpan Merek Unggulan</Text>}
      </Pressable>
      {custom ? (
        <Pressable testID="cm-feat-auto" disabled={busy} onPress={() => save(null)} style={styles.autoBtn}>
          <Text style={{ color: colors.brandPrimary, fontWeight: "500" }}>Kembali ke otomatis (merek terbanyak)</Text>
        </Pressable>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: spacing.lg, paddingTop: spacing.sm, gap: spacing.sm, paddingBottom: 120 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 56, padding: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.md },
  num: { width: 20, textAlign: "center", color: colors.muted, fontSize: fontSize.sm },
  logo: { width: 40, height: 40, borderRadius: 20 },
  noLogo: { backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  initial: { color: colors.brandPrimary, fontWeight: "700" },
  name: { flex: 1, color: colors.onSurface, fontSize: fontSize.base },
  btn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginTop: spacing.sm },
  input: { flex: 1, minHeight: 44, color: colors.onSurface, fontSize: fontSize.sm },
  save: { minHeight: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  saveText: { color: colors.onBrandPrimary, fontWeight: "600" },
  autoBtn: { minHeight: 44, alignItems: "center", justifyContent: "center" },
});
