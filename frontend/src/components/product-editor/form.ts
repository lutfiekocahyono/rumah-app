import type { Category, ProductForm, VariantOption, VariantRow } from "@/src/api";

export const EMPTY_FORM: ProductForm = {
  name: "", category: "", subcategory: "", brand: "", sku: "", condition: "new", showcase: "", status: "active",
  description: "", images: [], video: "", price: 0, discount_price: 0, stock: 0, min_order: 1, max_order: 0, low_stock_alert: 0,
  variants_enabled: false, variant_options: [], variants: [],
};
export type Errors = Record<string, string>;
export const MIN_DESC = 30;

export const plainLen = (md: string) => md.replace(/[*_#>`-]/g, "").replace(/^\d+\.\s/gm, "").trim().length;
export const vkey = (values: string[]) => values.join("/");

/** Every combination of the option values (Warna × Ukuran × Model). */
export function combos(options: VariantOption[]): string[][] {
  const groups = options.map((o) => o.values).filter((v) => v.length);
  if (!groups.length) return [];
  return groups.reduce<string[][]>((acc, g) => acc.flatMap((a) => g.map((v) => [...a, v])), [[]]);
}

/** Rebuild the variant table from the options, keeping what the seller already typed for each combination. */
export function syncRows(options: VariantOption[], rows: VariantRow[], defaults: { price: number; stock: number }): VariantRow[] {
  const old = new Map(rows.map((r) => [vkey(r.values), r]));
  return combos(options).map((values) => old.get(vkey(values)) ?? { variant_id: "", values, price: defaults.price, stock: defaults.stock, sku: "", image: "", active: true });
}

/** Same rules as the server (product_editor.validate). */
export function validateForm(f: ProductForm, cats: Category[]): Errors {
  const e: Errors = {};
  if (f.name.trim().length < 5) e.name = "Nama produk wajib diisi (min. 5 karakter)";
  if (!f.category) e.category = "Kategori wajib dipilih";
  else if (f.subcategory && !cats.some((c) => c.category_id === f.subcategory && c.parent === f.category)) e.subcategory = "Subkategori tidak sesuai kategori";
  if (!f.images.length) e.images = "Minimal 1 foto produk";
  const n = plainLen(f.description);
  if (n < MIN_DESC) e.description = `Deskripsi minimal ${MIN_DESC} karakter (sekarang ${n})`;
  if (f.max_order && f.max_order < f.min_order) e.max_order = "Maksimum pembelian harus ≥ minimum pembelian";
  if (f.min_order < 1) e.min_order = "Minimum pembelian minimal 1";
  if (f.stock < 0) e.stock = "Stok tidak boleh negatif";
  if (f.variants_enabled) {
    if (!f.variant_options.length) e.variants = "Tambahkan minimal 1 jenis variasi beserta pilihannya";
    f.variant_options.forEach((o, i) => {
      const vals = o.values.map((v) => v.trim());
      if (!o.name.trim()) e[`variant_options.${i}`] = "Nama variasi wajib diisi";
      else if (!vals.length) e[`variant_options.${i}`] = `Isi pilihan untuk ${o.name}`;
      else if (new Set(vals.map((v) => v.toLowerCase())).size !== vals.length) e[`variant_options.${i}`] = `Pilihan ${o.name} tidak boleh sama`;
    });
    if (f.variant_options.length && !f.variants.some((r) => r.active)) e.variants = "Minimal 1 variasi aktif";
    f.variants.forEach((r) => {
      if (r.active && r.price < 100) e[`variant.${vkey(r.values)}.price`] = "Harga minimal Rp100";
      if (r.stock < 0) e[`variant.${vkey(r.values)}.stock`] = "Stok tidak boleh negatif";
    });
  } else {
    if (f.price < 100) e.price = "Harga harus lebih dari 0 (min. Rp100)";
    if (f.discount_price && f.discount_price >= f.price) e.discount_price = "Harga diskon harus lebih kecil dari harga normal";
  }
  return e;
}

/** Checklist for the completeness indicator (required first, then recommended). */
export function checklist(f: ProductForm): { label: string; done: boolean; required: boolean }[] {
  const priced = f.variants_enabled ? f.variants.some((r) => r.active && r.price >= 100) : f.price >= 100;
  const stocked = f.variants_enabled ? f.variants.some((r) => r.active && r.stock > 0) : f.stock > 0;
  return [
    { label: "Nama produk", done: f.name.trim().length >= 5, required: true },
    { label: "Kategori", done: !!f.category, required: true },
    { label: "Foto produk", done: f.images.length > 0, required: true },
    { label: `Deskripsi (min. ${MIN_DESC} karakter)`, done: plainLen(f.description) >= MIN_DESC, required: true },
    { label: "Harga", done: priced, required: true },
    { label: "Stok", done: stocked, required: false },
    { label: "Minimal 3 foto", done: f.images.length >= 3, required: false },
    { label: "Merek", done: !!f.brand.trim(), required: false },
    { label: "Video produk", done: !!f.video, required: false },
  ];
}
