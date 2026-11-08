import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Voucher, type VoucherInput } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { DateTimeField } from "@/src/components/datetime-field";
import { voucherValue } from "@/src/components/home-sections";
import { adminStyles, Card, Chips, digits, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

const EMPTY: VoucherInput = {
  code: "", title: "", description: "", mode: "percent", value: 5, max_discount: 0, min_purchase: 0,
  quota: 0, ends_at: null, active: true, show_on_home: true,
};

export default function AdminVouchers() {
  const insets = useSafeAreaInsets();
  const [list, setList] = useState<Voucher[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<VoucherInput | null>(null);
  const [isNew, setIsNew] = useState(true);
  const [valueText, setValueText] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState({ err: "", ok: "" });

  const load = useCallback(async () => {
    try { setList(await api.adminVouchers()); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const set = (patch: Partial<VoucherInput>) => setForm((f) => (f ? { ...f, ...patch } : f));

  const save = async () => {
    if (!form) return;
    if (!/^[A-Za-z0-9]{3,20}$/.test(form.code)) return setMsg({ err: "Kode 3–20 huruf/angka tanpa spasi", ok: "" });
    if (!form.title.trim()) return setMsg({ err: "Judul wajib diisi", ok: "" });
    if (!form.value || (form.mode === "percent" && form.value > 100)) return setMsg({ err: "Nilai potongan tidak valid", ok: "" });
    setBusy("save");
    try {
      await api.adminSaveVoucher({ ...form, code: form.code.toUpperCase() }, isNew);
      setForm(null);
      setMsg({ err: "", ok: "Voucher disimpan" });
      await load();
    } catch (e: any) {
      setMsg({ err: e.message, ok: "" });
    } finally {
      setBusy("");
    }
  };

  const remove = async (code: string) => {
    setBusy("del");
    try { await api.adminDeleteVoucher(code); setForm(null); await load(); } finally { setBusy(""); }
  };

  const edit = (v?: Voucher) => {
    setMsg({ err: "", ok: "" });
    setIsNew(!v);
    setValueText(String(v?.value ?? EMPTY.value));
    if (!v) return setForm({ ...EMPTY });
    const { used: _u, claimed: _c, ...rest } = v;
    setForm(rest);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="admin-vouchers-screen">
      <ScreenHeader title="Voucher Diskon" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        {msg.err ? <Text style={adminStyles.err} testID="voucher-error">{msg.err}</Text> : null}
        {msg.ok ? <Text style={adminStyles.ok}>{msg.ok}</Text> : null}
        {form ? (
          <Card>
            <Text style={styles.formTitle}>{isNew ? "Voucher Baru" : `Ubah ${form.code}`}</Text>
            {isNew ? <Field testID="voucher-code" label="Kode voucher" autoCapitalize="characters" value={form.code} onChangeText={(t) => set({ code: t.toUpperCase().replace(/\s/g, "") })} placeholder="Contoh: HEMAT10" /> : null}
            <Field testID="voucher-title" label="Judul" value={form.title} onChangeText={(t) => set({ title: t })} placeholder="Contoh: Diskon 10% Akhir Pekan" />
            <Field testID="voucher-desc" label="Keterangan (opsional)" value={form.description} onChangeText={(t) => set({ description: t })} />
            <Text style={adminStyles.section}>Jenis potongan</Text>
            <Chips testID="voucher-mode" options={[{ id: "percent", label: "Persen (%)" }, { id: "rupiah", label: "Rupiah (Rp)" }]} value={form.mode} onChange={(v) => set({ mode: v })} />
            <Field testID="voucher-value" label={form.mode === "percent" ? "Potongan (%)" : "Potongan (Rp)"} keyboardType="decimal-pad" value={valueText} onChangeText={(t) => { const c = t.replace(",", ".").replace(/[^0-9.]/g, ""); setValueText(c); set({ value: Number(c) || 0 }); }} />
            {form.mode === "percent" ? (
              <Field testID="voucher-max" label="Maksimal potongan (Rp)" hint="0 = tanpa batas" keyboardType="number-pad" value={String(form.max_discount)} onChangeText={(t) => set({ max_discount: digits(t) })} />
            ) : null}
            <Field testID="voucher-min" label="Minimal belanja (Rp)" hint="0 = tanpa minimal" keyboardType="number-pad" value={String(form.min_purchase)} onChangeText={(t) => set({ min_purchase: digits(t) })} />
            <Field testID="voucher-quota" label="Kuota pemakaian" hint="0 = tanpa batas" keyboardType="number-pad" value={String(form.quota)} onChangeText={(t) => set({ quota: digits(t) })} />
            <Text style={adminStyles.section}>Berlaku sampai</Text>
            <DateTimeField testID="voucher-ends" allowEmpty value={form.ends_at} onChange={(v) => set({ ends_at: v })} />
            <ToggleRow testID="voucher-active" label="Voucher aktif" sub="Bisa dipakai saat checkout" value={form.active} onChange={(v) => set({ active: v })} />
            <ToggleRow testID="voucher-home" label="Tampilkan di beranda" sub="Pembeli bisa klaim dari halaman utama" value={form.show_on_home} onChange={(v) => set({ show_on_home: v })} />
            <PrimaryButton testID="voucher-save" label="Simpan Voucher" onPress={save} loading={busy === "save"} />
            <PrimaryButton label="Batal" variant="outline" onPress={() => setForm(null)} />
            {!isNew ? <PrimaryButton testID="voucher-delete" label="Hapus Voucher" variant="danger" loading={busy === "del"} onPress={() => remove(form.code)} /> : null}
          </Card>
        ) : (
          <PrimaryButton testID="voucher-add" label="+ Buat Voucher" onPress={() => edit()} />
        )}

        {loading ? <ActivityIndicator color={colors.brandPrimary} /> : list.map((v) => (
          <Pressable key={v.code} testID={`admin-voucher-${v.code}`} style={styles.row} onPress={() => edit(v)}>
            <View style={styles.badge}><Text style={styles.badgeText}>{voucherValue(v)}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.name} numberOfLines={1}>{v.code} · {v.title}</Text>
              <Text style={adminStyles.muted} numberOfLines={1}>
                {v.active ? "Aktif" : "Nonaktif"} · dipakai {v.used}{v.quota ? `/${v.quota}` : ""}{v.min_purchase ? ` · min ${formatIDR(v.min_purchase)}` : ""}
              </Text>
            </View>
            <Icon name="create-outline" size={20} color={colors.muted} />
          </Pressable>
        ))}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  formTitle: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, minHeight: 64 },
  badge: { width: 64, height: 44, borderRadius: radius.sm, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  badgeText: { color: colors.brandPrimary, fontWeight: "700", fontSize: fontSize.sm },
  name: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
});
