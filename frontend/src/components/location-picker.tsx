import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, Linking, Platform } from "react-native";
import * as Location from "expo-location";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api } from "@/src/api";
import { MapFrame, type MapCmd } from "@/src/components/map-frame";

export type Pin = { lat: number; lng: number };
const SIDOARJO: Pin = { lat: -7.447, lng: 112.718 };

const mapHtml = (pin: Pin | null) => `<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{margin:0;height:100%;width:100%}</style></head><body><div id="m"></div><script>
function send(o){var s=JSON.stringify(o);if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(s);else parent.postMessage({__pgsmap:s},"*");}
var start=${JSON.stringify(pin)};
var map=L.map("m",{zoomControl:true}).setView(start?[start.lat,start.lng]:[${SIDOARJO.lat},${SIDOARJO.lng}],start?17:12);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
var mk=null;
function place(lat,lng,emit){if(!mk){mk=L.marker([lat,lng],{draggable:true}).addTo(map);mk.on("dragend",function(){var p=mk.getLatLng();send({type:"pick",lat:p.lat,lng:p.lng});});}else mk.setLatLng([lat,lng]);if(emit)send({type:"pick",lat:lat,lng:lng});}
if(start)place(start.lat,start.lng,false);
map.on("click",function(e){place(e.latlng.lat,e.latlng.lng,true);});
window.__cmd=function(o){if(o&&o.type==="set"){place(o.lat,o.lng,false);map.setView([o.lat,o.lng],17);}else if(o&&o.type==="clear"&&mk){map.removeLayer(mk);mk=null;}};
window.addEventListener("message",function(e){if(e.data&&e.data.type)window.__cmd(e.data);});
</script></body></html>`;

type Props = { value: Pin | null; onChange: (p: Pin) => void; label?: string; required?: boolean; testID?: string };

