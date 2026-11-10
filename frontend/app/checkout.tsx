import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { useCart } from "@/src/cart-context";
import { useAuth } from "@/src/auth-context";
import { api, type Address, type Courier, type Destination, type PaymentMethod } from "@/src/api";
import { DestinationSearch } from "@/src/components/destination-search";
import { BranchSwitcher } from "@/src/components/branch-switcher";
import { useStore } from "@/src/store-context";
import { co } from "@/src/components/checkout/styles";
import { Input, Row } from "@/src/components/checkout/fields";
import { VoucherSection, type AppliedVoucher } from "@/src/components/checkout/voucher-section";
import { BalanceSection, PaymentSection, type PayAvail } from "@/src/components/checkout/payment-section";
import { CourierList } from "@/src/components/checkout/courier-list";
import * as WebBrowser from "expo-web-browser";

// "GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281" -> "Surabaya"
const cityFromLabel = (label: string) => {
  const parts = label.split(",").map((s) => s.trim());
  return parts.length >= 3 ? parts[2].toLowerCase().replace(/\b\w/g, (ch) => ch.toUpperCase()) : null;
};
const pinOf = (a?: Address) => (a && a.lat != null && a.lng != null ? { lat: a.lat, lng: a.lng } : null);

export default function Checkout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { cart, refresh } = useCart();
  const { user } = useAuth();
  const { choose } = useStore();

  // --- buyer / address ---
  const [fullName, setFullName] = useState(user?.name ?? "");
  useEffect(() => { if (user?.name) setFullName((n) => n || user.name); }, [user?.name]);
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("Sidoarjo");
  const [cityIsBuyers, setCityIsBuyers] = useState(false); // default "Sidoarjo" must not count as the buyer's area
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addrId, setAddrId] = useState("");
  const [dest, setDest] = useState<Destination | null>(null);
  const pickAddress = (a: Address) => {
    setAddrId(a.address_id);
    setFullName(a.recipient);
    setPhone(a.phone);
    setAddress(`${a.address}${a.postal_code ? `, ${a.postal_code}` : ""}`);
    setCity(a.city);
    setCityIsBuyers(true);
    // Saved shipping area -> rates appear immediately, no search needed
    setDest(a.destination_id ? { id: a.destination_id, label: a.destination_label ?? "" } : null);
  };
  useEffect(() => {
    if (!user) return;
    api.addresses().then((l) => { setAddresses(l); const d = l.find((a) => a.is_default) ?? l[0]; if (d) pickAddress(d); }).catch(() => {});
  }, [user]);
  const pickDest = (d: Destination | null) => {
    setDest(d);
    const c = d ? cityFromLabel(d.label) : null;
    if (c) setCity(c);
  };

  // --- payment ---
  const [method, setMethod] = useState<PaymentMethod>("cod");
  const [payAvail, setPayAvail] = useState<PayAvail>({ midtrans: false, xendit: false, midtrans_sandbox: true });
  useEffect(() => { api.paymentMethods().then(setPayAvail).catch(() => {}); }, []);
  const [voucher, setVoucher] = useState<AppliedVoucher | null>(null);
  const [balance, setBalance] = useState(0);
  const [useBalance, setUseBalance] = useState(false);
  useEffect(() => { if (user) api.wallet().then((w) => setBalance(w.balance)).catch(() => {}); }, [user]);

  // --- store items & shipping ---
  const params = useLocalSearchParams<{ store?: string }>();
  const storeId = params.store || cart.items[0]?.store_id || "pgs-official";
  const items = cart.items.filter((i) => i.store_id === storeId);
  const subtotal = items.reduce((t, i) => t + i.price * i.quantity, 0);
  const itemCount = items.reduce((t, i) => t + i.quantity, 0);
  const [couriers, setCouriers] = useState<Courier[]>([]);
  const [courier, setCourier] = useState("");
  const [autoShip, setAutoShip] = useState(false);
  const [ratesKey, setRatesKey] = useState(0);
  const [ratesLoading, setRatesLoading] = useState(false);
  const searchDest = useCallback(async (q: string) => { const r = await api.destinations(q); setAutoShip(r.auto); return r.data; }, []);
  useEffect(() => { api.shippingStatus().then((r) => setAutoShip(r.auto)).catch(() => {}); }, []);
  const autoPickFor = useRef<number | null>(null); // destination we already auto-picked the cheapest courier for
  useEffect(() => {
    let stale = false; // ignore late responses after the destination changed again
    setRatesLoading(true);
    api.shippingRates(storeId, dest?.id).then((l) => {
      if (stale) return;
      setCouriers(l);
      const shippable = l.filter((x) => x.code !== "pickup" && x.active !== false);
      const freshDest = !!dest && autoPickFor.current !== dest.id;
      if (dest) autoPickFor.current = dest.id;
      setCourier((c) => {
        // After a new destination is picked, choose the cheapest delivery courier; on a reload keep the buyer's choice
        if (freshDest && shippable.length && payAvail.midtrans) return shippable.reduce((a, b) => (b.cost < a.cost ? b : a)).code;
        return l.some((x) => x.code === c) ? c : l[0]?.code || "";
      });
    }).catch(() => {}).finally(() => { if (!stale) setRatesLoading(false); });
    return () => { stale = true; };
  }, [storeId, dest, ratesKey, payAvail.midtrans]);

  // COD only for "Ambil di toko"; courier delivery must be paid online
  const isPickup = courier === "pickup";
  useEffect(() => {
    if (!isPickup && method === "cod") { if (payAvail.midtrans) setMethod("midtrans"); else if (payAvail.xendit) setMethod("xendit"); }
    if (isPickup && method !== "cod" && !payAvail.midtrans && !payAvail.xendit) setMethod("cod");
  }, [isPickup, method, payAvail.midtrans, payAvail.xendit]);

  // --- totals ---
  const selectedCourier = couriers.find((c) => c.code === courier);
  const shipCost = selectedCourier?.cost ?? 0;
  const discount = voucher?.discount ?? 0;
  const total = subtotal - discount + shipCost;
  const balanceUsed = useBalance ? Math.min(balance, total) : 0;
  const toPay = total - balanceUsed;

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const validate = () => {
    if (!fullName.trim() || !phone.trim() || (!isPickup && (!address.trim() || !city.trim())))
      return isPickup ? "Lengkapi nama dan nomor HP pemesan" : "Lengkapi semua data pengiriman";
    if (itemCount === 0) return "Keranjang kosong";
    if (!courier) return "Pilih kurir pengiriman";
    if (!isPickup && toPay > 0 && !payAvail.midtrans && !payAvail.xendit)
      return "Pengiriman kurir wajib bayar online, yang saat ini belum tersedia. Pilih Ambil di toko (COD).";
    return "";
  };

  // Remember the shipping area on the saved address so next checkout quotes instantly
  const rememberArea = () => {
    const picked = addresses.find((a) => a.address_id === addrId);
    if (!picked || !dest || picked.destination_id === dest.id) return;
    const parts = dest.label.split(",").map((s) => s.trim());
    const areaPostal = parts.length >= 5 && /^\d{5}$/.test(parts[4]) ? parts[4] : picked.postal_code;
    api.saveAddress({
      label: picked.label, recipient: picked.recipient, phone: picked.phone, address: picked.address, is_default: picked.is_default,
      city: cityFromLabel(dest.label) ?? picked.city, postal_code: areaPostal, destination_id: dest.id, destination_label: dest.label,
    }, picked.address_id).catch(() => {});
  };

  const submit = async () => {
    const v = validate();
    setErr(v);
    if (v) return;
    setLoading(true);
    try {
      const order = await api.checkout({
        full_name: fullName, phone, address: isPickup ? "" : address, city: isPickup ? "" : city,
        payment_method: toPay === 0 && balanceUsed > 0 ? "saldo" : method, use_balance: useBalance, voucher_code: voucher?.code,
        store_id: storeId, courier, expected_shipping_cost: shipCost,
        destination_id: isPickup ? null : dest?.id ?? null, destination_label: isPickup ? "" : dest?.label ?? "",
      });
      await refresh();
      rememberArea();
      router.replace(`/order/${order.order_id}` as any);
      if (order.payment_url) await WebBrowser.openBrowserAsync(order.payment_url);
    } catch (e: any) {
      setErr(e?.message || "Gagal checkout");
      if (e?.status === 409) setRatesKey((k) => k + 1); // shipping changed: reload rates so the buyer sees the new price
    } finally {
      setLoading(false);
    }
  };

  const moveBranch = async (to: string) => {
    setErr("");
    const r = await api.moveCart(storeId, to).catch((e) => { setErr(e.message); return null; });
    if (!r) return;
    await choose(to);
    await refresh();
    router.setParams({ store: to });
    if (r.skipped.length) setErr(`${r.skipped.length} barang tidak tersedia di toko baru dan tetap di keranjang toko lama`);
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
        <Text style={co.section}>{isPickup ? "Data Pemesan" : "Alamat Pengiriman"}</Text>
        {user && !isPickup ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.sm }}>
            {addresses.map((a) => (
              <Pressable key={a.address_id} testID={`co-addr-${a.address_id}`} onPress={() => pickAddress(a)} style={[co.vChip, addrId === a.address_id && { backgroundColor: colors.brandPrimary }]}>
                <Icon name="location-outline" size={14} color={addrId === a.address_id ? colors.onBrandPrimary : colors.brandPrimary} />
                <Text style={[co.vChipText, addrId === a.address_id && { color: colors.onBrandPrimary }]}>{a.label} · {a.recipient}</Text>
              </Pressable>
            ))}
            <Pressable testID="co-addr-manage" onPress={() => router.push("/account/addresses" as any)} style={co.vChip}>
              <Icon name="add" size={14} color={colors.brandPrimary} />
              <Text style={co.vChipText}>{addresses.length ? "Kelola alamat" : "Simpan alamat"}</Text>
            </Pressable>
          </ScrollView>
        ) : null}
        <View style={co.card}>
          <Input testID="co-name" label="Nama Lengkap" value={fullName} onChangeText={setFullName} />
          <Input testID="co-phone" label="No. HP / WhatsApp" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
          {isPickup ? (
            <Text style={co.paySub} testID="co-pickup-note">Ambil sendiri di toko — alamat pengiriman tidak perlu diisi.</Text>
          ) : (
            <>
              <Input testID="co-address" label="Alamat lengkap" value={address} onChangeText={setAddress} multiline />
              <Input testID="co-city" label="Kota" value={city} onChangeText={(t) => { setCity(t); setCityIsBuyers(true); }} />
            </>
          )}
        </View>

        <Text style={[co.section, co.sectionGap]}>Toko & Kurir</Text>
        <View style={co.card} testID="checkout-couriers">
          <Text style={co.paySub}>Dikirim dari: {items[0]?.store_name ?? "-"}</Text>
          <BranchSwitcher storeId={storeId} items={items} area={dest?.label || (cityIsBuyers ? city : "")} pin={pinOf(addresses.find((a) => a.address_id === addrId))} pickup={isPickup} onMove={moveBranch} />
          {autoShip && !isPickup ? (
            <View style={{ gap: 4 }}>
              <Text style={co.paySub}>Kecamatan tujuan (untuk ongkir otomatis JNE / J&T / SiCepat)</Text>
              <DestinationSearch testID="co-dest" search={searchDest} value={dest} onPick={pickDest} />
            </View>
          ) : null}
          {autoShip && !dest && !isPickup ? <Text style={co.paySub}>Pilih kecamatan tujuan dulu; sementara tampil tarif standar.</Text> : null}
          <CourierList couriers={couriers} selected={courier} onPick={setCourier} />
        </View>

        <BalanceSection balance={balance} useBalance={useBalance} toPay={toPay} onToggle={() => setUseBalance((v) => !v)} />
        {toPay > 0 ? <PaymentSection isPickup={isPickup} payAvail={payAvail} method={method} onPick={setMethod} /> : null}
        <VoucherSection voucher={voucher} onChange={setVoucher} />

        <Text style={[co.section, co.sectionGap]}>Ringkasan</Text>
        <View style={co.card}>
          <Row label={`Subtotal (${itemCount} item)`} value={formatIDR(subtotal)} />
          <Row label={`Ongkos kirim${selectedCourier ? ` (${selectedCourier.name})` : ""}`} value={formatIDR(shipCost)} />
          {discount > 0 ? <Row label={`Voucher ${voucher?.code}`} value={`-${formatIDR(discount)}`} /> : null}
          <View style={styles.sep} />
          {balanceUsed > 0 ? <Row label="Pakai saldo" value={`-${formatIDR(balanceUsed)}`} /> : null}
          <Row label="Total Pembayaran" value={formatIDR(toPay)} big />
        </View>
      </ScrollView>

      <View style={[styles.bottom, { paddingBottom: Math.max(spacing.md, insets.bottom + spacing.sm) }]}>
        {err ? <Text style={styles.errBar} testID="checkout-error-bar">{err}</Text> : null}
        <View style={styles.bottomRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.smallLabel}>Total bayar</Text>
            <Text style={styles.totalValue}>{formatIDR(toPay)}</Text>
          </View>
          <Pressable testID="pay-now-btn" style={[styles.payBtn, ratesLoading && { opacity: 0.6 }]} onPress={submit} disabled={loading || ratesLoading}>
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={co.payBtnText}>{method === "cod" || toPay === 0 ? "Buat Pesanan" : "Bayar Sekarang"}</Text>}
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  title: { fontSize: fontSize.lg, fontWeight: "500", color: colors.onSurface },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.sm },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: spacing.sm },
  bottomRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  errBar: { color: colors.error, fontSize: fontSize.sm },
  smallLabel: { fontSize: 11, color: colors.muted },
  totalValue: { fontSize: fontSize.lg, color: colors.brandPrimary, fontWeight: "500" },
  payBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: 14, borderRadius: radius.pill, minWidth: 180, alignItems: "center" },
});
