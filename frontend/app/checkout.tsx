import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { useCart } from "@/src/cart-context";
import { useAuth } from "@/src/auth-context";
import { api, type Address, type Courier, type Destination, type PaymentMethod, type Voucher } from "@/src/api";
import { DestinationSearch } from "@/src/components/destination-search";
import * as WebBrowser from "expo-web-browser";

export default function Checkout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { cart, refresh } = useCart();
  const { user } = useAuth();

  const [fullName, setFullName] = useState(user?.name ?? "");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("Sidoarjo");
  const [method, setMethod] = useState<PaymentMethod>("midtrans");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [voucherText, setVoucherText] = useState("");
  const [voucher, setVoucher] = useState<{ code: string; title: string; discount: number } | null>(null);
  const [voucherErr, setVoucherErr] = useState("");
  const [voucherBusy, setVoucherBusy] = useState(false);
  const [myVouchers, setMyVouchers] = useState<Voucher[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addrId, setAddrId] = useState("");
  const pickAddress = (a: Address) => {
    setAddrId(a.address_id);
    setFullName(a.recipient);
    setPhone(a.phone);
    setAddress(`${a.address}${a.postal_code ? `, ${a.postal_code}` : ""}`);
    setCity(a.city);
  };

  useEffect(() => {
    if (!user) return;
    api.addresses().then((l) => { setAddresses(l); const d = l.find((a) => a.is_default) ?? l[0]; if (d) pickAddress(d); }).catch(() => {});
  }, [user]);

  useEffect(() => { api.myVouchers().then(setMyVouchers).catch(() => {}); }, []);

  const applyVoucher = async (code: string) => {
    if (!code.trim()) return;
    setVoucherBusy(true);
    setVoucherErr("");
    try {
      setVoucher(await api.applyVoucher(code.trim()));
      setVoucherText(code.trim().toUpperCase());
    } catch (e: any) {
      setVoucher(null);
      setVoucherErr(e.message);
    } finally {
      setVoucherBusy(false);
    }
  };

  const discount = voucher?.discount ?? 0;
  const params = useLocalSearchParams<{ store?: string }>();
  const storeId = params.store || cart.items[0]?.store_id || "pgs-official";
  const items = cart.items.filter((i) => i.store_id === storeId);
  const subtotal = items.reduce((t, i) => t + i.price * i.quantity, 0);
  const itemCount = items.reduce((t, i) => t + i.quantity, 0);
  const [couriers, setCouriers] = useState<Courier[]>([]);
  const [courier, setCourier] = useState("");
  const [dest, setDest] = useState<Destination | null>(null);
  const [autoShip, setAutoShip] = useState(false);
  const searchDest = useCallback(async (q: string) => { const r = await api.destinations(q); setAutoShip(r.auto); return r.data; }, []);
  useEffect(() => { api.shippingStatus().then((r) => setAutoShip(r.auto)).catch(() => {}); }, []);
  useEffect(() => {
    api.shippingRates(storeId, dest?.id).then((l) => {
      setCouriers(l);
      setCourier((c) => (l.some((x) => x.code === c) ? c : l[0]?.code || ""));
    }).catch(() => {});
  }, [storeId, dest?.id]);
  const shipCost = couriers.find((c) => c.code === courier)?.cost ?? 0;
  const total = subtotal - discount + shipCost;
  const [balance, setBalance] = useState(0);
  const [useBalance, setUseBalance] = useState(false);
  useEffect(() => { if (user) api.wallet().then((w) => setBalance(w.balance)).catch(() => {}); }, [user]);
  const balanceUsed = useBalance ? Math.min(balance, total) : 0;
  const toPay = total - balanceUsed;

  const submit = async () => {
    setErr("");
    if (!fullName.trim() || !phone.trim() || !address.trim() || !city.trim()) {
      setErr("Lengkapi semua data pengiriman");
      return;
    }
    if (itemCount === 0) {
      setErr("Keranjang kosong");
      return;
    }
    if (!courier) {
      setErr("Pilih kurir pengiriman");
      return;
    }
    setLoading(true);
    try {
      const order = await api.checkout({ full_name: fullName, phone, address, city, payment_method: toPay === 0 && balanceUsed > 0 ? "saldo" : method, use_balance: useBalance, voucher_code: voucher?.code, store_id: storeId, courier, destination_id: dest?.id ?? null, destination_label: dest?.label ?? "" });
      await refresh();
      router.replace(`/order/${order.order_id}` as any);
      if (order.payment_url) await WebBrowser.openBrowserAsync(order.payment_url);
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
        {user ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.sm }}>
            {addresses.map((a) => (
              <Pressable key={a.address_id} testID={`co-addr-${a.address_id}`} onPress={() => pickAddress(a)} style={[styles.vChip, addrId === a.address_id && { backgroundColor: colors.brandPrimary }]}>
                <Icon name="location-outline" size={14} color={addrId === a.address_id ? colors.onBrandPrimary : colors.brandPrimary} />
                <Text style={[styles.vChipText, addrId === a.address_id && { color: colors.onBrandPrimary }]}>{a.label} · {a.recipient}</Text>
              </Pressable>
            ))}
            <Pressable testID="co-addr-manage" onPress={() => router.push("/account/addresses" as any)} style={styles.vChip}>
              <Icon name="add" size={14} color={colors.brandPrimary} />
              <Text style={styles.vChipText}>{addresses.length ? "Kelola alamat" : "Simpan alamat"}</Text>
            </Pressable>
          </ScrollView>
        ) : null}
        <View style={styles.card}>
          <Input testID="co-name" label="Nama Lengkap" value={fullName} onChangeText={setFullName} />
          <Input testID="co-phone" label="No. HP / WhatsApp" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
          <Input testID="co-address" label="Alamat lengkap" value={address} onChangeText={setAddress} multiline />
          <Input testID="co-city" label="Kota" value={city} onChangeText={setCity} />
        </View>

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Toko & Kurir</Text>
        <View style={styles.card} testID="checkout-couriers">
          <Text style={styles.paySub}>Dikirim dari: {items[0]?.store_name ?? "-"}</Text>
          {autoShip ? (
            <View style={{ gap: 4 }}>
              <Text style={styles.paySub}>Kecamatan tujuan (untuk ongkir otomatis JNE / J&T / SiCepat)</Text>
              <DestinationSearch testID="co-dest" search={searchDest} value={dest} onPick={setDest} />
            </View>
          ) : null}
          {autoShip && !dest ? <Text style={styles.paySub}>Pilih kecamatan tujuan dulu; sementara tampil tarif standar.</Text> : null}
          {couriers.map((c) => (
            <Pressable key={c.code} testID={`co-courier-${c.code}`} onPress={() => setCourier(c.code)}
              style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 }}>
              <Icon name={courier === c.code ? "radio-button-on" : "radio-button-off"} size={20} color={courier === c.code ? colors.brandPrimary : colors.muted} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.onSurface, fontSize: fontSize.base }}>{c.name}</Text>
                {c.eta ? <Text style={styles.paySub}>Estimasi {c.eta}</Text> : null}
              </View>
              <Text style={{ color: colors.onSurface, fontWeight: "600" }}>{c.cost ? formatIDR(c.cost) : "Gratis"}</Text>
            </Pressable>
          ))}
        </View>

        {balance > 0 ? (
          <>
            <Text style={[styles.section, { marginTop: spacing.xl }]}>Saldo</Text>
            <Pressable testID="co-use-balance" style={[styles.card, styles.payRow]} onPress={() => setUseBalance((v) => !v)}>
              <Icon name={useBalance ? "checkbox" : "square-outline"} size={22} color={useBalance ? colors.brandPrimary : colors.muted} />
              <View style={{ flex: 1 }}>
                <Text style={styles.payLabel}>Pakai saldo {formatIDR(balance)}</Text>
                <Text style={styles.paySub}>{useBalance ? (toPay === 0 ? "Pesanan lunas dengan saldo" : `Sisa ${formatIDR(toPay)} dibayar dengan metode di bawah`) : "Dari refund komplain yang disetujui"}</Text>
              </View>
            </Pressable>
          </>
        ) : null}

        {toPay > 0 ? <Text style={[styles.section, { marginTop: spacing.xl }]}>Metode Pembayaran</Text> : null}
        {toPay > 0 ? <View style={styles.card}>
          {([
            { id: "midtrans", label: "Midtrans", sub: "QRIS · Transfer Bank (VA) · GoPay · ShopeePay", icon: "qr-code-outline" },
            { id: "xendit", label: "Xendit", sub: "QRIS · Transfer Bank (VA) · OVO · DANA · ShopeePay", icon: "wallet-outline" },
            { id: "cod", label: "COD (Bayar di Tempat)", sub: "Bayar tunai saat barang diterima", icon: "cash-outline" },
          ] as const).map((m) => (
            <Pressable
              key={m.id}
              testID={`pay-${m.id}`}
              style={styles.payRow}
              onPress={() => setMethod(m.id)}
            >
              <Icon name={m.icon as any} size={20} color={colors.onSurface} />
              <View style={{ flex: 1 }}>
                <Text style={styles.payLabel}>{m.label}</Text>
                <Text style={styles.paySub}>{m.sub}</Text>
              </View>
              <View style={[styles.radio, method === m.id && styles.radioActive]}>
                {method === m.id ? <View style={styles.radioDot} /> : null}
              </View>
            </Pressable>
          ))}
        </View> : null}

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Voucher Diskon</Text>
        <View style={styles.card} testID="checkout-voucher">
          <View style={styles.voucherRow}>
            <TextInput
              testID="co-voucher-input"
              value={voucherText}
              onChangeText={(t) => { setVoucherText(t.toUpperCase()); if (voucher) setVoucher(null); setVoucherErr(""); }}
              placeholder="Masukkan kode voucher"
              placeholderTextColor={colors.muted}
              autoCapitalize="characters"
              style={[styles.input, { flex: 1 }]}
            />
            {voucher ? (
              <Pressable testID="co-voucher-remove" style={styles.voucherBtnOutline} onPress={() => { setVoucher(null); setVoucherText(""); }}>
                <Text style={styles.voucherBtnOutlineText}>Hapus</Text>
              </Pressable>
            ) : (
              <Pressable testID="co-voucher-apply" style={styles.voucherBtn} onPress={() => applyVoucher(voucherText)} disabled={voucherBusy}>
                {voucherBusy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.payBtnText}>Pakai</Text>}
              </Pressable>
            )}
          </View>
          {voucher ? <Text style={styles.voucherOk} testID="co-voucher-ok">{voucher.title} · hemat {formatIDR(voucher.discount)}</Text> : null}
          {voucherErr ? <Text style={styles.err} testID="co-voucher-error">{voucherErr}</Text> : null}
          {myVouchers.length && !voucher ? (
            <View style={styles.myVouchers}>
              <Text style={styles.paySub}>Voucher yang sudah kamu klaim:</Text>
              <View style={styles.chipRow}>
                {myVouchers.map((v) => (
                  <Pressable key={v.code} testID={`co-my-voucher-${v.code}`} style={styles.vChip} onPress={() => applyVoucher(v.code)}>
                    <Icon name="ticket-outline" size={14} color={colors.brandPrimary} />
                    <Text style={styles.vChipText}>{v.code}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
        </View>

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Ringkasan</Text>
        <View style={styles.card}>
          <Row label={`Subtotal (${itemCount} item)`} value={formatIDR(subtotal)} />
          <Row label={`Ongkos kirim${couriers.find((c) => c.code === courier) ? ` (${couriers.find((c) => c.code === courier)!.name})` : ""}`} value={formatIDR(shipCost)} />
          {discount > 0 ? <Row label={`Voucher ${voucher?.code}`} value={`-${formatIDR(discount)}`} /> : null}
          <View style={styles.sep} />
          {balanceUsed > 0 ? <Row label="Pakai saldo" value={`-${formatIDR(balanceUsed)}`} /> : null}
          <Row label="Total Pembayaran" value={formatIDR(toPay)} big />
        </View>

        {err ? <Text style={styles.err} testID="checkout-error">{err}</Text> : null}
      </ScrollView>

      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.md, insets.bottom + spacing.sm) }]}>
        {err ? <Text style={styles.errBar} testID="checkout-error-bar">{err}</Text> : null}
        <View style={styles.bottomRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.smallLabel}>Total bayar</Text>
          <Text style={styles.totalValue}>{formatIDR(toPay)}</Text>
        </View>
        <Pressable testID="pay-now-btn" style={styles.payBtn} onPress={submit} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.payBtnText}>Bayar Sekarang</Text>}
        </Pressable>
        </View>
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
  payLabel: { color: colors.onSurface, fontSize: fontSize.sm, fontWeight: "500" },
  paySub: { color: colors.muted, fontSize: 11, marginTop: 2 },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },

  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  rowLabel: { color: colors.muted, fontSize: fontSize.sm },
  rowValue: { color: colors.onSurface, fontSize: fontSize.sm },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.sm },

  err: { color: colors.error, fontSize: fontSize.sm, marginTop: spacing.md },
  voucherRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  voucherBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center", alignItems: "center", minWidth: 80 },
  voucherBtnOutline: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center" },
  voucherBtnOutlineText: { color: colors.brandPrimary, fontWeight: "500" },
  voucherOk: { color: colors.success, fontSize: fontSize.sm, marginTop: spacing.sm },
  myVouchers: { marginTop: spacing.md, gap: spacing.sm },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  vChip: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 34, backgroundColor: colors.brandTertiary },
  vChipText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "600" },

  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: spacing.sm },
  bottomRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  errBar: { color: colors.error, fontSize: fontSize.sm },
  smallLabel: { fontSize: 11, color: colors.muted },
  totalValue: { fontSize: fontSize.lg, color: colors.brandPrimary, fontWeight: "500" },
  payBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: 14, borderRadius: radius.pill, minWidth: 180, alignItems: "center" },
  payBtnText: { color: colors.onBrandPrimary, fontWeight: "500" },
});
