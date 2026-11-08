import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform, useWindowDimensions } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { api, type Category, type EditorContext, type ProductDraft, type ProductForm } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { SellerShell } from "@/src/components/seller-shell";
import { ConfirmDialog } from "@/src/components/confirm-dialog";
import { fmtDate } from "@/src/utils/date";
import { EMPTY_FORM, validateForm, type Errors } from "@/src/components/product-editor/form";
import { BasicInfo } from "@/src/components/product-editor/basic-info";
import { MediaSection } from "@/src/components/product-editor/media-section";
import { VariantsSection } from "@/src/components/product-editor/variants-section";
import { Completeness, PriceStock } from "@/src/components/product-editor/price-stock";
import { ShippingSection, SpecsSection } from "@/src/components/product-editor/specs-shipping";

export default function ProductEditor() {
  const { id, draft } = useLocalSearchParams<{ id: string; draft?: string }>();
  const isNew = id === "new";
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const twoCol = width >= 1180;
  const scroll = useRef<any>(null); // ScrollView instance

  const [form, setForm] = useState<ProductForm | null>(null);
  const [ctx, setCtx] = useState<EditorContext | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [drafts, setDrafts] = useState<ProductDraft[]>([]);
  const [draftId, setDraftId] = useState<string | null>(draft ?? null);
  const [productId, setProductId] = useState<string | null>(isNew ? null : id ?? null);
  const [storeId, setStoreId] = useState("pgs-official");
  const [showErrors, setShowErrors] = useState(false);
  const [serverErrors, setServerErrors] = useState<Errors>({});
  const [busy, setBusy] = useState<"" | "draft" | "publish">("");
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const [askPublish, setAskPublish] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [done, setDone] = useState<{ product_id: string; status: string } | null>(null);
  const [loadErr, setLoadErr] = useState("");

  const flash = (ok: boolean, text: string) => { setToast({ ok, text }); setTimeout(() => setToast(null), 3500); };

  useEffect(() => {
    api.allCategories().then(setCats).catch(() => {});
    api.editorContext().then((c) => { setCtx(c); if (c.stores[0]) setStoreId((s) => (c.stores.some((x) => x.store_id === s) ? s : c.stores[0].store_id)); })
      .catch((e) => setLoadErr(e.message));
    if (draft) {
      api.editorDraft(draft).then((d) => { setForm({ ...EMPTY_FORM, ...d.data }); setProductId(d.product_id ?? null); setStoreId(d.store_id); }).catch((e) => setLoadErr(e.message));
    } else if (!isNew && id) {
      api.editorProduct(id).then((p) => { setForm({ ...EMPTY_FORM, ...p.data }); setStoreId(p.store_id); }).catch((e) => setLoadErr(e.message));
    } else {
      setForm({ ...EMPTY_FORM });
      api.editorDrafts().then(setDrafts).catch(() => {});
    }
  }, [id, draft, isNew]);

  const set = useCallback((p: Partial<ProductForm>) => {
    setForm((f) => (f ? { ...f, ...p } : f));
    setServerErrors((e) => { const n = { ...e }; Object.keys(p).forEach((k) => delete n[k]); return n; });
  }, []);
  const liveErrors = useMemo(() => (form ? validateForm(form, cats) : {}), [form, cats]);
  const errors: Errors = showErrors ? { ...liveErrors, ...serverErrors } : serverErrors;

  const payload = () => ({ draft_id: draftId, product_id: productId, store_id: admin ? storeId : null, data: form! });

  const saveDraft = async () => {
    if (!form) return;
    setBusy("draft");
    try {
      const d = await api.editorSaveDraft(payload());
      setDraftId(d.draft_id);
      flash(true, `Draft tersimpan · ${fmtDate(d.updated_at)}`);
    } catch (e: any) { flash(false, `Gagal menyimpan draft: ${e.message}`); } finally { setBusy(""); }
  };

  const tryPublish = () => {
    setShowErrors(true);
    if (Object.keys(liveErrors).length) {
      flash(false, `Lengkapi ${Object.keys(liveErrors).length} isian yang ditandai merah sebelum publikasi`);
      scroll.current?.scrollTo({ y: 0, animated: true });
      return;
    }
    setAskPublish(true);
  };

  const publish = async () => {
    setBusy("publish");
    try {
      const r = await api.editorPublish(payload());
      setAskPublish(false);
      setDraftId(null);
      setDone(r);
    } catch (e: any) {
      setAskPublish(false);
      if (e.errors) { setServerErrors(e.errors); setShowErrors(true); }
      flash(false, e.message);
    } finally { setBusy(""); }
  };

  const storeName = ctx?.stores.find((s) => s.store_id === storeId)?.name ?? "";
  const activeVariants = form?.variants.filter((v) => v.active).length ?? 0;

  const side = form ? <Completeness form={form} /> : null;
  return (
    <SellerShell admin={admin} title={isNew ? "Tambah Produk" : "Ubah Produk"}>
      {loadErr ? <Text style={[styles.err, { padding: spacing.lg }]} testID="pe-load-error">{loadErr}</Text> : !form || !ctx ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
          <ScrollView ref={scroll} contentContainerStyle={[styles.content, { paddingBottom: 120 + insets.bottom }]} keyboardShouldPersistTaps="handled" testID="product-editor">
            {isNew && !draftId && drafts.length ? (
              <View style={styles.drafts} testID="pe-drafts">
                <Icon name="document-text-outline" size={18} color={colors.brandPrimary} />
                <Text style={[styles.draftsText, { flex: 1 }]}>Anda punya {drafts.length} draft produk</Text>
                {drafts.slice(0, 3).map((d) => (
                  <Pressable key={d.draft_id} testID={`pe-draft-${d.draft_id}`} style={styles.draftChip} onPress={() => router.setParams({ draft: d.draft_id })}>
                    <Text style={styles.draftChipText} numberOfLines={1}>{d.data.name || "Tanpa nama"}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
            <View style={[styles.cols, twoCol && { flexDirection: "row", alignItems: "flex-start" }]}>
              <View style={{ flex: 1, gap: spacing.lg, minWidth: 0 }}>
                {!twoCol ? side : null}
                <BasicInfo form={form} set={set} errors={errors} cats={cats} ctx={ctx} storeId={storeId} onStore={setStoreId} />
                <MediaSection images={form.images} video={form.video} error={errors.images}
                  onImages={(f) => setForm((x) => (x ? { ...x, images: f(x.images) } : x))} onVideo={(u) => set({ video: u })}
                  maxImages={ctx.limits.images} imageMb={ctx.limits.image_mb} videoMb={ctx.limits.video_mb} />
                <VariantsSection form={form} set={set} errors={errors} maxCombos={ctx.limits.combos} />
                <PriceStock form={form} set={set} errors={errors} />
                <SpecsSection form={form} set={set} cats={cats} />
                <ShippingSection form={form} set={set} errors={errors} ctx={ctx} storeId={storeId} />
              </View>
              {twoCol ? <View style={{ width: 300 }}>{side}</View> : null}
            </View>
          </ScrollView>
          <View style={[styles.bar, { paddingBottom: Math.max(spacing.md, insets.bottom) }]}>
            {toast ? (
              <View style={[styles.toast, { backgroundColor: toast.ok ? colors.success : colors.error }]} testID={toast.ok ? "pe-toast-ok" : "pe-toast-error"}>
                <Icon name={toast.ok ? "checkmark-circle" : "alert-circle"} size={16} color={colors.onBrandPrimary} />
                <Text style={styles.toastText}>{toast.text}</Text>
              </View>
            ) : null}
            <View style={styles.barRow}>
              {productId && !admin ? (
                <Pressable testID="pe-delete" style={styles.del} onPress={() => setAskDelete(true)} disabled={!!busy}>
                  <Icon name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
              <Pressable testID="pe-save-draft" style={styles.outline} onPress={saveDraft} disabled={!!busy}>
                {busy === "draft" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Simpan Draft</Text>}
              </Pressable>
              <Pressable testID="pe-publish" style={styles.primary} onPress={tryPublish} disabled={!!busy}>
                <Text style={styles.primaryText}>{productId ? "Simpan Perubahan" : "Publikasikan"}</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      )}
      <ConfirmDialog visible={askPublish} danger={false} loading={busy === "publish"} confirmLabel={productId ? "Ya, simpan" : "Ya, publikasikan"}
        title={productId ? "Simpan perubahan produk?" : "Publikasikan produk?"}
        message={form ? `"${form.name.trim()}" akan ${form.status === "active" ? "langsung tampil untuk pembeli" : "disimpan sebagai Nonaktif (tidak tampil)"} di ${storeName}.${form.variants_enabled ? ` ${activeVariants} variasi aktif.` : ""}` : ""}
        onConfirm={publish} onCancel={() => setAskPublish(false)} />
      <ConfirmDialog visible={askDelete} title="Hapus produk?" message="Produk akan dihapus dari toko Anda." confirmLabel="Ya, hapus"
        onConfirm={async () => { try { await api.sellerDeleteProduct(productId!); setAskDelete(false); router.back(); } catch (e: any) { setAskDelete(false); flash(false, e.message); } }}
        onCancel={() => setAskDelete(false)} />
      <ConfirmDialog visible={!!done} danger={false} title="Produk berhasil disimpan 🎉"
        message={done?.status === "active" ? "Produk sudah tampil di aplikasi." : "Produk tersimpan sebagai Nonaktif dan belum tampil untuk pembeli."}
        confirmLabel={done?.status === "active" ? "Lihat produk" : "Selesai"}
        onConfirm={() => { const d = done!; setDone(null); if (d.status === "active") router.replace(`/product/${d.product_id}` as any); else router.back(); }}
        onCancel={() => { setDone(null); router.back(); }} />
    </SellerShell>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.lg, width: "100%", maxWidth: 1240, alignSelf: "center" },
  cols: { gap: spacing.lg },
  err: { color: colors.error, fontSize: fontSize.sm },
  drafts: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandTertiary },
  draftsText: { color: colors.onSurface, fontSize: fontSize.sm, fontWeight: "500" },
  draftChip: { backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 36, justifyContent: "center", maxWidth: 200 },
  draftChipText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "600" },
  bar: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: spacing.sm },
  barRow: { flexDirection: "row", gap: spacing.md, justifyContent: "flex-end", width: "100%", maxWidth: 1240, alignSelf: "center" },
  outline: { flex: 1, maxWidth: 220, minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  outlineText: { color: colors.brandPrimary, fontWeight: "600" },
  del: { width: 48, minHeight: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error, alignItems: "center", justifyContent: "center" },
  primary: { flex: 1, maxWidth: 260, minHeight: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600" },
  toast: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: radius.sm, padding: spacing.sm, alignSelf: "center", maxWidth: 1240, width: "100%" },
  toastText: { color: colors.onBrandPrimary, fontSize: 13, flex: 1 },
});
