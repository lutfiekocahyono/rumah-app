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
import { SeoSection } from "@/src/components/product-editor/seo-section";
import { ProductPreview } from "@/src/components/product-editor/product-preview";

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
  const skipReload = useRef(false);

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
  const [again, setAgain] = useState(false); // "Simpan & Tambah Baru"
  const [preview, setPreview] = useState(false);
  const [askCancel, setAskCancel] = useState(false);
  const [saved, setSaved] = useState(""); // last loaded/saved form, to know about unsaved changes
  const dirty = !!form && JSON.stringify(form) !== saved;
  const [auto, setAuto] = useState<{ state: "" | "saving" | "saved" | "error"; at?: string }>({ state: "" });
  const [duping, setDuping] = useState(false);
  const draftRef = useRef<string | null>(draft ?? null); // always the latest draft id (autosave may finish between renders)
  const savingRef = useRef<Promise<unknown> | null>(null);
  const setDraft = (d: string | null) => { draftRef.current = d; setDraftId(d); };
  const loaded = (f: ProductForm) => { setForm(f); setSaved(JSON.stringify(f)); };

  const flash = (ok: boolean, text: string) => { setToast({ ok, text }); setTimeout(() => setToast(null), 3500); };

  useEffect(() => {
    if (skipReload.current) { skipReload.current = false; return; } // URL cleared after "Simpan & Tambah Baru": keep the prepared form
    api.allCategories().then(setCats).catch(() => {});
    api.editorContext().then((c) => { setCtx(c); if (c.stores[0]) setStoreId((s) => (c.stores.some((x) => x.store_id === s) ? s : c.stores[0].store_id)); })
      .catch((e) => setLoadErr(e.message));
    setAuto({ state: "" });
    if (draft) {
      setDraft(draft);
      api.editorDraft(draft).then((d) => { loaded({ ...EMPTY_FORM, ...d.data }); setProductId(d.product_id ?? null); setStoreId(d.store_id); }).catch((e) => setLoadErr(e.message));
    } else if (!isNew && id) {
      api.editorProduct(id).then((p) => { loaded({ ...EMPTY_FORM, ...p.data }); setStoreId(p.store_id); }).catch((e) => setLoadErr(e.message));
      api.editorDrafts().then(setDrafts).catch(() => {});
    } else {
      loaded({ ...EMPTY_FORM });
      api.editorDrafts().then(setDrafts).catch(() => {});
    }
  }, [id, draft, isNew]);

  const set = useCallback((p: Partial<ProductForm>) => {
    setForm((f) => (f ? { ...f, ...p } : f));
    setServerErrors((e) => { const n = { ...e }; Object.keys(p).forEach((k) => delete n[k]); return n; });
  }, []);
  const liveErrors = useMemo(() => (form ? validateForm(form, cats) : {}), [form, cats]);
  const errors: Errors = showErrors ? { ...liveErrors, ...serverErrors } : serverErrors;

  const payload = () => ({ draft_id: draftRef.current, product_id: productId, store_id: admin ? storeId : null, data: form! });

  const saveDraft = async () => {
    if (!form) return;
    setBusy("draft");
    try {
      await savingRef.current?.catch(() => {});
      const d = await api.editorSaveDraft(payload());
      setDraft(d.draft_id);
      setSaved(JSON.stringify(form));
      setAuto({ state: "saved", at: d.updated_at });
      flash(true, `Draft tersimpan · ${fmtDate(d.updated_at)}`);
    } catch (e: any) { flash(false, `Gagal menyimpan draft: ${e.message}`); } finally { setBusy(""); }
  };

  // Autosave: 4 s after the last change, quietly keep a draft (only once something was filled in)
  const autosave = async () => {
    if (savingRef.current || !form) return;
    const snap = JSON.stringify(form);
    setAuto({ state: "saving" });
    const p = api.editorSaveDraft(payload());
    savingRef.current = p;
    try {
      const d = await p;
      setDraft(d.draft_id);
      setSaved(snap);
      setAuto({ state: "saved", at: d.updated_at });
    } catch { setAuto({ state: "error" }); } finally { savingRef.current = null; }
  };
  const started = !!form && (!!form.name.trim() || form.images.length > 0 || !!form.description.trim());
  useEffect(() => {
    if (!dirty || busy || !started) return;
    const t = setTimeout(() => { void autosave(); }, 4000);
    return () => clearTimeout(t);
  }, [form, dirty, busy, started]); // eslint-disable-line react-hooks/exhaustive-deps

  const duplicate = async () => {
    if (!productId) return;
    setDuping(true);
    try {
      const d = await api.editorDuplicate(productId);
      router.push(`/product-editor/new?draft=${d.draft_id}` as any);
    } catch (e: any) { flash(false, e.message); } finally { setDuping(false); }
  };
  const resumeDraft = drafts.find((d) => !isNew && !draft && d.product_id === id);

  const tryPublish = (andNew: boolean) => {
    setAgain(andNew);
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
      await savingRef.current?.catch(() => {}); // let a running autosave finish so its draft gets cleaned up
      const r = await api.editorPublish(payload());
      setAskPublish(false);
      setDraft(null);
      setAuto({ state: "" });
      setSaved(JSON.stringify(form));
      if (again) {
        // keep store, category and etalase so the next similar product is quicker to add
        const next = { ...EMPTY_FORM, category: form!.category, subcategory: form!.subcategory, showcase: form!.showcase };
        setShowErrors(false);
        setServerErrors({});
        setProductId(null);
        loaded(next);
        scroll.current?.scrollTo({ y: 0, animated: true });
        api.editorDrafts().then(setDrafts).catch(() => {});
        if (!isNew || draft) { skipReload.current = true; router.setParams({ id: "new", draft: undefined } as any); }
        flash(true, `"${form!.name.trim()}" berhasil disimpan. Silakan tambah produk berikutnya.`);
        return;
      }
      setDone(r);
    } catch (e: any) {
      setAskPublish(false);
      if (e.errors) { setServerErrors(e.errors); setShowErrors(true); }
      flash(false, e.message);
    } finally { setBusy(""); }
  };

  const storeName = ctx?.stores.find((s) => s.store_id === storeId)?.name ?? "";
  const leave = () => (router.canGoBack() ? router.back() : router.replace((admin ? "/admin" : "/seller") as any));
  const activeVariants = form?.variants.filter((v) => v.active).length ?? 0;

  const side = form ? <Completeness form={form} /> : null;
  return (
    <SellerShell admin={admin} title={productId ? "Ubah Produk" : "Tambah Produk"}>
      {loadErr ? <Text style={[styles.err, { padding: spacing.lg }]} testID="pe-load-error">{loadErr}</Text> : !form || !ctx ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
          <ScrollView ref={scroll} contentContainerStyle={[styles.content, { paddingBottom: 190 + insets.bottom }]} keyboardShouldPersistTaps="handled" testID="product-editor">
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
            {resumeDraft ? (
              <View style={styles.drafts} testID="pe-resume-draft">
                <Icon name="time-outline" size={18} color={colors.brandPrimary} />
                <Text style={[styles.draftsText, { flex: 1 }]}>Ada perubahan tersimpan otomatis ({fmtDate(resumeDraft.updated_at)}) yang belum disimpan ke produk</Text>
                <Pressable testID="pe-resume-open" style={styles.draftChip} onPress={() => router.setParams({ draft: resumeDraft.draft_id })}>
                  <Text style={styles.draftChipText}>Lanjutkan</Text>
                </Pressable>
                <Pressable testID="pe-resume-discard" style={styles.draftChip} onPress={() => { api.editorDeleteDraft(resumeDraft.draft_id).catch(() => {}); setDrafts((x) => x.filter((d) => d.draft_id !== resumeDraft.draft_id)); }}>
                  <Text style={[styles.draftChipText, { color: colors.onSurfaceSecondary }]}>Abaikan</Text>
                </Pressable>
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
                <SeoSection form={form} set={set} cats={cats} storeName={storeName} />
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
            <View style={[styles.barRow, styles.wrapRow]}>
              <Text style={[styles.autoText, { flex: 1 }, auto.state === "error" && { color: colors.error }]} testID="pe-autosave" numberOfLines={1}>
                {auto.state === "saving" ? "Menyimpan otomatis…" : auto.state === "error" ? "Gagal simpan otomatis" : dirty ? (started ? "Perubahan belum tersimpan" : "")
                  : auto.state === "saved" && auto.at ? "✓ Tersimpan otomatis" : ""}
              </Text>
              {productId ? (
                <Pressable testID="pe-duplicate" style={styles.ghost} onPress={duplicate} disabled={duping || !!busy}>
                  {duping ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="copy-outline" size={16} color={colors.brandPrimary} />}
                  <Text style={[styles.ghostText, { color: colors.brandPrimary }]}>Duplikat</Text>
                </Pressable>
              ) : null}
              <Pressable testID="pe-cancel" style={styles.ghost} onPress={() => (dirty ? setAskCancel(true) : leave())} disabled={!!busy}>
                <Text style={styles.ghostText}>Batalkan</Text>
              </Pressable>
              <Pressable testID="pe-preview-btn" style={styles.ghost} onPress={() => setPreview(true)}>
                <Icon name="eye-outline" size={16} color={colors.brandPrimary} />
                <Text style={[styles.ghostText, { color: colors.brandPrimary }]}>Preview Produk</Text>
              </Pressable>
              {productId && !admin ? (
                <Pressable testID="pe-delete" style={styles.del} onPress={() => setAskDelete(true)} disabled={!!busy}>
                  <Icon name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
              <Pressable testID="pe-save-draft" style={styles.outline} onPress={saveDraft} disabled={!!busy}>
                {busy === "draft" ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.outlineText}>Simpan Draft</Text>}
              </Pressable>
            </View>
            <View style={styles.barRow}>
              <Pressable testID="pe-publish-new" style={styles.outline} onPress={() => tryPublish(true)} disabled={!!busy}>
                <Text style={styles.outlineText} numberOfLines={1}>Simpan & Tambah Baru</Text>
              </Pressable>
              <Pressable testID="pe-publish" style={styles.primary} onPress={() => tryPublish(false)} disabled={!!busy}>
                <Text style={styles.primaryText}>{productId ? "Simpan Perubahan" : "Publikasikan"}</Text>
              </Pressable>
            </View>
          </View>
          <ProductPreview visible={preview} form={form} storeName={storeName} onClose={() => setPreview(false)} />
        </KeyboardAvoidingView>
      )}
      <ConfirmDialog visible={askCancel} title="Batalkan perubahan?" message={draftId ? "Perubahan terakhir yang belum tersimpan otomatis akan hilang. Draft sebelumnya tetap ada dan bisa dilanjutkan nanti." : "Perubahan yang belum disimpan akan hilang. Simpan Draft dulu jika ingin melanjutkan nanti."}
        confirmLabel="Ya, batalkan" onConfirm={() => { setAskCancel(false); leave(); }} onCancel={() => setAskCancel(false)} />
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
  wrapRow: { flexWrap: "wrap" },
  ghost: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 44, paddingHorizontal: spacing.md, justifyContent: "center" },
  ghostText: { color: colors.onSurfaceSecondary, fontWeight: "600", fontSize: fontSize.sm },
  primary: { flex: 1, maxWidth: 260, minHeight: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "600" },
  toast: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: radius.sm, padding: spacing.sm, alignSelf: "center", maxWidth: 1240, width: "100%" },
  toastText: { color: colors.onBrandPrimary, fontSize: 13, flex: 1 },
  autoText: { fontSize: 12, color: colors.muted, alignSelf: "center", minWidth: 120 },
});
