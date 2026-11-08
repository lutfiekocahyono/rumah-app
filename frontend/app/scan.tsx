import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, Linking } from "react-native";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ConfirmDialog } from "@/src/components/confirm-dialog";

type Mode = "product" | "pickup";
const TYPES = ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "code93", "itf14", "qr"] as const;

function PermissionCard({ perm, ask }: { perm: ReturnType<typeof useCameraPermissions>[0]; ask: () => void }) {
  const blocked = perm && !perm.granted && !perm.canAskAgain;
  return (
    <View style={styles.permCard} testID="scan-permission">
      <Icon name="camera-outline" size={40} color={colors.brandPrimary} />
      <Text style={styles.permTitle}>Izinkan kamera untuk scan</Text>
      <Text style={styles.muted}>Kamera dipakai untuk membaca barcode produk dan kode ambil pesanan. Anda juga bisa mengetik kodenya di bawah.</Text>
      {blocked ? (
        <Pressable testID="scan-open-settings" style={styles.primary} onPress={() => Linking.openSettings()}>
          <Text style={styles.primaryText}>Buka Pengaturan</Text>
        </Pressable>
      ) : (
        <Pressable testID="scan-allow-camera" style={styles.primary} onPress={ask}>
          <Text style={styles.primaryText}>Izinkan Kamera</Text>
        </Pressable>
      )}
    </View>
  );
}

function PickupResult({ order, done, busy, onHandOver, onAgain }: { order: Order; done: boolean; busy: boolean; onHandOver: () => void; onAgain: () => void }) {
  const settled = done || order.status === "completed";
  const due = order.payment_method === "cod" && !settled ? Math.max(0, order.total - (order.balance_used ?? 0)) : 0;
  const canHand = ["paid", "cod", "processing"].includes(order.status) && !done;
  return (
    <View style={styles.result} testID="pickup-result">
      <Text style={styles.resTitle}>{done ? "Pesanan diserahkan ✓" : `Pesanan ${order.order_id}`}</Text>
      <Text style={styles.muted}>
        {order.shipping?.name ? `${order.shipping.name} · ` : ""}Status: <Text style={styles.bold} testID="pickup-status">{ORDER_STATUS_LABEL[order.status]}</Text>
        {order.ready_at ? " · siap diambil" : ""}
      </Text>
      {order.items.map((it, i) => (
        <Text key={i} style={styles.item} numberOfLines={2}>{it.quantity}× {it.name}{it.variant_name ? ` (${it.variant_name})` : ""}</Text>
      ))}
      <Text style={[styles.bold, { color: due ? colors.error : colors.success }]} testID="pickup-due">
        {due ? `Tagih tunai: ${formatIDR(due)}` : settled ? "Pesanan sudah selesai / diserahkan" : "Sudah lunas — tidak perlu tagih"}
      </Text>
      {canHand ? (
        <Pressable testID="pickup-complete" style={styles.primary} onPress={onHandOver} disabled={busy}>
          {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Serahkan & Selesaikan</Text>}
        </Pressable>
      ) : !done ? <Text style={styles.muted}>Pesanan dengan status ini tidak bisa diserahkan.</Text> : null}
      <Pressable testID="scan-again" style={styles.outline} onPress={onAgain}>
        <Text style={styles.outlineText}>Scan lagi</Text>
      </Pressable>
    </View>
  );
}

