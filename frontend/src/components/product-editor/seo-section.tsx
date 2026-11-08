import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import type { Category, ProductForm } from "@/src/api";
import { Input, Section, ui } from "./ui";

const plain = (md: string) => md.replace(/[*_#>`]/g, "").replace(/^\s*([-•]|\d+\.)\s+/gm, "").replace(/\s+/g, " ").trim();
const cut = (s: string, n: number) => (s.length <= n ? s : `${s.slice(0, n - 1).replace(/\s+\S*$/, "")}…`);
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "produk";

/** Title ideas from the name, brand, category, store and key specs (max 70 characters). */
export function titleIdeas(f: ProductForm, category: string, store: string): string[] {
  const name = f.name.trim();
  if (!name) return [];
  const brand = f.brand.trim() && !name.toLowerCase().includes(f.brand.trim().toLowerCase()) ? ` ${f.brand.trim()}` : "";
  const spec = f.specs.material || f.specs.size || "";
  // drop the " - Store" / " | Store" tail when it doesn't fit instead of cutting the store name
  const fit = (t: string, tail: string) => cut((t + tail).length <= 70 ? t + tail : t, 70);
  return [...new Set([
    fit(`${name}${brand}${category ? ` - ${category}` : ""}`, ` | ${store}`),
    fit(`Jual ${name}${brand} ${f.condition === "used" ? "Bekas" : "Original"} Harga Grosir`, ""),
    fit(`${name}${spec ? ` ${spec}` : ""} Murah${f.preorder ? " (Pre-order)" : " Siap Kirim"}`, ` - ${store}`),
  ].map((t) => t.replace(/\s+/g, " ")))];
}

export function keywordIdeas(f: ProductForm, category: string): string[] {
  const words = f.name.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w.length > 2);
  const base = [f.name.trim().toLowerCase(), category.toLowerCase(), f.brand.trim().toLowerCase(), words.slice(0, 2).join(" "), `${words[0] ?? ""} murah`, `${words[0] ?? ""} grosir`];
  return [...new Set(base.filter((k) => k.trim().length > 2))].filter((k) => !f.keywords.includes(k)).slice(0, 6);
}

/** SEO checks shown as score + checklist. */
export function seoChecks(f: ProductForm) {
  const title = (f.seo_title || f.name).trim();
  const meta = f.meta_description.trim();
  const main = (f.keywords[0] ?? "").toLowerCase();
  return [
    { label: "Judul SEO 40–70 karakter", ok: title.length >= 40 && title.length <= 70, w: 20 },
    { label: "Judul memuat kata kunci utama", ok: !!main && title.toLowerCase().includes(main), w: 15 },
    { label: "Meta description 120–160 karakter", ok: meta.length >= 120 && meta.length <= 160, w: 20 },
    { label: "Meta description memuat kata kunci utama", ok: !!main && meta.toLowerCase().includes(main), w: 10 },
    { label: "Minimal 3 kata kunci", ok: f.keywords.length >= 3, w: 15 },
    { label: "Deskripsi produk ≥ 300 karakter", ok: plain(f.description).length >= 300, w: 10 },
    { label: "Minimal 3 foto produk", ok: f.images.length >= 3, w: 10 },
  ];
}

export function SeoSection({ form, set, cats, storeName }: { form: ProductForm; set: (p: Partial<ProductForm>) => void; cats: Category[]; storeName: string }) {
  const [kw, setKw] = useState("");
  const category = cats.find((c) => c.category_id === (form.subcategory || form.category))?.name ?? "";
  const ideas = titleIdeas(form, category, storeName);
  const checks = seoChecks(form);
  const score = checks.reduce((t, c) => t + (c.ok ? c.w : 0), 0);
  const tone = score >= 80 ? colors.success : score >= 50 ? colors.warning : colors.error;
  const title = (form.seo_title || form.name || "Judul produk").trim();
  const meta = form.meta_description.trim() || cut(plain(form.description), 160) || "Meta description akan tampil di sini.";
  const addKw = (k: string) => {
    const v = k.trim().toLowerCase().slice(0, 40);
    if (v && !form.keywords.includes(v) && form.keywords.length < 10) set({ keywords: [...form.keywords, v] });
    setKw("");
  };
  return (
    <Section title="SEO Produk" icon="search-outline" testID="pe-seo" subtitle="Bantu produk muncul di pencarian Google dan pencarian aplikasi."
      right={<View style={[styles.score, { borderColor: tone }]} testID="pe-seo-score"><Text style={[styles.scoreText, { color: tone }]}>{score}</Text></View>}>
      <Input testID="pe-seo-title" label="Judul SEO" value={form.seo_title} maxLength={70} counter={`${form.seo_title.length}/70`}
        onChangeText={(t) => set({ seo_title: t })} placeholder={form.name || "Kosong = memakai nama produk"} />
      {ideas.length ? (
        <View style={{ gap: 6 }} testID="pe-seo-ideas">
          <Text style={ui.hint}>Rekomendasi judul (ketuk untuk memakai):</Text>
          {ideas.map((t, i) => (
            <Pressable key={t} testID={`pe-seo-idea-${i}`} style={styles.idea} onPress={() => set({ seo_title: t })}>
              <Icon name="sparkles-outline" size={14} color={colors.brandPrimary} />
              <Text style={styles.ideaText}>{t}</Text>
              <Text style={ui.hint}>{t.length}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      <View style={{ gap: 4 }}>
        <Input testID="pe-seo-meta" label="Meta description" value={form.meta_description} maxLength={160} counter={`${form.meta_description.length}/160`}
          multiline onChangeText={(t) => set({ meta_description: t })} placeholder="Ringkasan singkat yang menarik untuk hasil pencarian" style={{ minHeight: 70 }} />
        {plain(form.description) ? (
          <Pressable testID="pe-seo-meta-auto" onPress={() => set({ meta_description: cut(plain(form.description), 160) })} style={{ alignSelf: "flex-start", minHeight: 36, justifyContent: "center" }}>
            <Text style={styles.link}>Buat otomatis dari deskripsi</Text>
          </Pressable>
        ) : null}
      </View>
      <View style={{ gap: 6 }}>
        <Text style={ui.label}>Kata kunci produk ({form.keywords.length}/10) — kata pertama = kata kunci utama</Text>
        <View style={styles.wrap}>
          {form.keywords.map((k, i) => (
            <View key={k} style={[styles.kw, i === 0 && { borderColor: colors.brandPrimary }]} testID={`pe-kw-${k}`}>
              <Text style={styles.kwText}>{k}</Text>
              <Pressable hitSlop={8} testID={`pe-kw-del-${k}`} style={styles.kwDel} onPress={() => set({ keywords: form.keywords.filter((x) => x !== k) })}><Icon name="close" size={14} color={colors.onSurfaceSecondary} /></Pressable>
            </View>
          ))}
          {form.keywords.length < 10 ? (
            <View style={[ui.inputWrap, { minWidth: 180, flex: 1 }]}>
              <TextInput testID="pe-kw-input" value={kw} onChangeText={setKw} onSubmitEditing={() => addKw(kw)} blurOnSubmit={false}
                placeholder="Tambah kata kunci" placeholderTextColor={colors.muted} style={ui.input} />
              <Pressable testID="pe-kw-add" onPress={() => addKw(kw)} style={styles.addBtn}><Icon name="add-circle" size={22} color={colors.brandPrimary} /></Pressable>
            </View>
          ) : null}
        </View>
        <View style={styles.wrap}>
          {keywordIdeas(form, category).map((k) => (
            <Pressable key={k} testID={`pe-kw-idea-${k}`} style={styles.kwIdea} onPress={() => addKw(k)}><Text style={styles.link}>+ {k}</Text></Pressable>
          ))}
        </View>
      </View>

      <View style={styles.serp} testID="pe-seo-preview">
        <Text style={ui.hint}>Pratinjau hasil pencarian</Text>
        <Text style={styles.url} numberOfLines={1}>pusatgrosirsidoarjo.com › produk › {slug(form.name)}</Text>
        <Text style={styles.serpTitle} numberOfLines={1}>{cut(title, 60)}</Text>
        <Text style={styles.serpDesc} numberOfLines={2}>{meta}</Text>
      </View>
      <View style={{ gap: 4 }} testID="pe-seo-checks">
        {checks.map((c) => (
          <View key={c.label} style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
            <Icon name={c.ok ? "checkmark-circle" : "ellipse-outline"} size={16} color={c.ok ? colors.success : colors.muted} />
            <Text style={{ fontSize: 13, color: colors.onSurface }}>{c.label}</Text>
          </View>
        ))}
      </View>
    </Section>
  );
}

const styles = StyleSheet.create({
  score: { width: 44, height: 44, borderRadius: 22, borderWidth: 3, alignItems: "center", justifyContent: "center" },
  scoreText: { fontWeight: "700", fontSize: fontSize.sm },
  idea: { flexDirection: "row", alignItems: "center", gap: 6, padding: spacing.sm, minHeight: 44, borderRadius: radius.sm, backgroundColor: colors.brandTertiary },
  ideaText: { flex: 1, fontSize: 13, color: colors.onSurface },
  link: { color: colors.brandPrimary, fontSize: 13, fontWeight: "600" },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },
  kw: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 36, backgroundColor: colors.surface },
  kwText: { fontSize: 13, color: colors.onSurface },
  kwDel: { width: 32, height: 36, alignItems: "center", justifyContent: "center", marginRight: -spacing.sm },
  kwIdea: { minHeight: 36, justifyContent: "center", paddingHorizontal: spacing.sm },
  addBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  serp: { gap: 2, padding: spacing.md, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  url: { fontSize: 12, color: colors.success },
  serpTitle: { fontSize: 17, color: "#1A0DAB" }, // search-result link blue stays the same in every theme
  serpDesc: { fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 18 },
});
