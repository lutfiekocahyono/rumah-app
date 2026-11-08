import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import type { Courier } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, PrimaryButton, ToggleRow, digits } from "@/src/components/admin-form";

/** Edit courier tariffs of a store. Used by store managers and by the super admin. */
export function CourierEditor({ title, load, save }: { title: string; load: () => Promise<Courier[]>; save: (c: Courier[]) => Promise<Courier[]> }) {
  const insets = useSafeAreaInsets();
  const [list, setList] = useState<Courier[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  const reload = useCallback(() => { load().then(setList).catch((e) => setMsg({ err: e.message, ok: "" })); }, [load]);
  useEffect(() => { reload(); }, [reload]);

  const set = (i: number, p: Partial<Courier>) => setList((l) => l?.map((c, j) => (j === i ? { ...c, ...p } : c)) ?? l);

  const submit = async () => {
    if (!list) return;
    const bad = list.find((c) => c.name.trim().length < 2 || !/^[a-z0-9_]{2,20}$/.test(c.code));
    if (bad) return setMsg({ err: "Nama kurir min. 2 huruf dan kode huruf kecil/angka", ok: "" });
    setBusy(true);
    try { setList(await save(list)); setMsg({ err: "", ok: "Tarif kurir disimpan" }); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setBusy(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="courier-editor">
      <ScreenHeader title={title} />
      {!list ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          {list.map((c, i) => (
            <View key={i} style={styles.card} testID={`courier-${c.code || i}`}>
              <View style={styles.row}>
                <TextInput value={c.name} onChangeText={(t) => set(i, { name: t })} style={[styles.input, { flex: 1 }]} placeholder="Nama kurir" placeholderTextColor={colors.muted} testID={`courier-name-${i}`} />
                <Pressable hitSlop={8} testID={`courier-remove-${i}`} onPress={() => setList(list.filter((_, j) => j !== i))}>
                  <Icon name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              </View>
              <View style={styles.row}>
                <Text style={styles.label}>Rp</Text>
                <TextInput value={String(c.cost)} keyboardType="number-pad" onChangeText={(t) => set(i, { cost: digits(t) })} style={[styles.input, { flex: 1 }]} testID={`courier-cost-${i}`} />
                <TextInput value={c.eta} onChangeText={(t) => set(i, { eta: t })} style={[styles.input, { flex: 1 }]} placeholder="Estimasi" placeholderTextColor={colors.muted} />
              </View>
              <ToggleRow label="Aktif" value={c.active} onChange={(v) => set(i, { active: v })} />
            </View>
          ))}
          <PrimaryButton testID="courier-add" label="+ Tambah Kurir" variant="outline"
            onPress={() => setList([...list, { code: `kurir${list.length + 1}`, name: "", cost: 0, eta: "", active: true }])} />
          {msg.err ? <Text style={adminStyles.err}>{msg.err}</Text> : null}
          {msg.ok ? <Text style={adminStyles.ok} testID="courier-ok">{msg.ok}</Text> : null}
          <PrimaryButton testID="courier-save" label="Simpan Tarif" onPress={submit} loading={busy} />
          <Text style={adminStyles.muted}>Contoh tarif: {formatIDR(25000)} untuk JNE Reguler. Ambil di toko = Rp0.</Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  label: { color: colors.muted, fontSize: fontSize.sm },
  input: { minWidth: 0, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface },
});
