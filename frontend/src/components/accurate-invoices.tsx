import React, { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, TextInput } from "react-native";

import { colors, formatIDR, spacing } from "@/src/theme";
import { api, type AccurateInvoice, type AccurateOrderRow } from "@/src/api";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { fmtDate } from "@/src/utils/date";
import { styles } from "@/src/components/accurate-sync";

const STATE: Record<string, { text: string; color: string }> = {
  none: { text: "Belum dikirim", color: colors.muted }, sending: { text: "Sedang dikirim", color: colors.warning },
  failed: { text: "Gagal, bisa dikirim ulang", color: colors.error }, sent: { text: "Terkirim", color: colors.success },
};

/** Tahap 2B — kirim pesanan online sebagai faktur penjualan ke Accurate, satu per satu setelah konfirmasi. */
export function AccurateInvoices({ connected, customerNo, shippingItemNo }: { connected: boolean; customerNo: string; shippingItemNo: string }) {
  const [cust, setCust] = useState(customerNo);
  const [ship, setShip] = useState(shippingItemNo);
  const [saved, setSaved] = useState(customerNo);
  const [tab, setTab] = useState<"todo" | "sent">("todo");
  const [list, setList] = useState<{ total: number; page: number; items: AccurateOrderRow[] } | null>(null);
  const [inv, setInv] = useState<AccurateInvoice | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [ask, setAsk] = useState(false);

  useEffect(() => { setCust(customerNo); setSaved(customerNo); setShip(shippingItemNo); }, [customerNo, shippingItemNo]);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setMsg(null);
    try { await fn(); } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(""); }
  };
  const load = useCallback((page = 1) => run("list", async () => { setList(await api.accurateOrders(tab === "sent", page)); }), [tab]);
  useEffect(() => { if (connected) load(1); }, [connected, load]);

  const saveSettings = () => run("set", async () => {
    const r = await api.accurateInvoiceSettings(cust, ship);
    setSaved(r.customer_no);
    setMsg({ ok: true, text: "Pengaturan faktur tersimpan" });
  });
  const open = (id: string) => run(`open-${id}`, async () => { setInv(await api.accurateInvoice(id)); });
  const send = () => {
    if (!inv) return;
    setAsk(false);
    run("send", async () => {
      try {
        const r = await api.accurateSendInvoice(inv.order_id);
        setInv(r);
        setMsg({ ok: true, text: `Faktur ${r.accurate_invoice.number} masuk ke Accurate` });
      } finally {
        api.accurateOrders(tab === "sent", list?.page ?? 1).then(setList).catch(() => {});  // refresh without clearing the message
      }
    });
  };

  return (
    <View style={[styles.card, !connected && { opacity: 0.6 }]} testID="accurate-invoices">
      <Text style={styles.h}>5. Faktur Penjualan ke Accurate</Text>
      <Text style={styles.small}>Pesanan yang sudah dibayar (COD setelah selesai) bisa dikirim sebagai faktur penjualan. Setiap faktur hanya dikirim setelah Anda menekan konfirmasi. Nomor faktur = nomor pesanan, jadi tidak bisa terkirim dua kali.</Text>
      <Text style={styles.label}>Kode Pelanggan Accurate</Text>
      <TextInput testID="accurate-customer-no" value={cust} onChangeText={setCust} autoCapitalize="characters" placeholder="mis. C.00001 (Pelanggan Umum Online)"
        placeholderTextColor={colors.muted} style={styles.input} />
      <Text style={styles.label}>Kode Barang Ongkir (opsional)</Text>
      <TextInput testID="accurate-shipping-item" value={ship} onChangeText={setShip} autoCapitalize="characters" placeholder="Barang jasa untuk ongkos kirim, mis. ONGKIR"
        placeholderTextColor={colors.muted} style={styles.input} />
      <Pressable testID="accurate-invoice-settings-save" style={styles.outline} onPress={saveSettings} disabled={!!busy || !cust.trim()}>
        {busy === "set" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Simpan Pengaturan Faktur</Text>}
      </Pressable>

      <View style={styles.pills}>
        {([["todo", "Belum dikirim"], ["sent", "Sudah dikirim"]] as const).map(([k, label]) => (
          <Pressable key={k} testID={`accurate-orders-tab-${k}`} style={[styles.pill, tab === k && styles.pillOn]} onPress={() => { setTab(k); setInv(null); }}>
            <Text style={{ fontSize: 13, color: tab === k ? colors.onBrandPrimary : colors.onSurface }}>{label}</Text>
          </Pressable>
        ))}
      </View>
      {busy === "list" && !list ? <ActivityIndicator color={colors.brandPrimary} /> : null}
      {list ? (
        <View testID="accurate-orders">
          <Text style={styles.small}>{list.total} pesanan</Text>
          {list.items.map((o) => {
            const st = STATE[o.accurate_invoice.status] ?? STATE.none;
            return (
              <Pressable key={o.order_id} style={styles.item} onPress={() => open(o.order_id)} testID={`accurate-order-${o.order_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>{o.order_id} · {formatIDR(o.total)}</Text>
                  <Text style={styles.small} numberOfLines={1}>{o.store_name} · {o.buyer || "Pembeli"} · {fmtDate(o.created_at)}</Text>
                  <Text style={[styles.small, { color: st.color }]}>{st.text}{o.accurate_invoice.number ? ` · ${o.accurate_invoice.number}` : ""}</Text>
                </View>
                {busy === `open-${o.order_id}` ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.link}>Pratinjau</Text>}
              </Pressable>
            );
          })}
          <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
            <Pressable testID="accurate-orders-prev" style={styles.outline} disabled={list.page <= 1 || !!busy} onPress={() => load(list.page - 1)}><Text style={styles.outlineText}>‹</Text></Pressable>
            <Pressable testID="accurate-orders-next" style={styles.outline} disabled={list.page * 20 >= list.total || !!busy} onPress={() => load(list.page + 1)}><Text style={styles.outlineText}>›</Text></Pressable>
          </View>
        </View>
      ) : null}

      {inv ? (
        <View style={{ gap: 4, paddingTop: spacing.sm }} testID="accurate-invoice-preview">
          <Text style={styles.h}>Faktur {inv.number}</Text>
          <Text style={styles.small}>Tanggal {inv.date} · Pelanggan {inv.customer_no || "–"} · {inv.store_name}</Text>
          {inv.lines.map((l, n) => (
            <Text key={n} style={styles.small}>{l.quantity} × {l.item_no || "(tanpa SKU)"} {l.name} @ {formatIDR(l.unit_price)}{l.warehouse ? ` · gudang ${l.warehouse}` : ""}</Text>
          ))}
          {inv.discount ? <Text style={styles.small}>Diskon: −{formatIDR(inv.discount)}</Text> : null}
          <Text style={styles.label}>Total faktur {formatIDR(inv.total)} (pesanan {formatIDR(inv.order_total)})</Text>
          {inv.notes.map((t) => <Text key={t} style={[styles.small, { color: colors.warning }]}>{t}</Text>)}
          {inv.problems.map((t) => <Text key={t} style={[styles.small, { color: colors.error }]} testID="accurate-invoice-problem">• {t}</Text>)}
          {inv.accurate_invoice.status === "failed" && inv.accurate_invoice.error ? <Text style={[styles.small, { color: colors.error }]}>Gagal sebelumnya: {inv.accurate_invoice.error}</Text> : null}
          {inv.accurate_invoice.status === "sent" ? (
            <Text style={[styles.small, { color: colors.success }]} testID="accurate-invoice-sent">Sudah di Accurate · {inv.accurate_invoice.number}{inv.accurate_invoice.at ? ` · ${fmtDate(inv.accurate_invoice.at)}` : ""}</Text>
          ) : (
            <Pressable testID="accurate-invoice-send" style={[styles.primary, (inv.problems.length || !saved) && { opacity: 0.5 }]} onPress={() => setAsk(true)}
              disabled={!!busy || !!inv.problems.length || inv.accurate_invoice.status === "sending"}>
              {busy === "send" ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Kirim Faktur ke Accurate</Text>}
            </Pressable>
          )}
        </View>
      ) : null}
      {msg ? <Text style={[styles.small, { color: msg.ok ? colors.success : colors.error }]} testID={`accurate-invoice-msg-${msg.ok ? "ok" : "error"}`}>{msg.text}</Text> : null}
      <ConfirmDialog visible={ask} title="Kirim faktur ke Accurate?" danger={false} confirmLabel="Ya, kirim"
        message={inv ? `Faktur penjualan ${inv.number} senilai ${formatIDR(inv.total)} akan dibuat di Accurate dan mengurangi stok gudang di sana. Tindakan ini tidak bisa dibatalkan dari aplikasi.` : ""}
        onConfirm={send} onCancel={() => setAsk(false)} />
    </View>
  );
}