/** Scan: barcode produk -> buka produknya; kode ambil pesanan -> kasir menyerahkan pesanan. */
export default function Scan() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [perm, ask] = useCameraPermissions();
  const [cashier, setCashier] = useState(false);
  const [mode, setMode] = useState<Mode>("product");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [done, setDone] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const lock = useRef(false);

  useEffect(() => {
    if (!user) { setCashier(false); return; }
    if (user.role === "admin" || user.role === "store_admin") { setCashier(true); return; }
    api.myStore().then((s) => setCashier(!!s && s.status === "active")).catch(() => setCashier(false));
  }, [user]);

  const lookup = async (raw: string) => {
    const c = raw.trim();
    if (!c || lock.current) return;
    // a scanned product link (QR) opens the product directly, no lookup needed
    const link = mode === "product" ? c.match(/\/product\/(pgs-\d+)\/?$/i) : null;
    if (link) { router.push(`/product/${link[1].toLowerCase()}` as any); return; }
    if (mode === "pickup" && !/^[\d\s-]{4,12}$/.test(c)) { setMsg({ ok: false, text: "Kode ambil berupa 6 digit angka. Untuk produk, pilih mode Barcode Produk." }); return; }
    lock.current = true;
    setBusy(true);
    setMsg(null);
    try {
      if (mode === "product") {
        const p = await api.productByCode(c);
        setMsg({ ok: true, text: `Membuka ${p.name}` });
        router.push(`/product/${p.product_id}` as any);
        setTimeout(() => { lock.current = false; }, 1500);
      } else {
        setOrder(await api.pickupLookup(c));
        setDone(false);
        setCode(c);
      }
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
      setTimeout(() => { lock.current = false; }, 1500); // avoid re-reading the same wrong code every frame
    } finally { setBusy(false); }
  };
  const onScan = (r: BarcodeScanningResult) => { if (!order) void lookup(r.data); };
  const handOver = async () => {
    setConfirm(false);
    setBusy(true);
    try { setOrder(await api.pickupComplete(code)); setDone(true); } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  };
  const again = () => { setOrder(null); setDone(false); setCode(""); setMsg(null); lock.current = false; };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="scan-screen">
      <View style={styles.header}>
        <Pressable testID="header-back" hitSlop={8} style={styles.back} onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)" as any))}>
          <Icon name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Scan</Text>
        <View style={styles.back} />
      </View>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {cashier ? (
          <View style={styles.modes}>
            {([["product", "Barcode Produk", "barcode-outline"], ["pickup", "Kode Ambil", "bag-check-outline"]] as const).map(([m, label, icon]) => (
              <Pressable key={m} testID={`scan-mode-${m}`} style={[styles.mode, mode === m && styles.modeOn]} onPress={() => { setMode(m); again(); }}>
                <Icon name={icon} size={18} color={mode === m ? colors.onBrandPrimary : colors.brandPrimary} />
                <Text style={[styles.modeText, mode === m && { color: colors.onBrandPrimary }]}>{label}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}
        <Text style={styles.muted}>
          {mode === "product" ? "Arahkan kamera ke barcode atau QR produk. Produknya langsung terbuka." : "Scan QR / ketik 6 digit kode ambil yang ditunjukkan pembeli."}
        </Text>
        {order ? (
          <PickupResult order={order} done={done} busy={busy} onHandOver={() => setConfirm(true)} onAgain={again} />
        ) : !perm ? <ActivityIndicator color={colors.brandPrimary} /> : perm.granted ? (
          <View style={styles.camWrap} testID="scan-camera">
            <CameraView style={StyleSheet.absoluteFill} facing="back" barcodeScannerSettings={{ barcodeTypes: [...TYPES] }} onBarcodeScanned={busy ? undefined : onScan} />
            <View style={styles.frame} pointerEvents="none" />
          </View>
        ) : <PermissionCard perm={perm} ask={ask} />}
        {!order ? (
          <View style={styles.manual}>
            <TextInput testID="scan-code-input" value={code} onChangeText={setCode} onSubmitEditing={() => lookup(code)} returnKeyType="search"
              placeholder={mode === "product" ? "Ketik barcode / SKU" : "Ketik kode ambil (6 digit)"} placeholderTextColor={colors.muted}
              keyboardType={mode === "pickup" ? "number-pad" : "default"} autoCapitalize="none" autoCorrect={false} style={styles.input} />
            <Pressable testID="scan-code-submit" style={[styles.primary, { paddingHorizontal: spacing.lg }]} onPress={() => lookup(code)} disabled={busy || !code.trim()}>
              {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Cari</Text>}
            </Pressable>
          </View>
        ) : null}
        {msg ? <Text style={[styles.muted, { color: msg.ok ? colors.success : colors.error }]} testID={msg.ok ? "scan-msg-ok" : "scan-msg-error"}>{msg.text}</Text> : null}
      </ScrollView>
      <ConfirmDialog visible={confirm} title="Serahkan pesanan?" danger={false}
        message={order ? `Pesanan ${order.order_id} akan ditandai selesai.${order.payment_method === "cod" ? " Pastikan uang tunai sudah diterima." : ""}` : ""}
        confirmLabel="Ya, serahkan" onConfirm={handOver} onCancel={() => setConfirm(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.sm, minHeight: 52, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { flex: 1, textAlign: "center", fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  body: { padding: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 560, alignSelf: "center" },
  modes: { flexDirection: "row", gap: spacing.sm },
  mode: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, paddingHorizontal: spacing.sm },
  modeOn: { backgroundColor: colors.brandPrimary },
  modeText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  muted: { fontSize: 13, color: colors.onSurfaceSecondary },
  bold: { fontWeight: "700", color: colors.onSurface },
  camWrap: { width: "100%", aspectRatio: 1, borderRadius: radius.lg, overflow: "hidden", backgroundColor: "#000", alignItems: "center", justifyContent: "center" },
  frame: { width: "70%", height: "40%", borderWidth: 3, borderColor: colors.brandPrimary, borderRadius: radius.md },
  permCard: { alignItems: "center", gap: spacing.sm, padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary },
  permTitle: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  manual: { flexDirection: "row", gap: spacing.sm },
  input: { flex: 1, minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, color: colors.onSurface, backgroundColor: colors.surface },
  primary: { minHeight: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600" },
  outline: { minHeight: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  outlineText: { color: colors.onSurface, fontWeight: "600" },
  result: { gap: spacing.sm, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  resTitle: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface },
  item: { fontSize: 13, color: colors.onSurface },
});
