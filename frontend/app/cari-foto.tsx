import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, Dimensions, Linking, Platform } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Product } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { ProductCard } from "@/src/components/product-card";
import { useStore } from "@/src/store-context";

const { width: screenW } = Dimensions.get("window");
const GAP = spacing.md;
const CARD_W = (Math.min(screenW, 720) - spacing.lg * 2 - GAP) / 2;
type Hit = Product & { similarity: number };

/** Cari dengan Foto: buyer takes / picks a photo, we show the 20 most similar products for the chosen branch. */
export default function PhotoSearch() {
  const insets = useSafeAreaInsets();
  const { store } = useStore();
  const [photo, setPhoto] = useState("");
  const [items, setItems] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [blocked, setBlocked] = useState(false); // camera permission permanently denied

  const search = async (a: ImagePicker.ImagePickerAsset) => {
    setPhoto(a.uri); setBusy(true); setErr(""); setItems(null);
    try {
      const r = await api.imageSearch({ uri: a.uri, name: a.fileName ?? "foto.jpg", mimeType: a.mimeType ?? "image/jpeg" });
      setItems(r.items);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const camera = async () => {
    setBlocked(false);
    if (Platform.OS !== "web") {
      let perm = await ImagePicker.getCameraPermissionsAsync();
      if (!perm.granted && perm.canAskAgain) perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) { setBlocked(!perm.canAskAgain); setErr("Izin kamera dibutuhkan untuk memotret barang. Anda juga bisa memilih foto dari galeri."); return; }
    }
    try {
      const r = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.8, allowsEditing: true });
      if (!r.canceled && r.assets[0]) void search(r.assets[0]);
    } catch { setErr("Kamera tidak bisa dibuka. Coba pilih foto dari galeri."); }
  };

  const gallery = async () => {
    setBlocked(false);
    try {
      const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8, allowsEditing: true });
      if (!r.canceled && r.assets[0]) void search(r.assets[0]);
    } catch { setErr("File tidak bisa dibuka. Pilih foto JPG atau PNG."); }
  };

  const header = (
    <View style={{ gap: spacing.md, paddingHorizontal: spacing.lg, paddingTop: spacing.md }}>
      <View style={styles.hero}>
        {photo ? <Image source={photo} style={styles.preview} contentFit="cover" testID="ps-preview" />
          : <Icon name="camera-outline" size={36} color={colors.brandPrimary} />}
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={styles.h}>Cari barang dengan foto</Text>
          <Text style={styles.muted}>Foto satu barang dari dekat dengan latar polos, lalu potong agar barangnya memenuhi foto. Harga & stok mengikuti {store?.name ?? "cabang Anda"}.</Text>
        </View>
      </View>
      <View style={styles.row}>
        <Pressable testID="ps-camera" style={[styles.btn, styles.btnPrimary]} onPress={camera} disabled={busy}>
          <Icon name="camera" size={18} color={colors.onBrandPrimary} /><Text style={[styles.btnText, { color: colors.onBrandPrimary }]}>Ambil Foto</Text>
        </Pressable>
        <Pressable testID="ps-gallery" style={styles.btn} onPress={gallery} disabled={busy}>
          <Icon name="images-outline" size={18} color={colors.brandPrimary} /><Text style={styles.btnText}>Pilih dari Galeri</Text>
        </Pressable>
      </View>
      {err ? <Text style={styles.err} testID="ps-error">{err}</Text> : null}
      {blocked ? (
        <Pressable testID="ps-open-settings" style={styles.btn} onPress={() => Linking.openSettings()}>
          <Icon name="settings-outline" size={18} color={colors.brandPrimary} /><Text style={styles.btnText}>Buka Pengaturan</Text>
        </Pressable>
      ) : null}
      {busy ? <View style={{ alignItems: "center", gap: spacing.sm, padding: spacing.lg }}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.muted}>Mencari produk yang mirip…</Text></View> : null}
      {items ? <Text style={styles.h} testID="ps-count">{items.length ? `${items.length} produk paling mirip` : "Tidak ada produk yang mirip"}</Text> : null}
    </View>
  );

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="photo-search-screen">
      <ScreenHeader title="Cari dengan Foto" />
      <FlatList
        data={items ?? []}
        keyExtractor={(p) => p.product_id}
        numColumns={2}
        ListHeaderComponent={header}
        columnWrapperStyle={{ gap: GAP, paddingHorizontal: spacing.lg }}
        contentContainerStyle={{ gap: GAP, paddingBottom: insets.bottom + spacing.xl, width: "100%", maxWidth: 720, alignSelf: "center" }}
        ListEmptyComponent={items && !items.length ? <Text style={[styles.muted, { textAlign: "center", padding: spacing.lg }]}>Coba foto lain yang lebih jelas atau dari sudut berbeda.</Text> : null}
        renderItem={({ item }) => (
          <View style={{ width: CARD_W }} testID={`ps-hit-${item.product_id}`}>
            <ProductCard product={item} style={{ width: CARD_W }} />
            <View style={styles.sim} pointerEvents="none"><Text style={styles.simText}>Mirip {item.similarity}%</Text></View>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  hero: { flexDirection: "row", gap: spacing.md, alignItems: "center", padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  preview: { width: 72, height: 72, borderRadius: radius.md },
  h: { fontSize: fontSize.base, fontWeight: "700", color: colors.onSurface },
  muted: { fontSize: fontSize.sm, color: colors.muted },
  err: { fontSize: fontSize.sm, color: colors.error },
  row: { flexDirection: "row", gap: spacing.sm },
  btn: { flex: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  btnPrimary: { backgroundColor: colors.brandPrimary },
  btnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm },
  sim: { position: "absolute", top: spacing.sm, left: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  simText: { fontSize: 12, fontWeight: "700", color: colors.onBrandPrimary },
});
