import React, { useEffect, useState } from "react";
import { View, Text, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { colors, spacing, formatIDR } from "@/src/theme";
import { api, COMPLAINT_REASONS, type ComplaintReason, type Order } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Chips, Field, PrimaryButton, digits } from "@/src/components/admin-form";

export default function NewComplaint() {
  const { order: orderId } = useLocalSearchParams<{ order: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [order, setOrder] = useState<Order | null>(null);
  const [reason, setReason] = useState<ComplaintReason>("damaged");
  const [desc, setDesc] = useState("");
  const [wantRefund, setWantRefund] = useState<"yes" | "no">("yes");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (orderId) api.order(orderId).then(setOrder).catch((e) => setErr(e.message)); }, [orderId]);

  const codUnpaid = order?.payment_method === "cod" && order.status !== "completed";
  const submit = async () => {
    if (!order) return;
    if (desc.trim().length < 10) return setErr("Ceritakan masalahnya minimal 10 huruf");
    const refund = wantRefund === "yes" ? digits(amount) : 0;
    if (wantRefund === "yes" && (refund <= 0 || refund > order.total)) return setErr(`Nominal refund 1 – ${formatIDR(order.total)}`);
    setBusy(true);
    setErr("");
    try {
      const c = await api.createComplaint({ order_id: order.order_id, reason, description: desc.trim(), refund_amount: refund });
      router.replace(`/complaint/${c.complaint_id}` as any);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="complaint-new-screen">
      <ScreenHeader title="Ajukan Komplain" />
      {!order ? (
        err ? <Text style={[adminStyles.err, { padding: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
          <Card>
            <Text style={adminStyles.section}>Pesanan</Text>
            <Text style={{ color: colors.onSurface, fontWeight: "600" }}>{order.order_id} · {order.store_name}</Text>
            <Text style={adminStyles.muted}>Total {formatIDR(order.total)} · {order.items.length} produk</Text>
          </Card>
          <Card>
            <Text style={adminStyles.section}>Masalahnya apa?</Text>
            <Chips testID="cn-reason" value={reason} onChange={setReason} options={COMPLAINT_REASONS} />
            <Field testID="cn-desc" label="Ceritakan detailnya" value={desc} onChangeText={(t) => { setDesc(t); setErr(""); }} multiline maxLength={1000}
              placeholder="Contoh: 2 piring pecah saat paket dibuka" />
          </Card>
          <Card>
            <Text style={adminStyles.section}>Minta pengembalian dana?</Text>
            <Chips testID="cn-refund" value={wantRefund} onChange={setWantRefund} options={[{ id: "yes", label: "Ya, refund ke saldo" }, { id: "no", label: "Tidak" }]} />
            {wantRefund === "yes" ? (
              <Field testID="cn-amount" label="Nominal refund (Rp)" value={amount} onChangeText={setAmount} keyboardType="number-pad"
                placeholder={String(order.total)} hint={`Maksimal ${formatIDR(order.total)}. Jika disetujui, dana masuk ke Saldo untuk belanja berikutnya.${codUnpaid ? " Pesanan COD baru bisa direfund setelah Anda membayar kurir dan pesanan selesai." : ""}`} />
            ) : null}
          </Card>
          <Text style={adminStyles.muted}>Toko akan meninjau komplain Anda. Jika ditolak, Anda bisa meneruskannya ke Admin PGS satu kali.</Text>
          {err ? <Text style={adminStyles.err} testID="cn-error">{err}</Text> : null}
          <PrimaryButton testID="cn-submit" label="Kirim Komplain" loading={busy} onPress={submit} />
        </KeyboardAwareScrollView>
      )}
    </View>
  );
}
