import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, ActivityIndicator, StyleSheet, RefreshControl, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type CustomerLocations } from "@/src/api";
import { fmtDate } from "@/src/utils/date";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Chips, ToggleRow } from "@/src/components/admin-form";
import { CustomerMap } from "@/src/components/customer-map";

const RANGES = [{ id: "0", label: "Semua" }, { id: "1", label: "24 jam" }, { id: "7", label: "7 hari" }, { id: "30", label: "30 hari" }];

/** Super Admin: peta & posisi terakhir semua pelanggan yang mengizinkan lokasi. */
export default function CustomerAnalysis() {
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const [days, setDays] = useState("0");
  const [guests, setGuests] = useState(true);
  const [d, setD] = useState<CustomerLocations | null>(null);
  const [err, setErr] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setErr("");
    try { setD(await api.customerLocations(Number(days), guests)); } catch (e: any) { setErr(e.message); }
  }, [days, guests]);
  useEffect(() => { void load(); }, [load]);

  const stats = d ? [
    { k: "Titik lokasi", v: d.stats.total }, { k: "Pelanggan (akun)", v: d.stats.customers }, { k: "Tamu", v: d.stats.guests },
    { k: "Aktif 24 jam", v: d.stats.active_24h }, { k: "Aktif 7 hari", v: d.stats.active_7d }, { k: "Pernah belanja", v: d.stats.buyers },
  ] : [];

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="customer-analysis-screen">
      <ScreenHeader title="Analisa Pelanggan" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
        <Text style={adminStyles.muted}>Posisi terakhir pelanggan yang mengizinkan akses lokasi (diperbarui saat aplikasi dibuka). Ketuk titik untuk detail.</Text>
        <Chips testID="ca-range" options={RANGES} value={days} onChange={setDays} />
        <ToggleRow testID="ca-guests" label="Tampilkan tamu" sub="Pengunjung yang belum masuk akun" value={guests} onChange={setGuests} />
        {err ? <Text style={adminStyles.err} testID="ca-error">{err}</Text> : null}
        {!d ? <ActivityIndicator color={colors.brandPrimary} /> : (
          <>
            <View style={styles.stats}>
              {stats.map((s) => (
                <View key={s.k} style={styles.stat} testID={`ca-stat-${s.k}`}>
                  <Text style={styles.statV}>{s.v.toLocaleString("id-ID")}</Text>
                  <Text style={adminStyles.muted}>{s.k}</Text>
                </View>
              ))}
            </View>
            <View style={styles.legend}>
              {[["Pernah belanja", colors.success], ["Pelanggan", colors.brandPrimary], ["Tamu", colors.muted]].map(([l, c]) => (
                <View key={l} style={styles.legendItem}><View style={[styles.dot, { backgroundColor: c }]} /><Text style={adminStyles.muted}>{l}</Text></View>
              ))}
            </View>
            <CustomerMap points={d.items} height={Math.max(320, Math.round(height * 0.5))} />
            <Card>
              <Text style={styles.h}>Daftar ({d.items.length.toLocaleString("id-ID")})</Text>
              {d.items.length === 0 ? <Text style={adminStyles.muted} testID="ca-empty">Belum ada lokasi pelanggan untuk filter ini.</Text> : null}
              {d.items.slice(0, 200).map((c) => (
                <View key={c.owner} style={styles.row} testID="ca-row">
                  <View style={[styles.dot, { backgroundColor: c.guest ? colors.muted : c.orders ? colors.success : colors.brandPrimary }]} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name} numberOfLines={1}>{c.name || "Tanpa nama"}{c.email ? ` · ${c.email}` : ""}</Text>
                    <Text style={adminStyles.muted} numberOfLines={1}>
                      {c.lat.toFixed(4)}, {c.lng.toFixed(4)} · {fmtDate(c.updated_at)}{c.orders ? ` · ${c.orders} pesanan · ${formatIDR(c.spent)}` : ""}
                    </Text>
                  </View>
                </View>
              ))}
              {d.items.length > 200 ? <Text style={adminStyles.muted}>Menampilkan 200 terbaru; semua titik ada di peta.</Text> : null}
            </Card>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  stats: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  stat: { flexGrow: 1, flexBasis: "30%", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  statV: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 44, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
});
