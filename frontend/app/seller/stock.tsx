import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, TextInput, Pressable } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type InventoryItem } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles } from "@/src/components/admin-form";

function StockRow({ item }: { item: InventoryItem }) {
  const router = useRouter();
  const [val, setVal] = useState(String(item.stock));
  const [state, setState] = useState<"idle" | "saving" | "ok" | "err">("idle");
  const save = async () => {
    const n = Number(val.replace(/\D/g, "")) || 0;
    if (n === item.stock && state !== "err") return;
    setState("saving");
    try { await api.sellerSetStock(item.product_id, n); item.stock = n; setVal(String(n)); setState("ok"); } catch { setState("err"); }
  };
  return (
    <View style={styles.row} testID={`stock-row-${item.product_id}`}>
      <Image source={item.image} style={styles.img} contentFit="cover" />
      <Pressable style={{ flex: 1 }} disabled={!item.own} onPress={() => router.push(`/product-editor/${item.product_id}` as any)}>
        <Text style={styles.name} numberOfLines={2}>{item.name}</Text>
        <Text style={adminStyles.muted}>{formatIDR(item.price)} · {item.own ? "Produk toko ini" : "Katalog PGS"}</Text>
      </Pressable>
      <TextInput testID={`stock-input-${item.product_id}`} value={val} onChangeText={setVal} onBlur={save} onSubmitEditing={save}
        keyboardType="number-pad" style={[styles.input, state === "err" && { borderColor: colors.error, borderWidth: 1 }]} />
      <View style={{ width: 20 }}>
        {state === "saving" ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : state === "ok" ? <Icon name="checkmark" size={18} color={colors.success} /> : null}
      </View>
    </View>
  );
}

export default function SellerStock() {
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [done, setDone] = useState(false);
  const busy = useRef(false);

  const load = useCallback(async (reset: boolean, query: string, from: number) => {
    if (busy.current) return;
    busy.current = true;
    try {
      const page = await api.sellerInventory(query, from);
      setItems((cur) => (reset ? page : [...(cur ?? []), ...page.filter((p) => !(cur ?? []).some((c) => c.product_id === p.product_id))]));
      setDone(page.length < 40);
    } catch { setItems((c) => c ?? []); } finally { busy.current = false; }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => { setItems(null); void load(true, q, 0); }, 300);
    return () => clearTimeout(t);
  }, [q, load]);

  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="seller-stock-screen">
      <ScreenHeader title="Stok Toko" />
      <View style={styles.search}>
        <Icon name="search" size={16} color={colors.muted} />
        <TextInput testID="stock-search" value={q} onChangeText={setQ} placeholder="Cari produk" placeholderTextColor={colors.muted} style={{ flex: 1, paddingVertical: 10, color: colors.onSurface }} />
      </View>
      <Text style={[adminStyles.muted, { paddingHorizontal: spacing.lg }]}>Ubah angka stok lalu tekan di luar kolom untuk menyimpan. 9999 = tidak terbatas.</Text>
      {items === null ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.product_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          keyboardShouldPersistTaps="handled"
          onEndReached={() => { if (!done) void load(false, q, items.length); }}
          onEndReachedThreshold={0.5}
          ListEmptyComponent={<Text style={adminStyles.muted}>Produk tidak ditemukan.</Text>}
          renderItem={({ item }) => <StockRow item={item} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, margin: spacing.lg, marginBottom: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  img: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: fontSize.sm, color: colors.onSurface },
  input: { width: 72, textAlign: "center", backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingVertical: 8, color: colors.onSurface, fontWeight: "600" },
});
