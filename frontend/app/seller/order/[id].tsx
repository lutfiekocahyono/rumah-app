import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { OrderTracking } from "@/src/components/order-tracking";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { adminStyles, Card, Field, PrimaryButton } from "@/src/components/admin-form";
import { fmtDate } from "@/src/utils/date";

export default function SellerOrderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [order, setOrder] = useState<Order | null>(null);
  const [resi, setResi] = useState("");
  const [busy, setBusy] = useState("");
  const [askCancel, setAskCancel] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (id) api.sellerOrder(id).then(setOrder).catch((e) => setErr(e.message)); }, [id]);

  const move = async (status: string) => {
    setBusy(status);
    setErr("");
    try { setOrder(await api.sellerSetOrderStatus(id!, status, resi)); setAskCancel(false); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  if (!order) {
    return (
      <View style={[adminStyles.root, { paddingTop: insets.top }]}>
        <ScreenHeader title="Detail Pesanan" />
        {err ? <Text style={[adminStyles.err, { padding: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />}
      </View>
    );
  }
  const pickup = order.courier?.code === "pickup";
  const s = order.status;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="seller-order-detail">
      <ScreenHeader title={order.order_id} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        <Text style={styles.status} testID="so-status">{ORDER_STATUS_LABEL[s]}</Text>
        <OrderTracking order={order} />
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {order.user_id ? (
            <View style={{ flex: 1 }}>
              <PrimaryButton testID="so-chat" label="Chat Pembeli" variant="outline" loading={busy === "chat"} onPress={async () => {
                setBusy("chat");
                try { const c = await api.sellerStartChat(order.order_id); router.push(`/chat/${c.conv_id}` as any); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
              }} />
            </View>
          ) : null}
          {order.complaint_id ? (
            <View style={{ flex: 1 }}>
              <PrimaryButton testID="so-complaint" label="Lihat Komplain" variant="danger" onPress={() => router.push(`/complaint/${order.complaint_id}` as any)} />
            </View>
          ) : null}
        </View>
        <Card>
          {order.items.map((i) => (
            <View key={i.product_id} style={styles.item}>
              <Image source={i.image} style={styles.img} contentFit="cover" />
              <Text style={styles.name} numberOfLines={2}>{i.name}</Text>
              <Text style={styles.qty}>{i.quantity} x {formatIDR(i.price)}</Text>
            </View>
          ))}
          <Text style={styles.total}>Total {formatIDR(order.total)} · {order.payment_method.toUpperCase()}</Text>
        </Card>
        <Card>
          <Text style={adminStyles.section}>{pickup ? "Pemesan (ambil di toko)" : "Kirim ke"}</Text>
          <Text style={styles.name}>{order.shipping.full_name} · {order.shipping.phone}</Text>
          <Text style={adminStyles.muted}>{order.shipping.address}, {order.shipping.city}</Text>
        </Card>
        {err ? <Text style={adminStyles.err} testID="so-error">{err}</Text> : null}
        {s === "pending" ? <Text style={adminStyles.muted}>Menunggu pembayaran pembeli.</Text> : null}
        {s === "cod" && order.expires_at ? (
          <Card>
            <Text style={adminStyles.muted} testID="so-expires">Batal otomatis jika belum diproses: {fmtDate(order.expires_at)}</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              {[24, 48].map((h) => (
                <View key={h} style={{ flex: 1 }}>
                  <PrimaryButton testID={`so-extend-${h}`} label={`Perpanjang ${h} jam`} variant="outline" loading={busy === `extend${h}`} onPress={async () => {
                    setBusy(`extend${h}`); setErr("");
                    try { setOrder(await api.sellerExtendOrder(order.order_id, h)); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
                  }} />
                </View>
              ))}
            </View>
          </Card>
        ) : null}
        {s === "paid" || s === "cod" ? <PrimaryButton testID="so-process" label="Proses Pesanan" loading={busy === "processing"} onPress={() => move("processing")} /> : null}
        {s === "processing" ? (
          pickup ? (
            <>
              {order.ready_at ? (
                <Text style={adminStyles.ok} testID="so-ready-info">Siap diambil sejak {fmtDate(order.ready_at)} — pembeli sudah diberi tahu</Text>
              ) : (
                <PrimaryButton testID="so-ready" label="Siap Diambil" variant="outline" loading={busy === "ready"} onPress={async () => {
                  setBusy("ready"); setErr("");
                  try { setOrder(await api.sellerReadyOrder(order.order_id)); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
                }} />
              )}
              <PrimaryButton testID="so-complete" label="Sudah Diambil Pembeli (Selesai)" loading={busy === "completed"} onPress={() => move("completed")} />
            </>
          ) : (
            <Card>
              <Field testID="so-resi" label="Nomor resi pengiriman" value={resi} onChangeText={setResi} autoCapitalize="characters" placeholder="Contoh: JNE1234567890" />
              <PrimaryButton testID="so-ship" label="Kirim Pesanan" loading={busy === "shipped"} onPress={() => move("shipped")} />
            </Card>
          )
        ) : null}
        {s === "shipped" ? <Text style={adminStyles.muted}>Menunggu pembeli mengonfirmasi pesanan diterima.</Text> : null}
        {["pending", "paid", "cod", "processing"].includes(s) ? (
          <PrimaryButton testID="so-cancel" label="Batalkan Pesanan" variant="danger" onPress={() => setAskCancel(true)} />
        ) : null}
      </ScrollView>
      <ConfirmDialog visible={askCancel} title="Batalkan pesanan?" message="Stok akan dikembalikan dan pembeli mendapat notifikasi." confirmLabel="Batalkan"
        loading={busy === "cancelled"} onConfirm={() => move("cancelled")} onCancel={() => setAskCancel(false)} />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  status: { fontSize: fontSize.lg, fontWeight: "600", color: colors.brandPrimary },
  item: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  img: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { flex: 1, fontSize: fontSize.sm, color: colors.onSurface },
  qty: { fontSize: 12, color: colors.muted },
  total: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface },
});
