import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, CUSTOMER_TYPE_LABEL, ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { statusColor } from "../orders";

const ACTIONS: { id: Order["status"]; label: string; icon: string }[] = [
  { id: "processing", label: "Proses", icon: "construct-outline" },
  { id: "shipped", label: "Kirim", icon: "car-outline" },
  { id: "completed", label: "Selesai", icon: "checkmark-done-outline" },
  { id: "cancelled", label: "Batalkan", icon: "close-circle-outline" },
];
const METHOD_LABEL = { midtrans: "Midtrans", xendit: "Xendit", cod: "COD" };

function waNumber(phone: string) {
  const d = phone.replace(/\D/g, "");
  return d.startsWith("0") ? "62" + d.slice(1) : d;
}

export default function AdminOrderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [order, setOrder] = useState<Order | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (id) api.adminOrder(id).then(setOrder).catch((e) => setErr(e.message));
  }, [id]);

  const setStatus = async (s: Order["status"]) => {
    if (!order) return;
    setBusy(s);
    setErr("");
    try {
      setOrder(await api.adminSetOrderStatus(order.order_id, s));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="admin-order-detail">
      <ScreenHeader title="Detail Pesanan" />
      {!order ? (
        err ? <Text style={[styles.err, { margin: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}>
          <View style={styles.card}>
            <View style={styles.between}>
              <Text style={styles.orderId}>{order.order_id}</Text>
              <Text style={[styles.status, { color: statusColor(order.status) }]} testID="admin-order-status">{ORDER_STATUS_LABEL[order.status]}</Text>
            </View>
            <Text style={styles.muted}>{new Date(order.created_at).toLocaleString("id-ID", { dateStyle: "full", timeStyle: "short" })}</Text>
            <Text style={styles.muted}>Bayar: {METHOD_LABEL[order.payment_method]} · {CUSTOMER_TYPE_LABEL[order.customer_type]}</Text>
          </View>

          <Text style={styles.section}>Ubah Status</Text>
          <View style={styles.actions}>
            {ACTIONS.map((a) => {
              const active = order.status === a.id;
              return (
                <Pressable key={a.id} testID={`set-status-${a.id}`} style={[styles.actionBtn, active && styles.actionActive]} disabled={!!busy || active} onPress={() => setStatus(a.id)}>
                  {busy === a.id ? <ActivityIndicator color={colors.brandPrimary} /> : <Icon name={a.icon as any} size={18} color={active ? colors.onBrandPrimary : a.id === "cancelled" ? colors.error : colors.onSurface} />}
                  <Text style={[styles.actionText, active && { color: colors.onBrandPrimary }, a.id === "cancelled" && !active && { color: colors.error }]}>{a.label}</Text>
                </Pressable>
              );
            })}
          </View>
          {err ? <Text style={styles.err}>{err}</Text> : null}

          <Text style={styles.section}>Pembeli</Text>
          <View style={styles.card}>
            <Text style={styles.name}>{order.shipping.full_name}</Text>
            <Text style={styles.muted}>{order.shipping.phone}</Text>
            <Text style={styles.muted}>{order.shipping.address}, {order.shipping.city}</Text>
            <Pressable testID="admin-wa-customer" style={styles.waBtn}
              onPress={() => Linking.openURL(`https://wa.me/${waNumber(order.shipping.phone)}?text=${encodeURIComponent(`Halo ${order.shipping.full_name}, pesanan ${order.order_id} di Pusat Grosir Sidoarjo: ${ORDER_STATUS_LABEL[order.status]}.`)}`)}>
              <Icon name="logo-whatsapp" size={18} color={colors.onSuccess} />
              <Text style={styles.waText}>Chat Pembeli via WhatsApp</Text>
            </Pressable>
          </View>

          <Text style={styles.section}>Produk</Text>
          <View style={styles.card}>
            {order.items.map((it) => (
              <View key={it.product_id} style={styles.itemRow}>
                <Image source={it.image} style={styles.img} contentFit="cover" />
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemName} numberOfLines={2}>{it.name}</Text>
                  <Text style={styles.muted}>{it.quantity} x {formatIDR(it.price)}</Text>
                </View>
                <Text style={styles.itemName}>{formatIDR(it.price * it.quantity)}</Text>
              </View>
            ))}
            <View style={styles.sep} />
            <View style={styles.between}><Text style={styles.muted}>Subtotal</Text><Text style={styles.itemName}>{formatIDR(order.subtotal)}</Text></View>
            <View style={styles.between}><Text style={styles.muted}>Ongkir</Text><Text style={styles.itemName}>{formatIDR(order.shipping_cost)}</Text></View>
            <View style={styles.between}><Text style={styles.name}>Total</Text><Text style={styles.total}>{formatIDR(order.total)}</Text></View>
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 6, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  orderId: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500" },
  status: { fontSize: fontSize.sm, fontWeight: "500" },
  section: { fontSize: fontSize.sm, color: colors.muted },
  muted: { fontSize: fontSize.sm, color: colors.muted },
  err: { color: colors.error, fontSize: fontSize.sm },
  name: { fontSize: fontSize.base, color: colors.onSurface, fontWeight: "500" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  actionBtn: { width: "48.5%", flexGrow: 1, minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  actionActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  actionText: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  waBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.success, borderRadius: radius.pill, minHeight: 44, marginTop: spacing.sm },
  waText: { color: colors.onSuccess, fontWeight: "500" },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  img: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  itemName: { fontSize: fontSize.sm, color: colors.onSurface },
  total: { fontSize: fontSize.lg, color: colors.brandPrimary, fontWeight: "500" },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: 4 },
});
