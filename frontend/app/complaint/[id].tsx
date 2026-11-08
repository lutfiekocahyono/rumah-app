import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, Pressable } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type Complaint } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Chips, Field, PrimaryButton, digits } from "@/src/components/admin-form";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { fmtDate } from "@/src/utils/date";
import { StatusPill } from "@/src/components/complaint-pill";

type Action = "refund" | "reject" | "resolve";

export default function ComplaintDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [c, setC] = useState<Complaint | null>(null);
  const [reply, setReply] = useState("");
  const [action, setAction] = useState<Action>("refund");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [escalateText, setEscalateText] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const d = await api.complaint(id);
      setC(d);
      setAmount((a) => a || String(Math.min(d.refund_amount || d.refundable, d.refundable)));
    } catch (e: any) { setErr(e.message); }
  }, [id]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const run = async (key: string, fn: () => Promise<Complaint>) => {
    setBusy(key);
    setErr("");
    try { setC(await fn()); return true; } catch (e: any) { setErr(e.message); return false; } finally { setBusy(""); }
  };

  if (!c) {
    return (
      <View style={[adminStyles.root, { paddingTop: insets.top }]}>
        <ScreenHeader title="Komplain" />
        {err ? <Text style={[adminStyles.err, { padding: spacing.lg }]}>{err}</Text> : <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />}
      </View>
    );
  }

  const decisionText = c.decision
    ? c.decision.action === "refund" ? `Refund ${formatIDR(c.decision.amount)} ke saldo pembeli` : c.decision.action === "reject" ? `Ditolak: ${c.decision.note}` : "Dinyatakan selesai tanpa refund"
    : "";
  const orderLink = c.viewer === "buyer" ? `/order/${c.order_id}` : c.viewer === "store" ? `/seller/order/${c.order_id}` : `/admin/order/${c.order_id}`;

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="complaint-detail-screen">
      <ScreenHeader title={c.complaint_id} />
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        <Card>
          <View style={styles.between}>
            <Text style={styles.h}>{c.reason_label}</Text>
            <StatusPill status={c.status} />
          </View>
          <Pressable testID="cd-order-link" onPress={() => router.push(orderLink as any)}>
            <Text style={styles.link}>Pesanan {c.order_id} · {c.store_name}</Text>
          </Pressable>
          <Text style={adminStyles.muted}>Pembeli: {c.user_name} · {fmtDate(c.created_at)}</Text>
          <Text style={adminStyles.muted}>Total pesanan {formatIDR(c.order_total)}{c.refund_amount ? ` · minta refund ${formatIDR(c.refund_amount)}` : " · tidak minta refund"}</Text>
          {c.decision ? (
            <View style={styles.decision} testID="cd-decision">
              <Text style={styles.decisionText}>{decisionText}</Text>
              <Text style={adminStyles.muted}>oleh {c.decision.by} · {fmtDate(c.decision.at)}</Text>
              {c.decision.note && c.decision.action !== "reject" ? <Text style={adminStyles.muted}>Catatan: {c.decision.note}</Text> : null}
            </View>
          ) : null}
        </Card>

        <Text style={adminStyles.section}>Percakapan komplain</Text>
        {c.messages.map((m, i) => {
          const mine = m.by === c.viewer;
          return (
            <View key={i} style={[styles.bubble, mine ? styles.mine : styles.theirs]}>
              <Text style={[styles.who, mine && { color: colors.onBrandPrimary }]}>{m.name}{m.by === "admin" ? " (Admin PGS)" : ""}</Text>
              <Text style={[styles.msg, mine && { color: colors.onBrandPrimary }]}>{m.text}</Text>
              <Text style={[styles.time, mine && { color: colors.onBrandPrimary }]}>{fmtDate(m.at)}</Text>
            </View>
          );
        })}

        {c.can_reply ? (
          <Card>
            <Field testID="cd-reply" label="Balas" value={reply} onChangeText={setReply} multiline maxLength={1000} placeholder="Tulis balasan…" />
            <PrimaryButton testID="cd-reply-send" label="Kirim Balasan" variant="outline" loading={busy === "reply"}
              onPress={async () => { if (reply.trim() && (await run("reply", () => api.replyComplaint(c.complaint_id, reply.trim())))) setReply(""); }} />
          </Card>
        ) : null}

        {c.can_decide ? (
          <Card>
            <Text style={styles.h}>{c.viewer === "admin" ? "Keputusan Admin PGS" : "Keputusan Toko"}</Text>
            {c.refundable <= 0 ? (
              <Text style={styles.warn} testID="cd-cod-unpaid">Pesanan COD belum dibayar, jadi belum bisa direfund ke saldo. Refund tersedia setelah pesanan selesai (uang COD diterima).</Text>
            ) : null}
            <Chips testID="cd-action" value={c.refundable <= 0 && action === "refund" ? "reject" : action} onChange={setAction} options={[
              ...(c.refundable > 0 ? [{ id: "refund" as Action, label: "Setujui refund" }] : []),
              { id: "reject" as Action, label: "Tolak" }, { id: "resolve" as Action, label: "Selesai tanpa refund" },
            ]} />
            {action === "refund" && c.refundable > 0 ? (
              <Field testID="cd-amount" label="Nominal refund ke saldo pembeli (Rp)" value={amount} onChangeText={setAmount} keyboardType="number-pad"
                hint={`Maksimal ${formatIDR(c.refundable)}${c.cod_unpaid ? " (bagian yang dibayar dengan saldo; sisa COD belum dibayar)" : ""}`} />
            ) : null}
            <Field testID="cd-note" label={action === "reject" ? "Alasan penolakan (wajib)" : "Catatan (opsional)"} value={note} onChangeText={setNote} multiline maxLength={500} />
            <PrimaryButton testID="cd-decide" label="Simpan Keputusan" variant={action === "reject" ? "danger" : "solid"} onPress={() => {
              if (action === "reject" && !note.trim()) return setErr("Tulis alasan penolakan");
              if (action === "refund" && !(digits(amount) > 0 && digits(amount) <= c.refundable)) return setErr(`Nominal refund 1 – ${formatIDR(c.refundable)}`);
              setErr("");
              setConfirm(true);
            }} />
          </Card>
        ) : null}

        {c.can_escalate ? (
          <Card>
            <Text style={styles.h}>Tidak setuju dengan keputusan toko?</Text>
            <Text style={adminStyles.muted}>Teruskan ke Admin PGS untuk ditinjau ulang (hanya satu kali).</Text>
            <Field testID="cd-escalate-text" label="Alasan" value={escalateText} onChangeText={setEscalateText} multiline maxLength={1000} />
            <PrimaryButton testID="cd-escalate" label="Teruskan ke Admin PGS" loading={busy === "escalate"}
              onPress={() => { if (!escalateText.trim()) return setErr("Tulis alasan Anda"); void run("escalate", () => api.escalateComplaint(c.complaint_id, escalateText.trim())); }} />
          </Card>
        ) : null}

        {c.viewer === "buyer" && c.status === "refunded" ? (
          <PrimaryButton testID="cd-wallet" label="Lihat Saldo Saya" variant="outline" onPress={() => router.push("/wallet" as any)} />
        ) : null}
        {err ? <Text style={adminStyles.err} testID="cd-error">{err}</Text> : null}
      </KeyboardAwareScrollView>
      <ConfirmDialog
        visible={confirm}
        title={action === "refund" ? `Refund ${formatIDR(digits(amount))}?` : action === "reject" ? "Tolak komplain?" : "Tutup komplain tanpa refund?"}
        message={action === "refund" ? "Dana langsung masuk ke saldo pembeli dan tidak bisa dibatalkan." : "Pembeli akan mendapat notifikasi."}
        confirmLabel="Ya, simpan"
        loading={busy === "decide"}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => { await run("decide", () => api.decideComplaint(c.complaint_id, action, action === "refund" ? digits(amount) : 0, note.trim())); setConfirm(false); }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  between: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, flexShrink: 1 },
  warn: { fontSize: 13, color: colors.warning, fontWeight: "500" },
  link: { fontSize: fontSize.sm, color: colors.brandPrimary, fontWeight: "500" },
  decision: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, padding: spacing.sm, gap: 2 },
  decisionText: { fontSize: fontSize.sm, color: colors.onSurface, fontWeight: "600" },
  bubble: { maxWidth: "85%", borderRadius: radius.md, padding: spacing.sm, gap: 2 },
  mine: { alignSelf: "flex-end", backgroundColor: colors.brandPrimary },
  theirs: { alignSelf: "flex-start", backgroundColor: colors.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  who: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceSecondary },
  msg: { fontSize: fontSize.sm, color: colors.onSurface },
  time: { fontSize: 10, color: colors.muted, alignSelf: "flex-end", opacity: 0.8 },
});