/** Pin lokasi di peta OpenStreetMap: ketuk/geser pin, cari tempat, atau pakai lokasi saat ini. */
export function LocationPicker({ value, onChange, label = "Pin lokasi di peta", required, testID = "loc" }: Props) {
  const html = useMemo(() => mapHtml(value), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [cmd, setCmd] = useState<MapCmd>(null);
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ label: string; lat: number; lng: number }[]>([]);
  const [searching, setSearching] = useState(false);
  const [place, setPlace] = useState("");
  const [gps, setGps] = useState<"idle" | "busy" | "blocked">("idle");
  const [msg, setMsg] = useState("");
  const seq = useRef(0);

  const moveTo = (p: Pin) => { seq.current += 1; setCmd({ type: "set", ...p, seq: seq.current }); onChange(p); };

  // search only when the user submits (OpenStreetMap search policy: no search-as-you-type)
  const search = () => {
    if (q.trim().length < 3) { setMsg("Ketik minimal 3 huruf lalu tekan Cari"); return; }
    setMsg("");
    setSearching(true);
    api.geoSearch(q.trim()).then((r) => { setRes(r); if (!r.length) setMsg("Tempat tidak ditemukan, coba kata lain"); })
      .catch((e) => { setRes([]); setMsg(e.message); }).finally(() => setSearching(false));
  };
  // pin removed from outside (e.g. "Hapus pin"): remove the marker too
  const had = useRef(!!value);
  useEffect(() => {
    if (had.current && !value) { seq.current += 1; setCmd({ type: "clear", seq: seq.current }); }
    had.current = !!value;
  }, [value]);

  useEffect(() => {
    if (!value) { setPlace(""); return; }
    const t = setTimeout(() => api.geoReverse(value.lat, value.lng).then((r) => setPlace(r.label)).catch(() => setPlace("")), 600);
    return () => clearTimeout(t);
  }, [value?.lat, value?.lng]); // eslint-disable-line react-hooks/exhaustive-deps

  const useCurrent = async () => {
    setMsg("");
    setGps("busy");
    try {
      let p = await Location.getForegroundPermissionsAsync();
      if (!p.granted && (p.canAskAgain || Platform.OS === "web")) p = await Location.requestForegroundPermissionsAsync();
      if (!p.granted) {
        setGps(p.canAskAgain && Platform.OS !== "web" ? "idle" : "blocked");
        setMsg("Izin lokasi ditolak. Anda tetap bisa memasang pin dengan mengetuk peta.");
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      moveTo({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      setGps("idle");
    } catch {
      setGps("idle");
      setMsg("Lokasi saat ini tidak terbaca. Coba lagi atau ketuk peta.");
    }
  };

  return (
    <View style={{ gap: spacing.sm }} testID={testID}>
      <Text style={styles.label}>{label}{required ? " *" : ""}</Text>
      <View style={styles.search}>
        <Icon name="search" size={16} color={colors.muted} />
        <TextInput testID={`${testID}-search`} value={q} onChangeText={setQ} placeholder="Cari jalan, gedung, atau kelurahan…"
          placeholderTextColor={colors.muted} style={styles.input} returnKeyType="search" onSubmitEditing={search} />
        {searching ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
          <Pressable testID={`${testID}-search-btn`} onPress={search} hitSlop={8} style={styles.searchBtn}>
            <Text style={styles.gpsText}>Cari</Text>
          </Pressable>
        )}
      </View>
      {res.map((r, i) => (
        <Pressable key={`${r.lat},${r.lng},${i}`} testID={`${testID}-result-${i}`} style={styles.result}
          onPress={() => { moveTo({ lat: r.lat, lng: r.lng }); setQ(""); setRes([]); }}>
          <Icon name="location-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.resultText} numberOfLines={2}>{r.label}</Text>
        </Pressable>
      ))}
      <Pressable testID={`${testID}-gps`} style={styles.gpsBtn} onPress={useCurrent} disabled={gps === "busy"}>
        {gps === "busy" ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="locate" size={16} color={colors.brandPrimary} />}
        <Text style={styles.gpsText}>Gunakan lokasi saat ini</Text>
      </Pressable>
      {gps === "blocked" && Platform.OS !== "web" ? (
        <Pressable testID={`${testID}-settings`} style={styles.gpsBtn} onPress={() => Linking.openSettings()}>
          <Icon name="settings-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.gpsText}>Buka Pengaturan untuk izin lokasi</Text>
        </Pressable>
      ) : null}
      {msg ? <Text style={styles.hint}>{msg}</Text> : null}
      <MapFrame html={html} cmd={cmd} testID={`${testID}-map`} style={styles.map}
        onMessage={(d) => { try { const o = JSON.parse(d); if (o.type === "pick") onChange({ lat: o.lat, lng: o.lng }); } catch {} }} />
      {value ? (
        <View style={styles.status} testID={`${testID}-set`}>
          <Icon name="checkmark-circle" size={16} color={colors.success} />
          <Text style={styles.statusText} numberOfLines={3}>{place || "Pin terpasang"} ({value.lat.toFixed(5)}, {value.lng.toFixed(5)})</Text>
        </View>
      ) : (
        <Text style={[styles.hint, required && { color: colors.error }]} testID={`${testID}-unset`}>
          Ketuk peta untuk memasang pin, lalu geser bila perlu.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, color: colors.onSurfaceSecondary, fontWeight: "500" },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, minHeight: 44, backgroundColor: colors.surface },
  searchBtn: { minHeight: 44, justifyContent: "center", paddingHorizontal: 4 },
  input: { flex: 1, color: colors.onSurface, fontSize: fontSize.sm, paddingVertical: 10 },
  result: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 44, paddingVertical: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  resultText: { flex: 1, fontSize: 13, color: colors.onSurface },
  gpsBtn: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44, alignSelf: "flex-start" },
  gpsText: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  map: { height: 260, borderRadius: radius.md, overflow: "hidden", borderWidth: 1, borderColor: colors.border },
  status: { flexDirection: "row", alignItems: "flex-start", gap: 6 },
  statusText: { flex: 1, fontSize: 12, color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted },
});
