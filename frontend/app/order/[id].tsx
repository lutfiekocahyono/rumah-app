import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, AppState } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import * as WebBrowser from "expo-web-browser";
import QRCode from "react-native-qrcode-svg";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { OrderTracking } from "@/src/components/order-tracking";
import { fmtDate } from "@/src/utils/date";
import { useStore } from "@/src/store-context";

const METHOD_LABEL = { midtrans: "Midtrans", xendit: "Xendit", cod: "COD (Bayar di Tempat)", saldo: "Saldo" };
const COMPLAINT_DAYS = 7;

/** Komplain: after the order was shipped (or picked up), for 7 days. Server re-checks. */
function canComplain(o: Order) {
  if (!["shipped", "completed"].includes(o.status)) return false;
  const h = [...o.status_history].reverse().find((x) => x.status === "shipped") ?? o.status_history.find((x) => x.status === "completed");
  if (!h) return false;
  const at = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(h.at) ? h.at : h.at + "Z").getTime();
  return Date.now() - at <= COMPLAINT_DAYS * 86400000;
}

export default function OrderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { stores } = useStore();
  const [extraStore, setExtraStore] = useState<{ store_id: string; address?: string; pickup_hours?: string } | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [err, setErr] = useState("");

  const check = useCallback(async () => {
    if (!id) return;
    setChecking(true);
    setErr("");
    try {
      setOrder(await api.refreshOrder(id));
    } catch (e: any) {
      setErr(e?.message || "Gagal memuat pesanan");
    } finally {
      setChecking(false);
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void check(); }, [check]);

  // Re-check when the user comes back from the payment page.
  useEffect(() => {
    const sub = AppState.addEventListener("change", (s) => { if (s === "active") void check(); });
    return () => sub.remove();
  }, [check]);

  const pay = async () => {
    if (!order?.payment_url) return;
    await WebBrowser.openBrowserAsync(order.payment_url);
    void check();
  };

  // Pickup from a non-official marketplace store: fetch its public page for address/hours
  useEffect(() => {
    if (order?.courier?.code === "pickup" && !stores.some((s) => s.store_id === order.store_id)) {
      api.storePage(order.store_id).then(setExtraStore).catch(() => {});
    }
  }, [order?.store_id, order?.courier?.code, stores]);

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>;
  const pickupStore = stores.find((s) => s.store_id === order?.store_id) ?? (extraStore?.store_id === order?.store_id ? extraStore : undefined);
  if (!order) {
    return (
      <View style={[styles.center, { gap: spacing.md }]} testID="order-not-found">
        <Text style={styles.muted}>{err || "Pesanan tidak ditemukan"}</Text>
        <Pressable style={styles.primaryBtn} onPress={() => router.replace("/(tabs)" as any)}>
          <Text style={styles.primaryText}>Kembali ke Beranda</Text>
        </Pressable>
      </View>
    );
  }

  const paid = ["paid", "processing", "shipped", "completed"].includes(order.status);
  const pending = order.status === "pending";
  const statusColor = paid ? colors.success : pending ? colors.warning : order.status === "cod" ? colors.info : colors.error;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="order-detail">
      <View style={styles.header}>
        <Pressable testID="order-back" hitSlop={8} onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)" as any))}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Detail Pesanan</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 160 }}>
        <View style={[styles.statusCard, { borderColor: statusColor }]}>
          <Icon name={paid ? "checkmark-circle" : pending ? "time-outline" : order.status === "cod" ? "cube-outline" : "close-circle"} size={36} color={statusColor} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.statusText, { color: statusColor }]} testID="order-status">{ORDER_STATUS_LABEL[order.status]}</Text>
            <Text style={styles.muted}>{order.order_id}</Text>
          </View>
        </View>
        {pending ? (
          <Text style={styles.hint}>Selesaikan pembayaran di halaman {METHOD_LABEL[order.payment_method]}, lalu kembali ke sini. Status diperbarui otomatis.</Text>
        ) : null}
        {err ? <Text style={styles.err}>{err}</Text> : null}

        <OrderTracking order={order} />
        {order.status === "shipped" ? (
          <Pressable testID="confirm-received-btn" style={styles.primaryBtn} disabled={checking} onPress={async () => {
            setChecking(true);
            try { setOrder(await api.confirmReceived(order.order_id)); } catch (e: any) { setErr(e.message); } finally { setChecking(false); }
          }}>
            <Text style={styles.primaryText}>Pesanan Sudah Diterima</Text>
          </Pressable>
        ) : null}

        {order.user_id ? (
          <View style={styles.actions}>
            <Pressable testID="chat-store-btn" style={styles.outlineBtn} disabled={checking} onPress={async () => {
              try { const c = await api.startChat(order.store_id); router.push(`/chat/${c.conv_id}` as any); } catch (e: any) { setErr(e.message); }
            }}>
              <Text style={styles.outlineText}>Chat Toko</Text>
            </Pressable>
            {order.complaint_id ? (
              <Pressable testID="view-complaint-btn" style={styles.outlineBtn} onPress={() => router.push(`/complaint/${order.complaint_id}` as any)}>
                <Text style={styles.outlineText}>Lihat Komplain</Text>
              </Pressable>
            ) : canComplain(order) ? (
              <Pressable testID="complain-btn" style={styles.outlineBtn} onPress={() => router.push(`/complaint/new?order=${order.order_id}` as any)}>
                <Text style={styles.outlineText}>Ajukan Komplain</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        <View style={styles.card}>
          {order.items.map((it) => (
            <View key={it.product_id} style={styles.itemRow}>
              <Image source={it.image} style={styles.itemImg} contentFit="cover" />
              <View style={{ flex: 1 }}>
                <Text style={styles.itemName} numberOfLines={2}>{it.name}</Text>
                <Text style={styles.muted}>{it.quantity} x {formatIDR(it.price)}</Text>
              </View>
              <Text style={styles.itemTotal}>{formatIDR(it.price * it.quantity)}</Text>
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <Row label="Subtotal" value={formatIDR(order.subtotal)} />
          <Row label="Ongkos kirim" value={formatIDR(order.shipping_cost)} />
          {order.discount ? <Row label={`Voucher ${order.voucher_code ?? ""}`} value={`-${formatIDR(order.discount)}`} /> : null}
          <Row label="Metode bayar" value={METHOD_LABEL[order.payment_method]} />
          <View style={styles.sep} />
          <Row label="Total" value={formatIDR(order.total)} big />
          {order.balance_used ? <Row label="Dibayar dengan saldo" value={`-${formatIDR(order.balance_used)}`} /> : null}
          {order.balance_used && order.payment_method !== "saldo" ? <Row label="Sisa dibayar" value={formatIDR(order.total - order.balance_used)} /> : null}
          {order.refunded ? <Row label="Sudah di-refund ke saldo" value={formatIDR(order.refunded)} /> : null}
        </View>

        {order.courier?.code === "pickup" ? (
          <View style={styles.card} testID="order-pickup-card">
            <Text style={styles.cardTitle}>Ambil di toko</Text>
            {order.pickup_code && !["cancelled", "expired", "failed", "completed"].includes(order.status) ? (
              <View style={styles.codeBox} testID="order-pickup-code">
                <Text style={styles.muted}>Kode ambil — tunjukkan QR atau 6 angka ini ke kasir</Text>
                <View style={styles.qr} testID="order-pickup-qr">
                  <QRCode value={`PGSAMBIL-${order.pickup_code}`} size={168} color="#000000" backgroundColor="#FFFFFF" />
                </View>
                <Text style={styles.code} selectable>{order.pickup_code}</Text>
              </View>
            ) : null}
            <Text style={styles.itemName}>{order.store_name}</Text>
            {!pickupStore?.address ? <Text style={styles.muted}>Alamat toko akan diinformasikan toko.</Text> : null}
            {pickupStore?.address ? <Text style={styles.muted}>{pickupStore.address}</Text> : null}
            {pickupStore?.pickup_hours ? <Text style={styles.muted}>Jam ambil: {pickupStore.pickup_hours}</Text> : null}
            {order.ready_at && order.status === "processing" ? (
              <Text style={[styles.muted, { color: colors.success, fontWeight: "600" }]} testID="order-ready">Pesanan siap diambil sejak {fmtDate(order.ready_at)}</Text>
            ) : null}
            {order.status === "cod" && order.expires_at ? (
              <Text style={styles.muted} testID="order-expires">Menunggu diproses toko. Batal otomatis bila belum diproses sampai {fmtDate(order.expires_at)}.</Text>
            ) : null}
            {order.payment_method === "cod" ? (
              <Text style={styles.muted} testID="order-cod-note">
                {order.status === "completed" ? "Lunas — dibayar tunai (COD) saat pengambilan." : ["cancelled", "expired", "failed"].includes(order.status) ? "Pesanan dibatalkan, tidak ada pembayaran." : "Bayar tunai (COD) saat mengambil pesanan."}
              </Text>
            ) : null}
          </View>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>{order.courier?.code === "pickup" ? "Pemesan" : "Dikirim ke"}</Text>
          <Text style={styles.itemName}>{order.shipping.full_name} · {order.shipping.phone}</Text>
          {order.courier?.code !== "pickup" ? <Text style={styles.muted}>{order.shipping.address}, {order.shipping.city}</Text> : null}
        </View>
      </ScrollView>

      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.lg, insets.bottom + spacing.sm) }]}>
        {pending && order.payment_url ? (
          <>
            <Pressable testID="check-status-btn" style={styles.outlineBtn} onPress={check} disabled={checking}>
              {checking ? <ActivityIndicator color={colors.onSurface} /> : <Text style={styles.outlineText}>Cek Status</Text>}
            </Pressable>
            <Pressable testID="pay-order-btn" style={styles.primaryBtn} onPress={pay}>
              <Text style={styles.primaryText}>Bayar Sekarang</Text>
            </Pressable>
          </>
        ) : (
          <>
            <Pressable testID="to-orders" style={styles.outlineBtn} onPress={() => router.replace("/orders" as any)}>
              <Text style={styles.outlineText}>Daftar Pesanan</Text>
            </Pressable>
            <Pressable testID="back-home" style={styles.primaryBtn} onPress={() => router.replace("/(tabs)" as any)}>
              <Text style={styles.primaryText}>Belanja Lagi</Text>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

function Row({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.muted, big && { color: colors.onSurface, fontWeight: "500" }]}>{label}</Text>
      <Text style={[styles.rowValue, big && { color: colors.brandPrimary, fontSize: fontSize.lg }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, padding: spacing.xl },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  title: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  statusCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1 },
  statusText: { fontSize: fontSize.lg, fontWeight: "500" },
  hint: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  err: { fontSize: fontSize.sm, color: colors.error },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  cardTitle: { fontSize: fontSize.sm, color: colors.muted },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  itemImg: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  itemName: { fontSize: fontSize.sm, color: colors.onSurface },
  itemTotal: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  muted: { fontSize: fontSize.sm, color: colors.muted },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  rowValue: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "500" },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  actions: { flexDirection: "row", gap: spacing.sm },
  codeBox: { alignItems: "center", backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, gap: 2 },
  qr: { padding: spacing.md, marginVertical: spacing.sm, backgroundColor: "#FFFFFF", borderRadius: radius.md }, // QR needs a white quiet zone in any theme
  code: { fontSize: 28, fontWeight: "800", letterSpacing: 6, color: colors.brandPrimary },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", gap: spacing.sm, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  outlineBtn: { flex: 1, minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  outlineText: { color: colors.onSurface, fontWeight: "500" },
  primaryBtn: { flex: 1, minHeight: 48, paddingHorizontal: spacing.xl, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "500" },
});
