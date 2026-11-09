import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator } from "react-native";

import { colors, fontSize, spacing } from "@/src/theme";
import { api, type FlashSchedule } from "@/src/api";
import { DateTimeField } from "@/src/components/datetime-field";
import { adminStyles, Card, PrimaryButton, ToggleRow } from "@/src/components/admin-form";

const STATUS: Record<FlashSchedule["status"], { label: string; color: string }> = {
  running: { label: "Sedang berjalan", color: colors.success },
  upcoming: { label: "Belum mulai", color: colors.warning },
  ended: { label: "Sudah berakhir", color: colors.muted },
  off: { label: "Flash Sale dimatikan Super Admin", color: colors.muted },
};

function Row({ s, onSaved }: { s: FlashSchedule; onSaved: (s: FlashSchedule) => void }) {
  const [follow, setFollow] = useState(s.follows_sidoarjo);
  const [start, setStart] = useState<string | null>(s.starts_at);
  const [end, setEnd] = useState<string | null>(s.ends_at);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const branch = s.store_id !== "pgs-official";
  const st = STATUS[s.status];

  const save = async () => {
    if (!follow && !end) return setMsg({ ok: false, text: "Isi waktu selesai" });
    if (!follow && start && end && new Date(end) <= new Date(start)) return setMsg({ ok: false, text: "Waktu selesai harus setelah waktu mulai" });
    setBusy(true); setMsg(null);
    try {
      const r = await api.saveFlashSchedule(s.store_id, { follow, starts_at: follow ? null : start, ends_at: follow ? null : end });
      onSaved(r); setStart(r.starts_at); setEnd(r.ends_at);
      setMsg({ ok: true, text: "Jadwal disimpan" });
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  };

  return (
    <Card>
      <View style={styles.head}>
        <Text style={styles.h}>{s.name}</Text>
        <Text style={[styles.status, { color: st.color }]} testID={`fs-status-${s.store_id}`}>{st.label}</Text>
      </View>
      {branch ? <ToggleRow testID={`fs-follow-${s.store_id}`} label="Ikut jadwal PGS Sidoarjo" value={follow} onChange={(v) => { setFollow(v); setMsg(null); }} /> : null}
      {follow ? <Text style={adminStyles.muted}>Mulai & selesai sama dengan jadwal PGS Sidoarjo.</Text> : (
        <>
          <Text style={adminStyles.section}>Mulai (kosongkan = langsung mulai)</Text>
          <DateTimeField testID={`fs-start-${s.store_id}`} value={start} allowEmpty onChange={setStart} />
          <Text style={adminStyles.section}>Selesai</Text>
          <DateTimeField testID={`fs-end-${s.store_id}`} value={end} onChange={setEnd} />
        </>
      )}
      {msg ? <Text style={msg.ok ? adminStyles.ok : adminStyles.err} testID={`fs-msg-${s.store_id}`}>{msg.text}</Text> : null}
      <PrimaryButton testID={`fs-save-${s.store_id}`} label="Simpan jadwal" variant="outline" loading={busy} onPress={save} />
    </Card>
  );
}

/** Jadwal Flash Sale per cabang: admin cabang melihat tokonya sendiri, Super Admin semua cabang. Hitung mundur pembeli ikut jadwal cabangnya. */
export function FlashScheduleList() {
  const [list, setList] = useState<FlashSchedule[] | null>(null);
  const [err, setErr] = useState("");
  const load = () => api.flashSchedules().then(setList).catch((e) => setErr(e.message));
  useEffect(() => { void load(); }, []);
  if (err) return <Text style={adminStyles.err} testID="fs-error">{err}</Text>;
  if (!list) return <ActivityIndicator color={colors.brandPrimary} />;
  return (
    <View style={{ gap: spacing.md }} testID="flash-schedules">
      {list.map((s) => <Row key={s.store_id} s={s} onSaved={() => void load()} />)}
    </View>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  h: { fontSize: fontSize.base, fontWeight: "600", color: colors.onSurface, flexShrink: 1 },
  status: { fontSize: fontSize.sm, fontWeight: "600" },
});
