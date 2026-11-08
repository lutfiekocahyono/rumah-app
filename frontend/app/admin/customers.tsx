import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, FlatList, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, CUSTOMER_TYPE_LABEL, type CustomerType, type User } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";

const TYPES: CustomerType[] = ["langsung", "pengecer", "reseller"];

export default function AdminCustomers() {
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      api.adminCustomers(q.trim()).then(setUsers).catch((e) => setErr(e.message)).finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const setType = async (u: User, t: CustomerType) => {
    if (u.customer_type === t) return;
    setBusy(u.user_id);
    setErr("");
    try {
      const updated = await api.adminSetCustomerType(u.user_id, t);
      setUsers((list) => list.map((x) => (x.user_id === u.user_id ? updated : x)));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-customers-screen">
      <ScreenHeader title="Kategori Pelanggan" />
      <View style={styles.searchWrap}>
        <View style={styles.search}>
          <Icon name="search" size={18} color={colors.muted} />
          <TextInput testID="customer-search-input" placeholder="Cari nama atau email" placeholderTextColor={colors.muted}
            value={q} onChangeText={setQ} autoCapitalize="none" style={styles.searchInput} />
        </View>
        {err ? <Text style={styles.err}>{err}</Text> : null}
      </View>
      {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={users}
          keyExtractor={(u) => u.user_id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}
          ListEmptyComponent={<Text style={styles.empty}>Tidak ada pelanggan</Text>}
          renderItem={({ item }) => (
            <View style={styles.card} testID={`customer-${item.email}`}>
              <View style={styles.cardTop}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{item.name}{item.role === "admin" ? " · Admin" : ""}</Text>
                  <Text style={styles.email}>{item.email}</Text>
                </View>
                {busy === item.user_id ? <ActivityIndicator color={colors.brandPrimary} /> : null}
              </View>
              <View style={styles.segment}>
                {TYPES.map((t) => {
                  const active = item.customer_type === t;
                  return (
                    <Pressable key={t} testID={`set-type-${item.email}-${t}`} style={[styles.segBtn, active && styles.segActive]}
                      onPress={() => setType(item, t)} disabled={busy === item.user_id}>
                      <Text style={[styles.segText, active && styles.segTextActive]} numberOfLines={1}>{CUSTOMER_TYPE_LABEL[t]}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  searchWrap: { padding: spacing.lg, paddingBottom: 0, gap: spacing.sm },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  searchInput: { flex: 1, color: colors.onSurface, paddingVertical: 12 },
  err: { color: colors.error, fontSize: fontSize.sm },
  empty: { textAlign: "center", color: colors.muted, marginTop: spacing.xl },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  cardTop: { flexDirection: "row", alignItems: "center" },
  name: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500" },
  email: { fontSize: fontSize.sm, color: colors.muted, marginTop: 2 },
  segment: { flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, padding: 3 },
  segBtn: { flex: 1, minHeight: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, paddingHorizontal: 4 },
  segActive: { backgroundColor: colors.brandPrimary },
  segText: { fontSize: 12, color: colors.onSurfaceTertiary },
  segTextActive: { color: colors.onBrandPrimary, fontWeight: "500" },
});
