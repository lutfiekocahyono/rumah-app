import React from "react";
import { View, Text, StyleSheet, Switch } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, radius, spacing } from "@/src/theme";
import type { Category, EditorContext, ProductForm, SpecKey } from "@/src/api";
import { FieldError, Input, Pill, Section, digitsOf, ui } from "./ui";
import type { Errors } from "./form";

export const SPEC_LABELS: Record<SpecKey, string> = {
  material: "Bahan / material", color: "Warna", size: "Ukuran", dimensions: "Dimensi", weight: "Berat",
  origin_country: "Negara asal", warranty: "Garansi", extra: "Informasi tambahan",
};
const PLACEHOLDER: Record<SpecKey, string> = {
  material: "Mis. Katun combed 30s", color: "Mis. Hitam, Putih", size: "Mis. S, M, L, XL", dimensions: "Otomatis dari pengiriman",
  weight: "Otomatis dari pengiriman", origin_country: "Mis. Indonesia", warranty: "Mis. 1 tahun garansi resmi", extra: "Mis. isi paket, cara perawatan",
};

/** Which specification fields fit the category (by its name); unknown categories get every field. */
function specKeysFor(name: string): SpecKey[] {
  const n = name.toLowerCase();
  if (/fashion|pakaian|baju|kaos|celana|sepatu|sandal|tas|hijab|busana|kemeja|jaket/.test(n)) return ["material", "color", "size", "origin_country", "extra"];
  if (/elektronik|tv|televisi|ac\b|kulkas|audio|speaker|dispenser|mesin|kipas|gadget|handphone|komputer|listrik|lampu/.test(n))
    return ["color", "dimensions", "weight", "origin_country", "warranty", "extra"];
  if (/dapur|rumah|perabot|masak|furnitur|mebel|perlengkapan/.test(n)) return ["material", "color", "size", "dimensions", "weight", "origin_country", "warranty", "extra"];
  if (/makanan|minuman|snack|sembako|bumbu/.test(n)) return ["weight", "origin_country", "extra"];
  return ["material", "color", "size", "dimensions", "weight", "origin_country", "warranty", "extra"];
}

const dimsText = (f: ProductForm) => (f.length_cm && f.width_cm && f.height_cm ? `${f.length_cm} × ${f.width_cm} × ${f.height_cm} cm` : "");
const weightText = (g: number) => (g ? (g >= 1000 ? `${(g / 1000).toLocaleString("id-ID")} kg` : `${g} gram`) : "");

export function SpecsSection({ form, set, cats }: { form: ProductForm; set: (p: Partial<ProductForm>) => void; cats: Category[] }) {
  const cat = cats.find((c) => c.category_id === form.category);
  const keys = specKeysFor(`${cat?.name ?? ""} ${cats.find((c) => c.category_id === form.subcategory)?.name ?? ""}`);
  const setSpec = (k: SpecKey, v: string) => set({ specs: { ...form.specs, [k]: v } });
  return (
    <Section title="Detail & Spesifikasi" icon="document-text-outline" testID="pe-specs"
      subtitle={cat ? `Isian disesuaikan untuk kategori ${cat.name}.` : "Pilih kategori dulu agar isian menyesuaikan."}>
      <View style={ui.row}>
        <Input testID="pe-spec-brand" label="Merek" value={form.brand} onChangeText={(t) => set({ brand: t })} maxLength={60} placeholder="Sama dengan merek di Informasi Dasar" />
        {keys.map((k) => {
          const auto = k === "dimensions" ? dimsText(form) : k === "weight" ? weightText(form.weight_grams) : "";
          return (
            <Input key={k} testID={`pe-spec-${k}`} label={SPEC_LABELS[k]} maxLength={300} multiline={k === "extra"}
              value={auto || form.specs[k] || ""} editable={!auto} hint={auto ? "Diambil dari Pengaturan Pengiriman" : undefined}
              onChangeText={(t) => setSpec(k, t)} placeholder={PLACEHOLDER[k]} style={k === "extra" ? { minHeight: 80 } : undefined} />
          );
        })}
      </View>
    </Section>
  );
}

