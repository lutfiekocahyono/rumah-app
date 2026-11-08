import React, { useEffect, useState } from "react";
import { View, Text, TextInput, Pressable, ActivityIndicator, StyleSheet } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";
import { colors, radius, spacing, fontSize, formatIDR } from "@/src/theme";
import { api, type Voucher } from "@/src/api";
import { co } from "./styles";

export type AppliedVoucher = { code: string; title: string; discount: number };

/** Voucher input + claimed-voucher chips. The applied voucher is owned by the checkout screen. */
export function VoucherSection({ voucher, onChange }: { voucher: AppliedVoucher | null; onChange: (v: AppliedVoucher | null) => void }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState<Voucher[]>([]);
  useEffect(() => { api.myVouchers().then(setMine).catch(() => {}); }, []);

  const apply = async (code: string) => {
    if (!code.trim()) return;
    setBusy(true);
    setErr("");
    try {
      onChange(await api.applyVoucher(code.trim()));
      setText(code.trim().toUpperCase());
    } catch (e: any) {
      onChange(null);
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Text style={[co.section, co.sectionGap]}>Voucher Diskon</Text>
      <View style={co.card} testID="checkout-voucher">
        <View style={styles.row}>
          <TextInput
            testID="co-voucher-input"
            value={text}
            onChangeText={(t) => { setText(t.toUpperCase()); if (voucher) onChange(null); setErr(""); }}
            placeholder="Masukkan kode voucher"
            placeholderTextColor={colors.muted}
            autoCapitalize="characters"
            style={[co.input, { flex: 1 }]}
          />
          {voucher ? (
            <Pressable testID="co-voucher-remove" style={styles.btnOutline} onPress={() => { onChange(null); setText(""); }}>
              <Text style={styles.btnOutlineText}>Hapus</Text>
            </Pressable>
          ) : (
            <Pressable testID="co-voucher-apply" style={styles.btn} onPress={() => apply(text)} disabled={busy}>
              {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={co.payBtnText}>Pakai</Text>}
            </Pressable>
          )}
        </View>
        {voucher ? <Text style={styles.ok} testID="co-voucher-ok">{voucher.title} · hemat {formatIDR(voucher.discount)}</Text> : null}
        {err ? <Text style={co.err} testID="co-voucher-error">{err}</Text> : null}
        {mine.length && !voucher ? (
          <View style={styles.mine}>
            <Text style={co.paySub}>Voucher yang sudah kamu klaim:</Text>
            <View style={co.chipRow}>
              {mine.map((v) => (
                <Pressable key={v.code} testID={`co-my-voucher-${v.code}`} style={co.vChip} onPress={() => apply(v.code)}>
                  <Icon name="ticket-outline" size={14} color={colors.brandPrimary} />
                  <Text style={co.vChipText}>{v.code}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  btn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center", alignItems: "center", minWidth: 80 },
  btnOutline: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center" },
  btnOutlineText: { color: colors.brandPrimary, fontWeight: "500" },
  ok: { color: colors.success, fontSize: fontSize.sm, marginTop: spacing.sm },
  mine: { marginTop: spacing.md, gap: spacing.sm },
});
