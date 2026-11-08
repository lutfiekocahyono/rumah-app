import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";
import { colors, formatIDR } from "@/src/theme";
import type { PaymentMethod } from "@/src/api";
import { co } from "./styles";

export type PayAvail = { midtrans: boolean; xendit: boolean; midtrans_sandbox: boolean };

/** Saldo toggle (only when the buyer has balance). */
export function BalanceSection({ balance, useBalance, toPay, onToggle }: { balance: number; useBalance: boolean; toPay: number; onToggle: () => void }) {
  if (balance <= 0) return null;
  return (
    <>
      <Text style={[co.section, co.sectionGap]}>Saldo</Text>
      <Pressable testID="co-use-balance" style={[co.card, co.payRow]} onPress={onToggle}>
        <Icon name={useBalance ? "checkbox" : "square-outline"} size={22} color={useBalance ? colors.brandPrimary : colors.muted} />
        <View style={{ flex: 1 }}>
          <Text style={co.payLabel}>Pakai saldo {formatIDR(balance)}</Text>
          <Text style={co.paySub}>{useBalance ? (toPay === 0 ? "Pesanan lunas dengan saldo" : `Sisa ${formatIDR(toPay)} dibayar dengan metode di bawah`) : "Dari refund komplain yang disetujui"}</Text>
        </View>
      </Pressable>
    </>
  );
}

/** Payment options. Rule: COD only for "Ambil di toko"; courier delivery must be paid online. */
export function PaymentSection({ isPickup, payAvail, method, onPick }: { isPickup: boolean; payAvail: PayAvail; method: PaymentMethod; onPick: (m: PaymentMethod) => void }) {
  const options = ([
    { id: "cod", label: "COD (Bayar di Tempat)", sub: "Bayar tunai saat ambil pesanan di toko", icon: "cash-outline" },
    { id: "midtrans", label: `Bayar Online (Midtrans)${payAvail.midtrans_sandbox ? " · Sandbox" : ""}`, sub: "QRIS · Transfer Bank (VA) · GoPay · ShopeePay", icon: "qr-code-outline" },
    { id: "xendit", label: "Xendit", sub: "QRIS · Transfer Bank (VA) · OVO · DANA · ShopeePay", icon: "wallet-outline" },
  ] as const).filter((m) => (m.id === "cod" ? isPickup : payAvail[m.id]));
  return (
    <>
      <Text style={[co.section, co.sectionGap]}>Metode Pembayaran</Text>
      <View style={co.card}>
        {!isPickup && !payAvail.midtrans && !payAvail.xendit ? (
          <Text style={[co.paySub, { color: colors.error }]} testID="co-online-required">
            Pengiriman kurir wajib bayar online, yang saat ini belum tersedia. Pilih &quot;Ambil di toko&quot; untuk bayar COD.
          </Text>
        ) : null}
        {isPickup ? <Text style={co.paySub}>COD (bayar tunai) hanya untuk Ambil di toko. Pesanan batal otomatis bila toko belum memprosesnya dalam 2×24 jam.</Text> : null}
        {options.map((m) => (
          <Pressable key={m.id} testID={`pay-${m.id}`} style={co.payRow} onPress={() => onPick(m.id)}>
            <Icon name={m.icon as any} size={20} color={colors.onSurface} />
            <View style={{ flex: 1 }}>
              <Text style={co.payLabel}>{m.label}</Text>
              <Text style={co.paySub}>{m.sub}</Text>
            </View>
            <View style={[styles.radio, method === m.id && styles.radioActive]}>
              {method === m.id ? <View style={styles.radioDot} /> : null}
            </View>
          </Pressable>
        ))}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },
});
