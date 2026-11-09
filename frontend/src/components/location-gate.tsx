import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, AppState, Linking, Platform, ActivityIndicator, Modal, ScrollView } from "react-native";
import * as Location from "expo-location";
import { usePathname, useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";

type Perm = "checking" | "granted" | "denied" | "blocked" | "off";
const OPEN = [/^\/login/, /^\/register/, /^\/forgot-password/]; // owner must always be able to sign in
const SEND_EVERY = 2 * 60 * 1000;
const MOVED_M = 200;

const meters = (a: Location.LocationObjectCoords, b: Location.LocationObjectCoords) => {
  const r = Math.PI / 180, dLat = (b.latitude - a.latitude) * r, dLng = (b.longitude - a.longitude) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * r) * Math.cos(b.latitude * r) * Math.sin(dLng / 2) ** 2;
  return 12742000 * Math.asin(Math.sqrt(h));
};

/** Pelanggan & tamu: izin lokasi diminta langsung; tanpa izin aplikasi dikunci. Super Admin, admin cabang & halaman masuk tidak dikunci. */
export function LocationGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const path = usePathname();
  const exempt = user?.role === "admin" || user?.role === "store_admin";
  const [perm, setPerm] = useState<Perm>("checking");
  const [asking, setAsking] = useState(false);

  const check = useCallback(async (request: boolean) => {
    try {
      let p = await Location.getForegroundPermissionsAsync();
      if (!p.granted && request && (p.canAskAgain || Platform.OS === "web")) {
        setAsking(true);
        p = await Location.requestForegroundPermissionsAsync();
      }
      if (!p.granted) return setPerm(p.canAskAgain && Platform.OS !== "web" ? "denied" : "blocked");
      if (Platform.OS !== "web" && !(await Location.hasServicesEnabledAsync())) return setPerm("off");
      setPerm("granted");
    } catch { setPerm("blocked"); } finally { setAsking(false); }
  }, []);

  useEffect(() => { if (!loading && !exempt) void check(true); }, [loading, exempt, check]);
  useEffect(() => { // back from Settings
    if (exempt) return;
    const sub = AppState.addEventListener("change", (st) => { if (st === "active") void check(false); });
    return () => sub.remove();
  }, [exempt, check]);

  // real-time position while the app is open, sent at most every 2 minutes unless the buyer moved
  const last = useRef<{ at: number; c: Location.LocationObjectCoords } | null>(null);
  useEffect(() => {
    if (exempt || perm !== "granted") return;
    last.current = null;
    let sub: Location.LocationSubscription | null = null;
    let stop = false;
    const send = (c: Location.LocationObjectCoords) => {
      const l = last.current;
      if (l && Date.now() - l.at < SEND_EVERY && meters(l.c, c) < MOVED_M) return;
      last.current = { at: Date.now(), c };
      api.saveLocation(c.latitude, c.longitude, c.accuracy ?? null, Platform.OS).catch(() => { last.current = null; });
    };
    Location.watchPositionAsync({ accuracy: Location.Accuracy.Balanced, timeInterval: 60000, distanceInterval: 50 }, (pos) => send(pos.coords))
      .then((s) => { if (stop) s.remove(); else sub = s; })
      .catch(() => {});
    return () => { stop = true; sub?.remove(); };
  }, [exempt, perm, user?.user_id]);

  const locked = !loading && !exempt && (perm === "denied" || perm === "blocked" || perm === "off") && !OPEN.some((r) => r.test(path));
  return (
    <View style={{ flex: 1 }}>
      {children}
      {locked ? <LockScreen perm={perm} asking={asking} onAllow={() => check(true)} /> : null}
    </View>
  );
}

function LockScreen({ perm, asking, onAllow }: { perm: Perm; asking: boolean; onAllow: () => void }) {
  const router = useRouter();
  const web = Platform.OS === "web";
  const settings = perm === "blocked" && !web;
  return (
    <Modal visible transparent animationType="fade" statusBarTranslucent onRequestClose={() => {}}>
    <View style={styles.backdrop} testID="location-lock">
    <ScrollView style={styles.card} contentContainerStyle={styles.cardInner} testID="location-popup">
      <View style={styles.icon}><Icon name="location" size={36} color={colors.brandPrimary} /></View>
      <Text style={styles.title}>Izinkan akses lokasi</Text>
      <Text style={styles.body}>
        {perm === "off" ? "Layanan lokasi (GPS) di HP Anda mati. Nyalakan GPS untuk memakai aplikasi Pusat Grosir Sidoarjo."
          : "Aplikasi Pusat Grosir Sidoarjo membutuhkan lokasi Anda untuk dipakai. Lokasi dipakai untuk layanan cabang & ongkir terdekat."}
      </Text>
      {perm === "blocked" ? (
        <View style={styles.steps} testID="location-help">
          {web ? (
            <>
              <Text style={styles.step}>1. Ketuk ikon gembok / ⓘ di sebelah alamat situs pada browser.</Text>
              <Text style={styles.step}>2. Pilih Izin situs → Lokasi → Izinkan.</Text>
              <Text style={styles.step}>3. Muat ulang halaman, lalu ketuk “Izinkan lokasi”.</Text>
            </>
          ) : (
            <>
              <Text style={styles.step}>1. Ketuk “Buka Pengaturan”.</Text>
              <Text style={styles.step}>2. Pilih Lokasi / Izin → Lokasi → “Saat aplikasi digunakan”.</Text>
              <Text style={styles.step}>3. Kembali ke aplikasi, kunci terbuka otomatis.</Text>
            </>
          )}
        </View>
      ) : null}
      <Pressable testID="location-allow" style={styles.btn} onPress={onAllow} disabled={asking}>
        {asking ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.btnText}>Izinkan lokasi</Text>}
      </Pressable>
      {settings || perm === "off" ? (
        <Pressable testID="location-settings" style={styles.outline} onPress={() => (perm === "off" && Platform.OS === "android"
          ? Linking.sendIntent("android.settings.LOCATION_SOURCE_SETTINGS").catch(() => Linking.openSettings()) : Linking.openSettings())}>
          <Text style={styles.outlineText}>Buka Pengaturan</Text>
        </Pressable>
      ) : null}
      <Pressable testID="location-login" style={styles.link} onPress={() => router.push("/login" as any)}>
        <Text style={styles.linkText}>Admin / pemilik toko? Masuk di sini</Text>
      </Pressable>
    </ScrollView>
    </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  card: { flexGrow: 0, width: "100%", maxWidth: 420, maxHeight: "90%", backgroundColor: colors.surface, borderRadius: radius.lg },
  cardInner: { alignItems: "center", padding: spacing.lg, gap: spacing.md },
  icon: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: fontSize.lg, fontWeight: "700", color: colors.onSurface, textAlign: "center" },
  body: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 20 },
  steps: { width: "100%", gap: 6, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md },
  step: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  btn: { width: "100%", minHeight: 50, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  btnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: fontSize.base },
  outline: { width: "100%", minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  outlineText: { color: colors.brandPrimary, fontWeight: "600" },
  link: { minHeight: 44, justifyContent: "center" },
  linkText: { color: colors.muted, fontSize: fontSize.sm, textDecorationLine: "underline" },
});
