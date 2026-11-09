import React, { useEffect, useMemo, useState } from "react";
import { View, Text, Pressable } from "react-native";

import { colors, spacing } from "@/src/theme";
import { api } from "@/src/api";
import { Input, ui } from "./ui";

let cache: string[] | null = null;  // existing brands, loaded once per session

/** Merek: ketik bebas, dengan saran dari merek yang sudah ada supaya filter merek di pencarian tetap rapi. */
export function BrandInput({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  const [brands, setBrands] = useState<string[]>(cache ?? []);
  const [focus, setFocus] = useState(false);
  useEffect(() => {
    if (cache) return;
    api.productFacets().then((f) => { cache = f.brands.map((b) => b.name).sort((a, b) => a.localeCompare(b)); setBrands(cache); }).catch(() => {});
  }, []);
  const t = value.trim().toLowerCase();
  const hits = useMemo(() => (t ? brands.filter((b) => b.toLowerCase().includes(t) && b.toLowerCase() !== t).slice(0, 6) : []), [brands, t]);
  const exact = brands.find((b) => b.toLowerCase() === t);

  return (
    <View style={{ flex: 1, minWidth: 140, gap: 4 }}>
      <Input testID="pe-brand" label="Merek" value={value} maxLength={60} onChangeText={onChange} placeholder="Contoh: Advance"
        onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 200)}
        hint={exact && exact !== value.trim() ? `Disamakan dengan merek yang sudah ada: ${exact}` : "Dipakai untuk filter merek di pencarian"} />
      {exact && exact !== value.trim() ? (
        <Pressable onPress={() => onChange(exact)} hitSlop={6} testID="pe-brand-normalize"><Text style={[ui.hint, { color: colors.brandPrimary }]}>Pakai “{exact}”</Text></Pressable>
      ) : null}
      {focus && hits.length ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }} testID="pe-brand-suggestions">
          {hits.map((b) => (
            <Pressable key={b} style={ui.pill} onPress={() => onChange(b)} testID={`pe-brand-sug-${b}`}>
              <Text style={ui.pillText}>{b}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}
