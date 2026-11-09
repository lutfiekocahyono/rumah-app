"""Seller Center Tahap 3: product list, bulk edit (price / stock / status), Excel export, template and import."""
import csv
import html
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from fastapi import Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, Field, ValidationError

import history
import product_notify
from pricing import scale_tiers
from product_editor import ProductForm, TierRow, to_form, to_product, validate

MAX_ROWS = 10000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# (form key, Excel header). "*" = wajib untuk produk baru.
COLS = [
    ("product_id", "ID Produk (jangan diubah)"), ("sku", "SKU"), ("name", "Nama Produk*"), ("category", "Kategori*"),
    ("subcategory", "Subkategori"), ("brand", "Merek"), ("condition", "Kondisi (baru/bekas)"), ("status", "Status (aktif/nonaktif)"),
    ("showcase", "Etalase"), ("price", "Harga Normal*"), ("discount_price", "Harga Diskon"), ("stock", "Stok"),
    ("min_order", "Min. Beli"), ("max_order", "Maks. Beli (0 = bebas)"), ("weight_grams", "Berat (gram)*"),
    ("length_cm", "Panjang (cm)"), ("width_cm", "Lebar (cm)"), ("height_cm", "Tinggi (cm)"),
    ("images", "URL Foto* (pisahkan dengan baris baru)"), ("description", "Deskripsi* (min. 30 karakter)"),
    ("permalink", "Link Produk di Website (info)"),
]
# Column names used by the website (WooCommerce export, English & Indonesian) and common spellings -> form key
ALIASES = {
    "id": "product_id", "id produk": "product_id", "nama": "name", "name": "name", "nama produk": "name", "product name": "name",
    "categories": "category", "kategori": "category", "product categories": "category", "subkategori": "subcategory",
    "brands": "brand", "brand": "brand", "merek": "brand", "merk": "brand", "published": "status", "diterbitkan": "status",
    "status": "status", "regular price": "price", "harga reguler": "price", "harga normal": "price", "harga": "price",
    "sale price": "discount_price", "harga obral": "discount_price", "harga diskon": "discount_price", "harga promo": "discount_price",
    "stock": "stock", "stok": "stock", "stock quantity": "stock", "weight (kg)": "weight_kg", "berat (kg)": "weight_kg",
    "weight (g)": "weight_grams", "berat (g)": "weight_grams", "berat (gram)": "weight_grams", "berat": "weight_grams",
    "length (cm)": "length_cm", "panjang (cm)": "length_cm", "width (cm)": "width_cm", "lebar (cm)": "width_cm",
    "height (cm)": "height_cm", "tinggi (cm)": "height_cm", "images": "images", "gambar": "images", "foto": "images",
    "description": "description", "deskripsi": "description", "short description": "short_description",
    "deskripsi singkat": "short_description", "deskripsi pendek": "short_description", "type": "type", "tipe": "type",
    "jenis": "type", "permalink": "permalink", "link": "permalink", "url": "permalink", "kondisi": "condition",
    "condition": "condition", "etalase": "showcase", "min. beli": "min_order", "minimum order": "min_order",
}
EXTRA_LABEL = {"weight_kg": "Berat (kg, diubah ke gram)", "short_description": "Deskripsi (dipakai jika Deskripsi kosong)",
               "type": "Tipe produk (baris variasi dilewati)", "permalink": "Link website (info, tidak disimpan)"}
FIELD_LABEL = {k: h.split(" (")[0].rstrip("*") for k, h in COLS} | EXTRA_LABEL
REQUIRED_NEW = [("name", ("name",)), ("category", ("category",)), ("price", ("price",)), ("weight_grams", ("weight_grams", "weight_kg")),
                ("images", ("images",)), ("description", ("description", "short_description"))]
