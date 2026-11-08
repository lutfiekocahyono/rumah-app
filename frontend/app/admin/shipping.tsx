import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator, Linking, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type KeyStatus, type ShippingSettings, type Store } from "@/src/api";
import { fmtDate } from "@/src/utils/date";
import { ScreenHeader } from "@/src/components/screen-header";
import { DestinationSearch } from "@/src/components/destination-search";
import { adminStyles, Card, digits, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

export default function AdminShippingSettings() {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<ShippingSettings | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [key, setKey] = useState("");
  const [weightText, setWeightText] = useState("");
  useEffect(() => { if (s) setWeightText(String(s.default_weight_grams)); }, [s?.default_weight_grams]); // eslint-disable-line react-hooks/exhaustive-deps
  const [busy, setBusy] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  useEffect(() => {
    api.shippingSettings().then(setS).catch((e) => setMsg({ err: e.message, ok: "" }));
    api.officialStores().then(setStores).catch(() => {});
  }, []);

  const save = async (apiKey: string | null) => {
    if (!s) return;
    setBusy(true);
    setMsg({ err: "", ok: "" });
    try {
      const out = await api.saveShippingSettings({ enabled: s.enabled, default_weight_grams: s.default_weight_grams, origins: s.origins, api_key: apiKey });
      setS(out);
      setKey("");
      setMsg({ err: "", ok: apiKey ? "API key disimpan dan sudah dicek" : "Pengaturan ongkir disimpan" });
    } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setBusy(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-shipping-screen">
      <ScreenHeader title="Pengaturan Ongkir Otomatis" />
      {!s ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          <Text style={adminStyles.muted}>
            Ongkir JNE, J&T, dan SiCepat dihitung otomatis lewat RajaOngkir (Komerce) dari lokasi tiap toko. Selama API key belum diisi
            atau lokasi toko belum dipilih, dipakai tarif manual. Pilihan &quot;Ambil di toko&quot; dan kurir toko tetap manual.
          </Text>
          <Card>
            <Text style={adminStyles.section}>API key RajaOngkir — Shipping Cost</Text>
            <Text style={s.configured ? adminStyles.muted : adminStyles.err} testID="ship-key-status">
              {s.configured ? `Tersimpan (${s.key_hint})` : "Belum diisi — memakai tarif manual"}
            </Text>
            {s.configured ? <KeyStatusBadge st={s.key_status} /> : null}
            {s.configured ? (
              <PrimaryButton testID="ship-key-verify" label="Cek Kunci Sekarang" variant="outline" loading={verifying} onPress={async () => {
                setVerifying(true);
                setMsg({ err: "", ok: "" });
                try { setS(await api.verifyShippingKey()); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setVerifying(false); }
              }} />
            ) : null}
            <Field testID="ship-key" label={s.configured ? "Ganti API key" : "API key"} value={key} onChangeText={setKey} secureTextEntry autoCapitalize="none" placeholder="Tempel API key di sini" />
            <PrimaryButton testID="ship-key-save" label="Simpan API Key" loading={busy} onPress={() => (key.trim().length < 10 ? setMsg({ err: "API key terlalu pendek", ok: "" }) : save(key.trim()))} />
            {s.configured ? <PrimaryButton testID="ship-key-remove" label="Hapus API Key" variant="danger" onPress={() => save("")} /> : null}
            <Pressable style={{ minHeight: 44, justifyContent: "center" }} onPress={() => Linking.openURL("https://collaborator.komerce.id")}>
              <Text style={{ color: colors.brandPrimary, fontSize: 12 }}>Dapatkan key: collaborator.komerce.id → Developer → Settings → Api Key</Text>
            </Pressable>
          </Card>
          <Card>
            <ToggleRow testID="ship-enabled" label="Aktifkan ongkir otomatis" value={s.enabled} onChange={(v) => setS({ ...s, enabled: v })} />
            <Field testID="ship-weight" label="Berat rata-rata per barang (gram)" keyboardType="number-pad" value={weightText}
              onChangeText={(t) => { const c = t.replace(/\D/g, ""); setWeightText(c); if (c) setS({ ...s, default_weight_grams: Math.max(1, digits(c)) }); }} hint="Produk belum punya data berat; ongkir = jumlah barang × berat ini" />
          </Card>
          <Text style={adminStyles.section}>Lokasi asal pengiriman tiap toko</Text>
          {!s.configured ? <Text style={adminStyles.muted}>Simpan API key dulu untuk mencari lokasi.</Text> : stores.map((st) => (
            <Card key={st.store_id}>
              <Text style={{ fontWeight: "600", color: colors.onSurface }}>{st.name}</Text>
              <DestinationSearch testID={`origin-${st.store_id}`} search={api.adminDestinations} value={s.origins[st.store_id]}
                placeholder={`Cari kecamatan ${st.city}`} onPick={(d) => setS({ ...s, origins: { ...s.origins, [st.store_id]: d } })} />
            </Card>
          ))}
          {msg.err ? <Text style={adminStyles.err} testID="ship-error">{msg.err}</Text> : null}
          {msg.ok ? <Text style={adminStyles.ok} testID="ship-ok">{msg.ok}</Text> : null}
          <PrimaryButton testID="ship-save" label="Simpan Pengaturan" loading={busy} onPress={() => save(null)} />
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}

const STATE_UI: Record<KeyStatus["state"], { icon: string; color: string; title: string }> = {
  valid: { icon: "checkmark-circle", color: colors.success, title: "Kunci valid" },
  invalid: { icon: "close-circle", color: colors.error, title: "Kunci tidak valid — ongkir memakai tarif manual" },
  limited: { icon: "alert-circle", color: colors.warning, title: "Kuota habis — sementara memakai tarif manual" },
  unknown: { icon: "help-circle", color: colors.muted, title: "Belum bisa dipastikan" },
};

function KeyStatusBadge({ st }: { st: KeyStatus | null | undefined }) {
  if (!st) return <Text style={adminStyles.muted} testID="ship-key-check">Belum pernah dicek. Ketuk &quot;Cek Kunci Sekarang&quot;.</Text>;
  const ui = STATE_UI[st.state];
  return (
    <View style={[styles.badge, { borderColor: ui.color }]} testID="ship-key-check">
      <Icon name={ui.icon as any} size={20} color={ui.color} />
      <View style={{ flex: 1 }}>
        <Text style={styles.badgeTitle} testID={`ship-key-state-${st.state}`}>{ui.title}</Text>
        <Text style={adminStyles.muted}>{st.message}</Text>
        <Text style={styles.time}>Dicek {fmtDate(st.checked_at)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", borderWidth: 1, borderRadius: radius.sm, padding: spacing.sm, backgroundColor: colors.surface },
  badgeTitle: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  time: { fontSize: 11, color: colors.muted, marginTop: 2 },
});