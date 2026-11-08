import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import type { Destination } from "@/src/api";

/** Debounced search of RajaOngkir destinations (kecamatan/kota). */
export function DestinationSearch({ search, value, onPick, placeholder = "Ketik kecamatan / kota (min. 3 huruf)", testID = "dest" }: {
  search: (q: string) => Promise<Destination[]>; value?: Destination | null; onPick: (d: Destination) => void; placeholder?: string; testID?: string;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Destination[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (q.trim().length < 3) { setItems([]); return; }
    const t = setTimeout(() => {
      setBusy(true);
      setErr("");
      search(q.trim()).then(setItems).catch((e) => setErr(e.message)).finally(() => setBusy(false));
    }, 400);
    return () => clearTimeout(t);
  }, [q, search]);

  return (
    <View style={{ gap: spacing.sm }}>
      {value ? (
        <View style={styles.picked} testID={`${testID}-picked`}>
          <Icon name="location" size={16} color={colors.brandPrimary} />
          <Text style={styles.pickedText}>{value.label}</Text>
        </View>
      ) : null}
      <View style={styles.search}>
        <Icon name="search" size={16} color={colors.muted} />
        <TextInput testID={`${testID}-input`} value={q} onChangeText={setQ} placeholder={value ? "Ganti lokasi" : placeholder}
          placeholderTextColor={colors.muted} style={styles.input} />
        {busy ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
      </View>
      {err ? <Text style={styles.err}>{err}</Text> : null}
      {items.map((d) => (
        <Pressable key={d.id} testID={`${testID}-result-${d.id}`} style={styles.row} onPress={() => { onPick(d); setQ(""); setItems([]); }}>
          <Text style={styles.rowText}>{d.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md },
  input: { flex: 1, minWidth: 0, paddingVertical: 10, color: colors.onSurface, fontSize: fontSize.sm },
  picked: { flexDirection: "row", alignItems: "center", gap: 6 },
  pickedText: { flex: 1, fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  row: { paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider, minHeight: 44, justifyContent: "center" },
  rowText: { fontSize: 13, color: colors.onSurface },
  err: { color: colors.error, fontSize: 12 },
});
