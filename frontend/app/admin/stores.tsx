import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Store } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Chips, PrimaryButton } from "@/src/components/admin-form";
import { fmtDate } from "@/src/utils/date";

const LABEL = { pending: "Menunggu", active: "Aktif", rejected: "Ditolak", suspended: "Nonaktif" } as const;
type Action = { store: Store; status: "active" | "rejected" | "suspended" };

export default function AdminStores() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [filter, setFilter] = useState<string>("pending");
  const [list, setList] = useState<Store[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setList(null);
    try { setList(await api.adminStores(filter === "all" ? undefined : filter)); } catch (e: any) { setErr(e.message); setList([]); }
  }, [filter]);
  useEffect(() => { void load(); }, [load]);

  const run = async () => {
    if (!action) return;
    setBusy(true);
    try {
      await api.adminSetStoreStatus(action.store.store_id, action.status, notes[action.store.store_id] ?? "");
      setAction(null);
      await load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-stores-screen">
      <ScreenHeader title="Verifikasi Toko" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        <Chips testID="stores-filter" value={filter} onChange={setFilter}
          options={[{ id: "pending", label: "Menunggu" }, { id: "active", label: "Aktif" }, { id: "rejected", label: "Ditolak" }, { id: "suspended", label: "Nonaktif" }, { id: "all", label: "Semua" }]} />
        {err ? <Text style={adminStyles.err}>{err}</Text> : null}
        {list === null ? <ActivityIndicator color={colors.brandPrimary} /> : !list.length ? <Text style={adminStyles.muted}>Tidak ada toko.</Text> : list.map((s) => (
          <View key={s.store_id} style={styles.card} testID={`admin-store-${s.store_id}`}>
            <View style={styles.between}>
              <Text style={styles.name}>{s.name}</Text>
              <Text style={styles.status}>{LABEL[s.status]}</Text>
            </View>
            <Text style={adminStyles.muted}>{s.owner_name} · {s.owner_email}</Text>
            <Text style={adminStyles.muted}>{s.city} · {s.phone} · {fmtDate(s.created_at)}</Text>
            {s.description ? <Text style={styles.desc}>{s.description}</Text> : null}
            {s.store_id !== "pgs-official" && !s.official ? (
              <>
                <TextInput testID={`store-note-${s.store_id}`} placeholder="Catatan untuk penjual (opsional)" placeholderTextColor={colors.muted}
                  value={notes[s.store_id] ?? ""} onChangeText={(t) => setNotes((n) => ({ ...n, [s.store_id]: t }))} style={styles.input} />
                <View style={styles.actions}>
                  {s.status !== "active" ? <View style={{ flex: 1 }}><PrimaryButton testID={`store-approve-${s.store_id}`} label="Setujui" onPress={() => setAction({ store: s, status: "active" })} /></View> : null}
                  {s.status === "pending" ? <View style={{ flex: 1 }}><PrimaryButton testID={`store-reject-${s.store_id}`} label="Tolak" variant="danger" onPress={() => setAction({ store: s, status: "rejected" })} /></View> : null}
                  {s.status === "active" ? <View style={{ flex: 1 }}><PrimaryButton testID={`store-suspend-${s.store_id}`} label="Nonaktifkan" variant="danger" onPress={() => setAction({ store: s, status: "suspended" })} /></View> : null}
                </View>
              </>
            ) : (
              <View style={{ gap: 6 }}>
                <Text style={adminStyles.muted}>Toko resmi PGS</Text>
                <PrimaryButton testID={`store-couriers-${s.store_id}`} label="Atur Tarif Kurir" variant="outline"
                  onPress={() => router.push({ pathname: "/admin/store-couriers/[id]", params: { id: s.store_id, name: s.name } } as any)} />
              </View>
            )}
          </View>
        ))}
      </ScrollView>
      <ConfirmDialog visible={!!action} loading={busy} danger={action?.status !== "active"}
        title={action?.status === "active" ? "Setujui toko?" : action?.status === "rejected" ? "Tolak pengajuan toko?" : "Nonaktifkan toko?"}
        message={action ? `Toko "${action.store.name}" — pemilik akan menerima notifikasi.` : ""}
        confirmLabel={action?.status === "active" ? "Setujui" : action?.status === "rejected" ? "Tolak" : "Nonaktifkan"}
        onConfirm={run} onCancel={() => setAction(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 6, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  name: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, flex: 1 },
  status: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  desc: { fontSize: 13, color: colors.onSurfaceSecondary },
  input: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface },
  actions: { flexDirection: "row", gap: spacing.sm },
});