export function ShippingSection({ form, set, errors, ctx, storeId }: { form: ProductForm; set: (p: Partial<ProductForm>) => void; errors: Errors; ctx: EditorContext; storeId: string }) {
  const ship = ctx.shipping[storeId] ?? { origin: "", pickup: false, couriers: [] };
  const regular = ship.couriers.filter((c) => !c.cargo);
  const cargo = ship.couriers.filter((c) => c.cargo);
  const all = form.couriers.length === 0;
  const toggle = (code: string) => {
    const cur = all ? ship.couriers.map((c) => c.code) : form.couriers;
    const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code];
    set({ couriers: next.length === ship.couriers.length ? [] : next });
  };
  const vol = form.length_cm * form.width_cm * form.height_cm / 6; // grams
  return (
    <Section title="Pengaturan Pengiriman" icon="car-outline" testID="pe-shipping" subtitle="Berat dan ukuran dipakai untuk menghitung ongkir otomatis.">
      <View style={ui.row}>
        <Input testID="pe-weight" label="Berat (gram)" required keyboardType="number-pad" value={form.weight_grams ? String(form.weight_grams) : ""}
          onChangeText={(t) => set({ weight_grams: Math.min(500000, digitsOf(t)) })} error={errors.weight_grams} placeholder="Mis. 1200" />
        <Input testID="pe-length" label="Panjang (cm)" keyboardType="number-pad" value={form.length_cm ? String(form.length_cm) : ""} onChangeText={(t) => set({ length_cm: Math.min(500, digitsOf(t)) })} />
        <Input testID="pe-width" label="Lebar (cm)" keyboardType="number-pad" value={form.width_cm ? String(form.width_cm) : ""} onChangeText={(t) => set({ width_cm: Math.min(500, digitsOf(t)) })} />
        <Input testID="pe-height" label="Tinggi (cm)" keyboardType="number-pad" value={form.height_cm ? String(form.height_cm) : ""} onChangeText={(t) => set({ height_cm: Math.min(500, digitsOf(t)) })} />
      </View>
      <FieldError msg={errors.dimensions} testID="pe-dimensions-error" />
      {vol > form.weight_grams && form.weight_grams > 0 ? (
        <Text style={ui.hint} testID="pe-volumetric">Berat volume {weightText(Math.round(vol))} lebih besar dari berat asli — ongkir dihitung dari berat volume.</Text>
      ) : null}

      <View style={{ gap: spacing.sm }}>
        <View style={styles.toggleRow}>
          <View style={{ flex: 1 }}><Text style={ui.label}>Pengiriman reguler</Text><Text style={ui.hint}>Kurir ekspedisi biasa</Text></View>
          <Switch testID="pe-ship-regular" value={form.ship_regular} onValueChange={(v) => set({ ship_regular: v })} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor={colors.surface} />
        </View>
        {form.ship_regular ? (
          <View style={ui.row}>
            {regular.map((c) => <Pill key={c.code} testID={`pe-courier-${c.code}`} icon={all || form.couriers.includes(c.code) ? "checkbox" : "square-outline"} label={c.name} on={all || form.couriers.includes(c.code)} onPress={() => toggle(c.code)} />)}
            {!regular.length ? <Text style={ui.hint}>Toko belum punya kurir reguler aktif. Atur di menu Pengiriman.</Text> : null}
          </View>
        ) : null}
        <View style={styles.toggleRow}>
          <View style={{ flex: 1 }}><Text style={ui.label}>Pengiriman kargo</Text><Text style={ui.hint}>{cargo.length ? "Untuk barang besar / berat" : "Belum tersedia: tambahkan kurir kargo (mis. JNE Trucking, Indah Cargo) di menu Pengiriman"}</Text></View>
          <Switch testID="pe-ship-cargo" value={form.ship_cargo} disabled={!cargo.length && !form.ship_cargo} onValueChange={(v) => set({ ship_cargo: v })} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor={colors.surface} />
        </View>
        {form.ship_cargo && cargo.length ? (
          <View style={ui.row}>
            {cargo.map((c) => <Pill key={c.code} testID={`pe-courier-${c.code}`} icon={all || form.couriers.includes(c.code) ? "checkbox" : "square-outline"} label={c.name} on={all || form.couriers.includes(c.code)} onPress={() => toggle(c.code)} />)}
          </View>
        ) : null}
        <FieldError msg={errors.shipping} testID="pe-shipping-error" />
        {ship.pickup ? <Text style={ui.hint}>✓ Ambil di toko selalu tersedia untuk pembeli.</Text> : null}
      </View>

      <View style={styles.toggleRow}>
        <View style={{ flex: 1 }}><Text style={ui.label}>Pre-order</Text><Text style={ui.hint}>Barang dibuat/dipesan dulu setelah ada pesanan</Text></View>
        <Switch testID="pe-preorder" value={form.preorder} onValueChange={(v) => set({ preorder: v, preorder_days: v ? form.preorder_days || 7 : 0 })} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor={colors.surface} />
      </View>
      <View style={ui.row}>
        {form.preorder ? (
          <Input testID="pe-preorder-days" label="Lama pre-order (hari)" required keyboardType="number-pad" value={form.preorder_days ? String(form.preorder_days) : ""}
            onChangeText={(t) => set({ preorder_days: Math.min(90, digitsOf(t)) })} error={errors.preorder_days} hint="1–90 hari" />
        ) : (
          <Input testID="pe-processing-days" label="Waktu pemrosesan pesanan (hari)" keyboardType="number-pad" value={String(form.processing_days || "")}
            onChangeText={(t) => set({ processing_days: Math.max(1, Math.min(30, digitsOf(t))) })} hint="Sebelum paket diserahkan ke kurir (1–30 hari)" />
        )}
      </View>

      <View style={styles.origin} testID="pe-origin">
        <Icon name="location-outline" size={18} color={colors.brandPrimary} />
        <View style={{ flex: 1 }}>
          <Text style={ui.label}>Lokasi asal pengiriman</Text>
          <Text style={ui.hint}>{ship.origin || "Belum diatur. Super Admin mengatur asal pengiriman cabang di Pengaturan Ongkir; toko penjual mengisi alamat toko."}</Text>
        </View>
      </View>
    </Section>
  );
}

const styles = StyleSheet.create({
  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 },
  origin: { flexDirection: "row", gap: spacing.sm, alignItems: "center", padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
});