COL_DOCS = {  # Petunjuk Kolom: (wajib untuk produk baru, format / isi, contoh)
    "product_id": ("Tidak", "Kosongkan untuk produk baru. Terisi = mengubah produk itu (dari file Ekspor). ID website (mis. 9849) juga dikenali.", "pgs-9849"),
    "sku": ("Tidak", "Kode barang toko, maks. 40 karakter.", "DBLP32HC"),
    "name": ("Ya", "5–150 karakter.", "Happy Call Double Pan 32 cm"),
    "category": ("Ya", "Nama kategori dari sheet Kategori. Format website 'Dapur > Peralatan Masak' juga bisa.", "Dapur"),
    "subcategory": ("Tidak", "Nama subkategori dari sheet Kategori (harus di bawah kategorinya).", "Peralatan Masak"),
    "brand": ("Tidak", "Merek, maks. 60 karakter.", "Happy Call"),
    "condition": ("Tidak", "baru atau bekas (kosong = baru).", "baru"),
    "status": ("Tidak", "aktif (tampil) atau nonaktif (disembunyikan). Kosong = aktif.", "aktif"),
    "showcase": ("Tidak", "Nama etalase toko.", "Peralatan Dapur"),
    "price": ("Ya", "Angka rupiah tanpa titik/Rp, min. 100. Produk bervariasi: isi di sheet Variasi.", "167000"),
    "discount_price": ("Tidak", "Harus lebih kecil dari Harga Normal. Isi 0 untuk menghapus diskon.", "150000"),
    "stock": ("Tidak", "Angka 0–999999. 9999 = tidak terbatas.", "100"),
    "min_order": ("Tidak", "Minimal jumlah beli (kosong = 1).", "1"),
    "max_order": ("Tidak", "Maksimal jumlah beli, 0 = bebas.", "0"),
    "weight_grams": ("Ya", "Berat kemasan dalam gram (dipakai menghitung ongkir). Kolom website 'Weight (kg)' otomatis diubah ke gram.", "1500"),
    "length_cm": ("Tidak", "Panjang paket (cm). Isi ketiganya atau kosongkan semua.", "35"),
    "width_cm": ("Tidak", "Lebar paket (cm).", "35"),
    "height_cm": ("Tidak", "Tinggi paket (cm).", "12"),
    "images": ("Ya", "Link foto https://..., satu per baris di dalam sel (atau dipisah koma). Maks. 12, foto pertama = foto utama.", "https://pusatgrosirsidoarjo.com/wp-content/uploads/....webp"),
    "description": ("Ya", "Min. 30 karakter. Teks biasa; HTML dari website dibersihkan otomatis.", "Panci dua sisi anti lengket ..."),
    "permalink": ("Tidak", "Info saja (link produk di pusatgrosirsidoarjo.com), tidak disimpan saat impor.", "https://pusatgrosirsidoarjo.com/..."),
}
VCOLS = [("product_id", "ID Produk"), ("variant_id", "ID Variasi (jangan diubah)"), ("product_name", "Nama Produk (info)"),
         ("name", "Variasi (info)"), ("sku", "SKU Variasi"), ("price", "Harga"), ("stock", "Stok"), ("active", "Aktif (ya/tidak)")]
INT_KEYS = {"price", "discount_price", "stock", "min_order", "max_order", "weight_grams", "length_cm", "width_cm", "height_cm"}
PRICE_FN = {
    "set": lambda old, v: v, "up_pct": lambda old, v: round(old * (100 + v) / 100), "down_pct": lambda old, v: round(old * (100 - v) / 100),
    "up": lambda old, v: old + v, "down": lambda old, v: old - v,
}
STOCK_FN = {"set": lambda old, v: v, "add": lambda old, v: old + v, "sub": lambda old, v: old - v}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("*", "")).strip().lower()


def _int(v) -> int:
    """167000 / '167.000' / 'Rp 167.000' / '167000.00' -> 167000."""
    if isinstance(v, (int, float)):
        return max(0, int(round(v)))
    s = str(v).strip()
    if re.fullmatch(r"\d+[.,]\d{1,2}", s):
        return int(round(float(s.replace(",", "."))))
    d = re.sub(r"[^\d]", "", s.split(",")[0])
    if not d:
        raise ValueError
    return int(d)


def _float(v) -> float:
    return float(v) if isinstance(v, (int, float)) else float(str(v).strip().replace(",", "."))


def clean_html(s: str) -> str:
    """Website descriptions are HTML: keep line breaks, drop tags."""
    if "<" not in s and "&" not in s:
        return s.strip()
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


class BulkIn(BaseModel):
    store_id: Optional[str] = None
    product_ids: List[str] = Field(min_length=1, max_length=500)
    price_mode: str = Field(default="", pattern="^(|set|up_pct|down_pct|up|down)$")
    price_value: int = Field(default=0, ge=0, le=1_000_000_000)
    stock_mode: str = Field(default="", pattern="^(|set|add|sub)$")
    stock_value: int = Field(default=0, ge=0, le=999999)
    status: str = Field(default="", pattern="^(|active|inactive)$")


