import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { useCart } from "@/src/cart-context";
import { useAuth } from "@/src/auth-context";
import { api } from "@/src/api";

export default function Checkout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { cart, refresh } = useCart();
  const { user } = useAuth();

  const [fullName, setFullName] = useState(user?.name ?? "");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("Sidoarjo");
  const [method, setMethod] = useState("ewallet");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const total = cart.subtotal + 25000;

  const submit = async () => {
    setErr("");
    if (!fullName.trim() || !phone.trim() || !address.trim() || !city.trim()) {
      setErr("Lengkapi semua data pengiriman");
      return;
    }
    if (cart.item_count === 0) {
      setErr("Keranjang kosong");
      return;
    }
    setLoading(true);
    try {
      const order = await api.checkout({ full_name: fullName, phone, address, city, payment_method: method });
      await refresh();
      router.replace({ pathname: "/order-success" as any, params: { order_id: order.order_id, total: String(order.total) } });
    } catch (e: any) {
      setErr(e?.message || "Gagal checkout");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" hitSlop={8} onPress={() => router.back()}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Checkout</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled">
        <Text style={styles.section}>Alamat Pengiriman</Text>
        <View style={styles.card}>
          <Input testID="co-name" label="Nama Lengkap" value={fullName} onChangeText={setFullName} />
          <Input testID="co-phone" label="No. HP / WhatsApp" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
          <Input testID="co-address" label="Alamat lengkap" value={address} onChangeText={setAddress} multiline />
          <Input testID="co-city" label="Kota" value={city} onChangeText={setCity} />
        </View>

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Metode Pembayaran</Text>
        <View style={styles.card}>
          {[
            { id: "ewallet", label: "E-Wallet (OVO, Gopay, Dana)", icon: "wallet-outline" },
            { id: "transfer", label: "Transfer Bank", icon: "business-outline" },
            { id: "cod", label: "COD (Bayar di Tempat)", icon: "cash-outline" },
          ].map((m) => (
            <Pressable
              key={m.id}
              testID={`pay-${m.id}`}
              style={styles.payRow}
              onPress={() => setMethod(m.id)}
            >
              <Icon name={m.icon as any} size={20} color={colors.onSurface} />
              <Text style={styles.payLabel}>{m.label}</Text>
              <View style={[styles.radio, method === m.id && styles.radioActive]}>
                {method === m.id ? <View style={styles.radioDot} /> : null}
              </View>
            </Pressable>
          ))}
        </View>

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Ringkasan</Text>
        <View style={styles.card}>
          <Row label={`Subtotal (${cart.item_count} item)`} value={formatIDR(cart.subtotal)} />
          <Row label="Ongkos kirim" value={formatIDR(25000)} />
          <View style={styles.sep} />
          <Row label="Total Pembayaran" value={formatIDR(total)} big />
        </View>

        {err ? <Text style={styles.err} testID="checkout-error">{err}</Text> : null}
      </ScrollView>

      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.md, insets.bottom + spacing.sm) }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.smallLabel}>Total</Text>
          <Text style={styles.totalValue}>{formatIDR(total)}</Text>
        </View>
        <Pressable testID="pay-now-btn" style={styles.payBtn} onPress={submit} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.payBtnText}>Bayar Sekarang</Text>}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function Input(props: { label: string; value: string; onChangeText: (v: string) => void; keyboardType?: any; multiline?: boolean; testID?: string }) {
  return (
    <View style={{ marginBottom: spacing.sm }}>
      <Text style={styles.label}>{props.label}</Text>
      <TextInput
        testID={props.testID}
        value={props.value}
        onChangeText={props.onChangeText}
        placeholder={props.label}
        placeholderTextColor={colors.muted}
        keyboardType={props.keyboardType}
        multiline={props.multiline}
        style={[styles.input, props.multiline && { minHeight: 60, textAlignVertical: "top" }]}
      />
    </View>
  );
}

function Row({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.rowLabel, big && { color: colors.onSurface, fontWeight: "500", fontSize: fontSize.base }]}>{label}</Text>
      <Text style={[styles.rowValue, big && { color: colors.brandPrimary, fontSize: fontSize.lg, fontWeight: "500" }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  title: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },

  section: { fontSize: fontSize.sm, color: colors.muted, marginBottom: spacing.sm },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },

  label: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, marginBottom: 4 },
  input: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface, fontSize: fontSize.base },

  payRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  payLabel: { flex: 1, color: colors.onSurface, fontSize: fontSize.sm },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },

  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  rowLabel: { color: colors.muted, fontSize: fontSize.sm },
  rowValue: { color: colors.onSurface, fontSize: fontSize.sm },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.sm },

  err: { color: colors.error, fontSize: fontSize.sm, marginTop: spacing.md },

  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md },
  smallLabel: { fontSize: 11, color: colors.muted },
  totalValue: { fontSize: fontSize.lg, color: colors.brandPrimary, fontWeight: "500" },
  payBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: 14, borderRadius: radius.pill, minWidth: 180, alignItems: "center" },
  payBtnText: { color: colors.onBrandPrimary, fontWeight: "500" },
});
