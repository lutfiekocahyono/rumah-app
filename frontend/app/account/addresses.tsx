import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Address, type AddressInput } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, Field, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

const EMPTY: AddressInput = { label: "Rumah", recipient: "", phone: "", address: "", city: "Sidoarjo", postal_code: "", is_default: false };

export default function Addresses() {
  const insets = useSafeAreaInsets();
  const [list, setList] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<AddressInput | null>(null);
  const [editId, setEditId] = useState<string | undefined>();
  const [del, setDel] = useState<Address | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setList(await api.addresses()); } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const set = (p: Partial<AddressInput>) => setForm((f) => (f ? { ...f, ...p } : f));

  const save = async () => {
    if (!form) return;
    if (!form.recipient.trim() || form.phone.trim().length < 6 || form.address.trim().length < 5 || form.city.trim().length < 2)
      return setErr("Lengkapi nama penerima, nomor HP, alamat, dan kota");
    setBusy(true);
    setErr("");
    try {
      setList(await api.saveAddress(form, editId));
      setForm(null);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!del) return;
    setBusy(true);
    try { setList(await api.deleteAddress(del.address_id)); setDel(null); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="addresses-screen">
      <ScreenHeader title="Alamat Pengiriman" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        {err ? <Text style={adminStyles.err} testID="address-error">{err}</Text> : null}
        {form ? (
          <Card>
            <Text style={styles.h}>{editId ? "Ubah Alamat" : "Alamat Baru"}</Text>
            <Field testID="addr-label" label="Label (Rumah, Kantor, Gudang…)" value={form.label} onChangeText={(t) => set({ label: t })} />
            <Field testID="addr-recipient" label="Nama penerima" value={form.recipient} onChangeText={(t) => set({ recipient: t })} />
            <Field testID="addr-phone" label="No. HP penerima" value={form.phone} onChangeText={(t) => set({ phone: t })} keyboardType="phone-pad" />
            <Field testID="addr-address" label="Alamat lengkap" value={form.address} onChangeText={(t) => set({ address: t })} multiline />
            <Field testID="addr-city" label="Kota / Kabupaten" value={form.city} onChangeText={(t) => set({ city: t })} />
            <Field testID="addr-postal" label="Kode pos (opsional)" value={form.postal_code} onChangeText={(t) => set({ postal_code: t })} keyboardType="number-pad" />
            <ToggleRow testID="addr-default" label="Jadikan alamat utama" value={form.is_default} onChange={(v) => set({ is_default: v })} />
            <PrimaryButton testID="addr-save" label="Simpan Alamat" onPress={save} loading={busy} />
            <PrimaryButton label="Batal" variant="outline" onPress={() => setForm(null)} />
          </Card>
        ) : (
          <PrimaryButton testID="addr-add" label="+ Tambah Alamat" onPress={() => { setEditId(undefined); setErr(""); setForm({ ...EMPTY }); }} />
        )}
        {loading ? <ActivityIndicator color={colors.brandPrimary} /> : !list.length && !form ? (
          <Text style={[adminStyles.muted, { textAlign: "center" }]}>Belum ada alamat tersimpan.</Text>
        ) : list.map((a) => (
          <View key={a.address_id} style={styles.item} testID={`address-${a.address_id}`}>
            <View style={styles.between}>
              <Text style={styles.label}>{a.label}</Text>
              {a.is_default ? <View style={styles.tag}><Text style={styles.tagText}>Utama</Text></View> : null}
            </View>
            <Text style={styles.name}>{a.recipient} · {a.phone}</Text>
            <Text style={adminStyles.muted}>{a.address}, {a.city} {a.postal_code}</Text>
            <View style={styles.actions}>
              <Pressable testID={`addr-edit-${a.address_id}`} hitSlop={8} style={styles.action} onPress={() => {
                const { address_id: _id, ...rest } = a;
                setEditId(a.address_id); setErr(""); setForm(rest);
              }}>
                <Icon name="create-outline" size={16} color={colors.brandPrimary} /><Text style={styles.actionText}>Ubah</Text>
              </Pressable>
              {!a.is_default ? (
                <Pressable testID={`addr-default-${a.address_id}`} hitSlop={8} style={styles.action} onPress={async () => {
                  const { address_id: _id, ...rest } = a;
                  try { setList(await api.saveAddress({ ...rest, is_default: true }, a.address_id)); } catch (e: any) { setErr(e.message); }
                }}>
                  <Icon name="star-outline" size={16} color={colors.brandPrimary} /><Text style={styles.actionText}>Jadikan utama</Text>
                </Pressable>
              ) : null}
              <Pressable testID={`addr-delete-${a.address_id}`} hitSlop={8} style={styles.action} onPress={() => setDel(a)}>
                <Icon name="trash-outline" size={16} color={colors.error} /><Text style={[styles.actionText, { color: colors.error }]}>Hapus</Text>
              </Pressable>
            </View>
          </View>
        ))}
      </ScrollView>
      <ConfirmDialog visible={!!del} title="Hapus alamat?" message={del ? `Alamat "${del.label}" akan dihapus.` : ""} loading={busy}
        onConfirm={remove} onCancel={() => setDel(null)} />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  h: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  item: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  between: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  label: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
  tag: { backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2 },
  tagText: { color: colors.brandPrimary, fontSize: 11, fontWeight: "600" },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  actions: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm },
  action: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 32 },
  actionText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "500" },
});