def list_row(p: dict) -> dict:
    vs = p.get("variants") or []
    return {"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", ""), "sku": p.get("sku", ""),
            "price": p.get("price", 0), "original_price": p.get("original_price") or p.get("price", 0), "stock": p.get("stock", 0),
            "status": p.get("status", "active"), "variants": len(vs), "sold": p.get("sold", 0), "store_id": p.get("store_id")}


def register(api, db, *, actor: Callable, target_store: Callable, editable: Callable, owner_key: Callable, form_of: Callable, load_parents: Callable, log_activity):

    async def scope(ctx: dict, store_id: Optional[str]) -> dict:
        return await target_store(ctx, store_id)

    # ---------------- list ----------------
    @api.get("/product-editor/products")
    async def list_products(store_id: Optional[str] = None, q: str = "", status: str = "", skip: int = 0,
                            limit: int = Query(default=30, le=100), ctx=Depends(actor)):
        store = await scope(ctx, store_id)
        query: dict = {"store_id": store["store_id"]}
        if q.strip():
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            query["$or"] = [{"name": rx}, {"sku": rx}, {"product_id": q.strip()}]
        if status == "inactive":
            query["status"] = "inactive"
        elif status == "active":
            query["status"] = {"$ne": "inactive"}
        elif status == "empty":
            query["stock"] = 0
        total = await db.products.count_documents(query)
        docs = await db.products.find(query, {"_id": 0}).sort([("updated_at", -1), ("product_id", 1)]).skip(max(0, skip)).limit(limit).to_list(limit)
        return {"total": total, "items": [list_row(d) for d in docs], "store_id": store["store_id"]}

    # ---------------- bulk edit ----------------
    def new_price(f: ProductForm, mode: str, v: int) -> Optional[str]:
        fn = PRICE_FN[mode]
        if f.variants_enabled:
            for r in f.variants:
                r.price = max(0, fn(r.price, v))
            return "Harga variasi jadi kurang dari Rp100" if any(r.active and r.price < 100 for r in f.variants) else None
        old_sell = f.discount_price or f.price
        normal = max(0, fn(f.price, v))
        disc = f.discount_price if mode == "set" else (max(0, fn(f.discount_price, v)) if f.discount_price else 0)
        if normal < 100:
            return "Harga jadi kurang dari Rp100"
        f.price, f.discount_price = normal, disc if 0 < disc < normal else 0
        # wholesale tiers move in proportion to the selling price, so buying more never costs more
        scaled = scale_tiers({k: [r.model_dump() for r in rows] for k, rows in f.tier_prices.items()}, old_sell, f.discount_price or f.price)
        f.tier_prices = {k: [TierRow(**r) for r in rows] for k, rows in scaled.items()}
        return None

    def new_stock(f: ProductForm, mode: str, v: int) -> None:
        fn = STOCK_FN[mode]
        if f.variants_enabled:
            for r in f.variants:
                r.stock = min(999999, max(0, fn(r.stock, v)))
        else:
            f.stock = min(999999, max(0, fn(f.stock, v)))

    @api.post("/product-editor/bulk")
    async def bulk_edit(body: BulkIn, ctx=Depends(actor)):
        if not (body.price_mode or body.stock_mode or body.status):
            raise HTTPException(status_code=400, detail="Pilih perubahan yang ingin diterapkan")
        if body.price_mode == "set" and body.price_value < 100:
            raise HTTPException(status_code=400, detail="Harga minimal Rp100")
        if body.price_mode in ("up_pct", "down_pct") and not 1 <= body.price_value <= (99 if body.price_mode == "down_pct" else 500):
            raise HTTPException(status_code=400, detail="Persentase harus 1–99% (turun) atau 1–500% (naik)")
        store = await scope(ctx, body.store_id)
        updated, skipped = 0, []
        for pid in dict.fromkeys(body.product_ids):
            p = await db.products.find_one({"product_id": pid, "store_id": store["store_id"]}, {"_id": 0})
            if not p:
                skipped.append({"product_id": pid, "name": "", "reason": "Produk tidak ditemukan di toko ini"})
                continue
            f = ProductForm(**to_form(p))
            if body.price_mode:
                err = new_price(f, body.price_mode, body.price_value)
                if err:
                    skipped.append({"product_id": pid, "name": p.get("name", ""), "reason": err})
                    continue
            if body.stock_mode:
                new_stock(f, body.stock_mode, body.stock_value)
            doc = to_product(f, store)
            upd = {k: doc[k] for k in ("price", "original_price", "discount", "stock", "in_stock", "variants", "tier_prices", "updated_at")}
            if body.status:
                upd["status"] = body.status
            if upd["stock"] > p.get("stock", 0):
                upd["restocked_at"] = _now()
            await db.products.update_one({"product_id": pid}, {"$set": upd})
            await history.record(db, ctx["user"], store["store_id"], p, history.snap(p), history.snap({**p, **upd}), "bulk")
            await product_notify.on_info(db, p, upd)  # inactive -> active counts as a new product for buyers
            updated += 1
        if updated:
            await log_activity(ctx["user"]["user_id"], "store", f"Edit massal {updated} produk")
        return {"updated": updated, "skipped": skipped}

    # ---------------- Excel export / template ----------------
    async def cat_maps():
        cats = await db.categories.find({}, {"_id": 0, "category_id": 1, "name": 1, "parent": 1}).to_list(5000)
        return cats, {c["category_id"]: c for c in cats}

    def head(ws, cols, fill="F97316"):
        ws.append([h for _, h in cols])
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=fill)
            c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.freeze_panes = "A2"
        for i, (_, h) in enumerate(cols):
            ws.column_dimensions[ws.cell(1, i + 1).column_letter].width = max(14, min(40, len(h) + 4))

    def build_xlsx(products: list, cats: list, by_id: dict, example: bool, examples: list = ()) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Produk"
        head(ws, COLS)
        vs = wb.create_sheet("Variasi")
        head(vs, VCOLS)
        if example:  # real catalogue products as examples (SKU "CONTOH-..." rows are skipped on import)
            for p in examples:
                f = form_of(p)
                cat, sub = by_id.get(f["category"], {}).get("name", ""), by_id.get(f["subcategory"], {}).get("name", "")
                ws.append(["", f"CONTOH-{f['sku'] or p['product_id']}"[:40], f["name"], cat, sub, f["brand"] or "", "baru", "aktif", "",
                           f["price"], f["discount_price"] or None, f["stock"] if f["stock"] < 9999 else 100, 1, 0,
                           f["weight_grams"] or 1000, f["length_cm"] or None, f["width_cm"] or None, f["height_cm"] or None,
                           "\n".join(f["images"][:3]), f["description"][:600], p.get("permalink", "")])
            for c in ws[ws.max_row - len(examples) + 1:ws.max_row] if examples else []:
                for cell in c:
                    cell.fill = PatternFill("solid", fgColor="FFF4E5")
        for p in products:
            f = form_of(p)
            v = bool(f["variants_enabled"])
            cat, sub = by_id.get(f["category"], {}).get("name", f["category"]), by_id.get(f["subcategory"], {}).get("name", "")
            ws.append([p["product_id"], f["sku"], f["name"], cat, sub, f["brand"], "bekas" if f["condition"] == "used" else "baru",
                       "nonaktif" if f["status"] == "inactive" else "aktif", f["showcase"],
                       None if v else f["price"], None if v or not f["discount_price"] else f["discount_price"], None if v else f["stock"],
                       f["min_order"], f["max_order"], f["weight_grams"] or None, f["length_cm"] or None, f["width_cm"] or None,
                       f["height_cm"] or None, "\n".join(f["images"]), f["description"], p.get("permalink", "")])
            for r in p.get("variants") or []:
                vs.append([p["product_id"], r.get("variant_id", ""), f["name"], r.get("name") or " / ".join(r.get("values", [])),
                           r.get("sku", ""), r.get("price", 0), r.get("stock", 0), "ya" if r.get("active", True) else "tidak"])
        g = wb.create_sheet("Panduan")
        for line in [
            "PANDUAN IMPOR PRODUK PGS", "",
            "1. Baris dengan 'ID Produk' terisi = MENGUBAH produk itu. Kosongkan ID untuk MENAMBAH produk baru.",
            "2. Kolom bertanda * wajib untuk produk baru. Kolom yang dikosongkan pada produk lama = tidak diubah. Isi 0 di Harga Diskon untuk menghapus diskon.",
            "3. Kategori & Subkategori: tulis nama persis seperti di sheet 'Kategori'.",
            "4. Harga & stok produk bervariasi diubah di sheet 'Variasi' (per ID Variasi). Variasi baru ditambah lewat Ubah Produk.",
            "5. URL Foto: link gambar (https://...), satu per baris di dalam sel. Maksimal 12 foto.",
            "6. Produk baru yang datanya belum lengkap disimpan sebagai DRAFT agar bisa dilengkapi di aplikasi.",
            "7. Maksimal 10.000 baris per file. Format .xlsx (Excel) atau .csv (mis. ekspor produk WooCommerce dari website).",
            "8. Baris berwarna oranye dengan SKU 'CONTOH-...' adalah contoh dan DILEWATI saat impor. Hapus atau ganti dengan produk Anda.",
            "9. Sebelum disimpan, aplikasi menampilkan pencocokan kolom file Anda dengan kolom aplikasi. Lihat sheet 'Petunjuk Kolom'.",
        ]:
            g.append([line])
        g.column_dimensions["A"].width = 110
        pk = wb.create_sheet("Petunjuk Kolom", 1)
        head(pk, [("", "Kolom"), ("", "Wajib (produk baru)"), ("", "Format / isi"), ("", "Contoh")])
        for key, label in COLS:
            pk.append([label, *COL_DOCS[key]])
        for col, w in zip("ABCD", (34, 18, 90, 40)):
            pk.column_dimensions[col].width = w
        for r in pk.iter_rows(min_row=2):
            for cell in r:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        k = wb.create_sheet("Kategori")
        head(k, [("", "Kategori"), ("", "Subkategori"), ("", "ID")])
        names = {c["category_id"]: c["name"] for c in cats}
        for c in sorted(cats, key=lambda c: (names.get(c.get("parent") or c["category_id"], ""), bool(c.get("parent")), c["name"])):
            k.append([names.get(c["parent"], "") if c.get("parent") else c["name"], c["name"] if c.get("parent") else "", c["category_id"]])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @api.get("/product-editor/export")
    async def export_xlsx(store_id: Optional[str] = None, template: bool = False, ctx=Depends(actor)):
        store = await scope(ctx, store_id)
        products = [] if template else await db.products.find({"store_id": store["store_id"]}, {"_id": 0}).sort("name", 1).to_list(20000)
        cats, by_id = await cat_maps()
        await load_parents()
        examples = []
        if template:  # 2 complete products from the catalogue (website data) as filled-in examples
            examples = await db.products.find({"images.0": {"$exists": True}, "variants": {"$in": [[], None]}, "price": {"$gte": 1000},
                                               "description": {"$regex": "^[\\s\\S]{60,}"}, "status": {"$ne": "inactive"}},
                                              {"_id": 0}).sort("product_id", 1).limit(2).to_list(2)
        data = await run_in_threadpool(build_xlsx, products, cats, by_id, template, examples)
        name = "template-impor-produk.xlsx" if template else f"produk-{store['store_id']}-{_now():%Y%m%d}.xlsx"
        return Response(content=data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ---------------- Excel import ----------------
    def read_sheet(rows, cols, aliases: Optional[dict] = None) -> tuple:
        """rows: iterator of tuples (first = header). Returns (data rows, column mapping shown to the seller)."""
        header = next(rows, None) or []
        lookup = (aliases or {}) | {_norm(v): k for k, v in FIELD_LABEL.items() if aliases is not None} | {_norm(h): k for k, h in cols} | {k: k for k, _ in cols}
        idx = {i: lookup.get(_norm(h)) for i, h in enumerate(header)}
        labels = FIELD_LABEL if aliases is not None else {k: h.split(" (")[0] for k, h in cols}
        mapping, used = [], set()
        for i, h in enumerate(header):
            if h is None or not str(h).strip():
                continue
            k, dup = idx[i], False
            if k in used:  # same field twice: keep the first column
                idx[i], k, dup = None, None, True
            if k:
                used.add(k)
            mapping.append({"header": str(h).strip(), "field": k, "label": labels.get(k, "") if k else ("duplikat (diabaikan)" if dup else "")})
        out = []
        for n, r in enumerate(rows, start=2):
            d = {idx[i]: v for i, v in enumerate(r) if idx.get(i) and v is not None and str(v).strip() != ""}
            if d:
                out.append((n, d))
        return out, mapping

    def resolve_cat(val, cats, parent: Optional[str] = None) -> Optional[str]:
        s = _norm(val)
        for c in cats:
            if (c.get("parent") or None) == parent and (_norm(c["name"]) == s or c["category_id"].lower() == s):
                return c["category_id"]
        return None

    def apply_patch(base: dict, d: dict, cats: list, by_id: Optional[dict] = None) -> tuple:
        """Excel cells -> form dict. Returns (form dict, cell errors). Category cells equal to the exported label keep the old value."""
        f, errs = dict(base), []
        d = dict(d)
        for key in ("category", "subcategory"):
            if key in d and by_id is not None and base.get(key) and _norm(d[key]) in (_norm(base[key]), _norm(by_id.get(base[key], {}).get("name"))):
                d.pop(key)
        if "category" in d:  # website format "Dapur > Peralatan Masak, Lainnya": first path, parent > child
            path = [x.strip() for x in str(d["category"]).split(",")[0].split(">") if x.strip()]
            if path:
                d["category"] = path[0]
                if len(path) > 1 and "subcategory" not in d:
                    d["subcategory"] = path[-1]
                if not resolve_cat(path[0], cats):  # a subcategory name on its own
                    sub = next((c for c in cats if c.get("parent") and _norm(c["name"]) == _norm(path[-1])), None)
                    if sub:
                        d["category"], d["subcategory"] = sub["parent"], sub["category_id"]
        if "weight_kg" in d and "weight_grams" not in d:
            try:
                f["weight_grams"] = int(round(_float(d["weight_kg"]) * 1000))
            except ValueError:
                errs.append("Kolom Berat (kg) harus angka")
        if "short_description" in d and "description" not in d:
            f["description"] = clean_html(str(d["short_description"]))
        for k, v in d.items():
            if k in ("product_id", "category", "subcategory", "weight_kg", "short_description", "type", "permalink"):
                continue
            if k == "description":
                f[k] = clean_html(str(v))
                continue
            if k in INT_KEYS:
                try:
                    f[k] = _int(v)
                except ValueError:
                    errs.append(f"Kolom {dict(COLS)[k].rstrip('*')} harus angka")
            elif k == "condition":
                f[k] = "used" if _norm(v) in ("bekas", "used") else "new"
            elif k == "status":
                f[k] = "inactive" if _norm(v) in ("nonaktif", "inactive", "tidak aktif", "0", "-1", "draft", "private", "pending") else "active"
            elif k == "images":
                f[k] = [u for u in re.split(r"[\n,;\s]+", str(v)) if u.startswith(("http://", "https://", "/api/files/"))][:12]
            else:
                f[k] = str(v).strip()
        if "category" in d:
            cid = resolve_cat(d["category"], cats)
            if not cid:
                errs.append(f"Kategori '{d['category']}' tidak ditemukan")
            else:
                f["category"], f["subcategory"] = cid, "" if cid != base.get("category") else base.get("subcategory", "")
        if "subcategory" in d and f.get("category"):
            sid = resolve_cat(d["subcategory"], cats, f["category"])
            if not sid:
                errs.append(f"Subkategori '{d['subcategory']}' tidak ada di kategori ini")
            else:
                f["subcategory"] = sid
        return f, errs

    @api.post("/product-editor/import")
    async def import_xlsx(file: UploadFile = File(...), store_id: Optional[str] = None, commit: bool = False, ctx=Depends(actor)):
        fname = (file.filename or "").lower()
        if not fname.endswith((".xlsx", ".csv")):
            raise HTTPException(status_code=400, detail="File harus berformat .xlsx (Excel) atau .csv")
        raw = await file.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran file maksimal 10 MB")
        vrows, vmap = [], []
        if fname.endswith(".csv"):  # e.g. WooCommerce product export from the website
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            first = text.split("\n", 1)[0]
            rows, pmap = read_sheet(iter(csv.reader(io.StringIO(text), delimiter=";" if first.count(";") > first.count(",") else ",")), COLS, ALIASES)
        else:
            try:
                wb = await run_in_threadpool(load_workbook, io.BytesIO(raw), read_only=True, data_only=True)
            except Exception:
                raise HTTPException(status_code=400, detail="File Excel tidak bisa dibaca. Gunakan template dari tombol Unduh Template")
            ws = wb["Produk"] if "Produk" in wb.sheetnames else wb.worksheets[0]
            rows, pmap = read_sheet(ws.iter_rows(values_only=True), COLS, ALIASES)
            if "Variasi" in wb.sheetnames:
                vrows, vmap = read_sheet(wb["Variasi"].iter_rows(values_only=True), VCOLS)
        if not any(m["field"] for m in pmap) and not vrows:
            raise HTTPException(status_code=400, detail="Tidak ada kolom yang dikenali. Gunakan template dari tombol Unduh Template")
        if not rows and not vrows:
            raise HTTPException(status_code=400, detail="Tidak ada data produk di file")
        found = {m["field"] for m in pmap if m["field"]}
        missing = [FIELD_LABEL[k] for k, alts in REQUIRED_NEW if not found & set(alts)]
        columns = [{"sheet": "Produk", **m} for m in pmap] + [{"sheet": "Variasi", **m} for m in vmap]
        if len(rows) + len(vrows) > MAX_ROWS:
            raise HTTPException(status_code=400, detail=f"Maksimal {MAX_ROWS} baris per impor")
        store = await scope(ctx, store_id)
        cats, by_id = await cat_maps()
        await load_parents()
        report, counts = [], {"update": 0, "same": 0, "create": 0, "draft": 0, "skip": 0}

        def add(n, name, action, msg=""):
            counts[action] += 1
            report.append({"row": n, "name": name, "action": action, "message": msg})

        seen = set()
        for n, d in rows:
            pid = str(d.get("product_id", "")).strip()
            if isinstance(d.get("product_id"), float):
                pid = str(int(d["product_id"]))
            name = str(d.get("name", "")).strip()
            if str(d.get("sku", "")).upper().startswith("CONTOH"):
                add(n, name, "skip", "Baris contoh dari template dilewati (hapus atau ganti SKU-nya)")
                continue
            if _norm(d.get("type")) in ("variation", "variasi"):
                add(n, name, "skip", "Baris variasi dari website dilewati — atur variasi lewat Ubah Produk atau sheet Variasi")
                continue
            if pid:
                if pid.isdigit() and not await db.products.find_one({"product_id": pid, "store_id": store["store_id"]}, {"_id": 1}):
                    pid = f"pgs-{pid}"  # website (WooCommerce) ID -> product imported from the website
                if pid in seen:
                    add(n, name, "skip", "ID produk muncul dua kali di file")
                    continue
                seen.add(pid)
                p = await db.products.find_one({"product_id": pid, "store_id": store["store_id"]}, {"_id": 0})
                if not p:
                    add(n, name, "skip", "ID produk tidak ditemukan di toko ini")
                    continue
                base = form_of(p)
                if base["variants_enabled"]:
                    d = {k: v for k, v in d.items() if k not in ("price", "discount_price", "stock")}
                f, errs = apply_patch(base, d, cats, by_id)
                if f.get("tier_prices") and (f["discount_price"] or f["price"]) != (base["discount_price"] or base["price"]):
                    f["tier_prices"] = scale_tiers(f["tier_prices"], base["discount_price"] or base["price"], f["discount_price"] or f["price"])
                try:
                    form = ProductForm(**f)
                except ValidationError as e:
                    errs.append(e.errors()[0]["msg"])
                if not errs:
                    changed = {k for k in f if f[k] != base.get(k)}
                    if not changed:
                        add(n, form.name, "same")
                        continue
                    # only complain about what this row changes (old catalogue data may be incomplete, e.g. no weight)
                    owns = lambda k: k.split(".")[0] in changed or (k == "dimensions" and changed & {"length_cm", "width_cm", "height_cm"}) \
                        or (k == "discount_price" and "price" in changed)
                    errs = [m for k, m in (await validate(db, form)).items() if owns(k)]
                if errs:
                    add(n, name or p["name"], "skip", "; ".join(errs[:3]))
                    continue
                if commit:
                    doc = to_product(form, store)
                    if doc["stock"] > p.get("stock", 0):
                        doc["restocked_at"] = _now()
                    await db.products.update_one({"product_id": pid}, {"$set": doc})
                    await history.record(db, ctx["user"], store["store_id"], p, history.snap(p), history.snap({**p, **doc}), "import")
                    await product_notify.on_info(db, p, doc)
                add(n, form.name, "update")
            elif not name:
                add(n, "(tanpa nama)", "skip", "Nama produk kosong, baris dilewati")
            else:
                f, errs = apply_patch(ProductForm().model_dump(), d, cats)
                try:
                    form = ProductForm(**f)
                except ValidationError as e:
                    add(n, name, "skip", e.errors()[0]["msg"])
                    continue
                problems = errs + list((await validate(db, form)).values())
                if not problems:
                    if commit:
                        pid = f"sp_{uuid.uuid4().hex[:10]}"
                        new_doc = {**to_product(form, store), "product_id": pid, "rating": 0, "sold": 0, "views": 0,
                                   "created_at": _now(), "published_at": _now()}
                        await db.products.insert_one(new_doc)
                        await product_notify.on_new(db, new_doc)
                    add(n, form.name, "create")
                else:
                    if commit:
                        await db.product_drafts.insert_one({"draft_id": f"dr_{uuid.uuid4().hex[:10]}", "owner": owner_key(ctx), "product_id": None,
                                                            "store_id": store["store_id"], "data": form.model_dump(), "updated_at": _now()})
                    note = "Produk bervariasi dari website — lengkapi variasi & harga di aplikasi. " if _norm(d.get("type")) in ("variable", "bervariasi") else ""
                    add(n, form.name or "(tanpa nama)", "draft", note + "Disimpan sebagai draft: " + "; ".join(problems[:3]))

        # variant sheet: price / stock / sku / active per existing variant
        by_product: dict = {}
        for n, d in vrows:
            by_product.setdefault(str(d.get("product_id", "")).strip(), []).append((n, d))
        for pid, items in by_product.items():
            p = await db.products.find_one({"product_id": pid, "store_id": store["store_id"]}, {"_id": 0}) if pid else None
            if not p or not p.get("variants"):
                for n, d in items:
                    add(n, str(d.get("name", "")), "skip", "Produk bervariasi dengan ID ini tidak ditemukan")
                continue
            form = ProductForm(**form_of(p))
            rows_by_id = {r.variant_id: r for r in form.variants}
            ok = []
            for n, d in items:
                r = rows_by_id.get(str(d.get("variant_id", "")).strip())
                label = f"{p['name']} · {d.get('name', '')}"
                if not r:
                    add(n, label, "skip", "ID variasi tidak ditemukan")
                    continue
                try:
                    price = _int(d["price"]) if "price" in d else r.price
                    stock = min(999999, _int(d["stock"])) if "stock" in d else r.stock
                except ValueError:
                    add(n, label, "skip", "Harga/stok harus angka")
                    continue
                active = _norm(d["active"]) not in ("tidak", "no", "nonaktif", "0") if "active" in d else r.active
                if active and price < 100:
                    add(n, label, "skip", "Harga minimal Rp100")
                    continue
                r.price, r.stock, r.active = price, stock, active
                if "sku" in d:
                    r.sku = str(d["sku"]).strip()[:40]
                ok.append((n, label))
            if ok and not any(r.active for r in form.variants):
                for n, label in ok:
                    add(n, label, "skip", "Minimal 1 variasi harus aktif")
                continue
            if ok and commit:
                doc = to_product(form, store)
                upd = {k: doc[k] for k in ("price", "original_price", "discount", "stock", "in_stock", "variants", "updated_at")}
                if upd["stock"] > p.get("stock", 0):
                    upd["restocked_at"] = _now()
                await db.products.update_one({"product_id": pid}, {"$set": upd})
                await history.record(db, ctx["user"], store["store_id"], p, history.snap(p), history.snap({**p, **upd}), "import")
            for n, label in ok:
                add(n, label, "update")  # variant rows: counted as update even when equal
        if commit and (counts["update"] or counts["create"] or counts["draft"]):
            await log_activity(ctx["user"]["user_id"], "store",
                               f"Impor Excel: {counts['create']} baru, {counts['update']} diubah, {counts['draft']} draft")
        report.sort(key=lambda r: r["row"])
        return {"committed": commit, "counts": counts, "rows": report[:MAX_ROWS], "columns": columns, "missing": missing,
                "format": "csv" if fname.endswith(".csv") else "xlsx"}
