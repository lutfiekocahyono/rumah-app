import React, { useEffect, useState } from "react";
import { Text, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { colors, spacing } from "@/src/theme";
import { api, type HomeSettings } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { FreeShippingBanner } from "@/src/components/home-sections";
import { adminStyles, Card, digits, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

export default function AdminHomeSettings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [s, setS] = useState<HomeSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ err: "", ok: "" });

  useEffect(() => { api.homeSettings().then(setS).catch((e) => setMsg({ err: e.message, ok: "" })); }, []);

  const setFs = (patch: Partial<HomeSettings["free_shipping"]>) => setS((x) => (x ? { ...x, free_shipping: { ...x.free_shipping, ...patch } } : x));

  const save = async () => {
    if (!s) return;
    setSaving(true);
    try {
      setS(await api.adminSaveHomeSettings({ free_shipping: s.free_shipping, recommend_mode: s.recommend_mode }));
      setMsg({ err: "", ok: "Pengaturan disimpan" });
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-home-settings-screen">
      <ScreenHeader title="Gratis Ongkir" />
      {!s ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          <Text style={adminStyles.section}>Banner Gratis Ongkir (informasi saja, ongkir tetap dihitung)</Text>
          <Card>
            <ToggleRow testID="fs-enabled" label="Tampilkan di beranda" value={s.free_shipping.enabled} onChange={(v) => setFs({ enabled: v })} />
            <Field testID="fs-title" label="Judul" value={s.free_shipping.title} onChangeText={(t) => setFs({ title: t })} />
            <Field testID="fs-subtitle" label="Keterangan" value={s.free_shipping.subtitle} onChangeText={(t) => setFs({ subtitle: t })} placeholder="Contoh: Area {kota} & sekitarnya, min. belanja Rp500.000" />
            <Text style={{ color: colors.muted, fontSize: 12 }}>Tulis {"{kota}"} agar otomatis diganti kota cabang yang dipilih pembeli.</Text>
            <Field testID="fs-min" label="Minimal belanja (Rp) — catatan" keyboardType="number-pad" value={String(s.free_shipping.min_purchase)} onChangeText={(t) => setFs({ min_purchase: digits(t) })} />
          </Card>
          <Text style={adminStyles.muted}>Pratinjau:</Text>
          <FreeShippingBanner s={{ ...s.free_shipping, enabled: true }} />

          <Text style={[adminStyles.section, { marginTop: spacing.lg }]}>Produk Populer, Terbaru & Rekomendasi</Text>
          <Card>
            <Text style={adminStyles.muted}>Aturan bagian produk di beranda sekarang diatur per cabang.</Text>
            <PrimaryButton testID="home-settings-sections" label="Buka Produk di Beranda" variant="outline" onPress={() => router.push("/admin/home-sections" as any)} />
          </Card>
          {msg.err ? <Text style={adminStyles.err}>{msg.err}</Text> : null}
          {msg.ok ? <Text style={adminStyles.ok} testID="home-settings-ok">{msg.ok}</Text> : null}
          <PrimaryButton testID="home-settings-save" label="Simpan Pengaturan" onPress={save} loading={saving} />
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}
