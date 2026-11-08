"""Seller Center Tahap 3: product list, bulk edit (price / stock / status), Excel export, template and import."""
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

from product_editor import ProductForm, to_form, to_product, validate

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
]
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
    if isinstance(v, (int, float)):
        return max(0, int(v))
    d = re.sub(r"[^\d]", "", str(v).split(",")[0])
    if not d:
        raise ValueError
    return int(d)


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
        normal = max(0, fn(f.price, v))
        disc = f.discount_price if mode == "set" else (max(0, fn(f.discount_price, v)) if f.discount_price else 0)
        if normal < 100:
            return "Harga jadi kurang dari Rp100"
        f.price, f.discount_price = normal, disc if 0 < disc < normal else 0
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
            upd = {k: doc[k] for k in ("price", "original_price", "discount", "stock", "in_stock", "variants", "updated_at")}
            if body.status:
                upd["status"] = body.status
            if upd["stock"] > p.get("stock", 0):
                upd["restocked_at"] = _now()
            await db.products.update_one({"product_id": pid}, {"$set": upd})
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

    def build_xlsx(products: list, cats: list, by_id: dict, example: bool) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Produk"
        head(ws, COLS)
        vs = wb.create_sheet("Variasi")
        head(vs, VCOLS)
        if example:
            sample_cat = next((c for c in cats if not c.get("parent")), {"name": ""})
            ws.append(["", "SKU-001", "Contoh Panci Stainless 24cm", sample_cat["name"], "", "Merek A", "baru", "aktif", "Dapur",
                       85000, 79000, 20, 1, 0, 1200, 26, 26, 14, "https://contoh.com/foto-panci.jpg",
                       "Panci stainless tebal 24 cm, cocok untuk semua jenis kompor termasuk induksi."])
        for p in products:
            f = form_of(p)
            v = bool(f["variants_enabled"])
            cat, sub = by_id.get(f["category"], {}).get("name", f["category"]), by_id.get(f["subcategory"], {}).get("name", "")
            ws.append([p["product_id"], f["sku"], f["name"], cat, sub, f["brand"], "bekas" if f["condition"] == "used" else "baru",
                       "nonaktif" if f["status"] == "inactive" else "aktif", f["showcase"],
                       None if v else f["price"], None if v or not f["discount_price"] else f["discount_price"], None if v else f["stock"],
                       f["min_order"], f["max_order"], f["weight_grams"] or None, f["length_cm"] or None, f["width_cm"] or None,
                       f["height_cm"] or None, "\n".join(f["images"]), f["description"]])
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
            "7. Maksimal 10.000 baris per file. Simpan dalam format .xlsx.",
        ]:
            g.append([line])
        g.column_dimensions["A"].width = 110
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
        data = await run_in_threadpool(build_xlsx, products, cats, by_id, template)
        name = "template-impor-produk.xlsx" if template else f"produk-{store['store_id']}-{_now():%Y%m%d}.xlsx"
        return Response(content=data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ---------------- Excel import ----------------
    def read_sheet(ws, cols) -> list:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None) or []
        lookup = {_norm(h): k for k, h in cols} | {k: k for k, _ in cols}
        idx = {i: lookup.get(_norm(h)) for i, h in enumerate(header)}
        out = []
        for n, r in enumerate(rows, start=2):
            d = {idx[i]: v for i, v in enumerate(r) if idx.get(i) and v is not None and str(v).strip() != ""}
            if d:
                out.append((n, d))
        return out

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
        for k, v in d.items():
            if k in ("product_id", "category", "subcategory"):
                continue
            if k in INT_KEYS:
                try:
                    f[k] = _int(v)
                except ValueError:
                    errs.append(f"Kolom {dict(COLS)[k].rstrip('*')} harus angka")
            elif k == "condition":
                f[k] = "used" if _norm(v) in ("bekas", "used") else "new"
            elif k == "status":
                f[k] = "inactive" if _norm(v) in ("nonaktif", "inactive", "tidak aktif") else "active"
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
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail="File harus berformat .xlsx (Excel)")
        raw = await file.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran file maksimal 10 MB")
        try:
            wb = await run_in_threadpool(load_workbook, io.BytesIO(raw), read_only=True, data_only=True)
        except Exception:
            raise HTTPException(status_code=400, detail="File Excel tidak bisa dibaca. Gunakan template dari tombol Unduh Template")
        ws = wb["Produk"] if "Produk" in wb.sheetnames else wb.worksheets[0]
        rows = read_sheet(ws, COLS)
        vrows = read_sheet(wb["Variasi"], VCOLS) if "Variasi" in wb.sheetnames else []
        if not rows and not vrows:
            raise HTTPException(status_code=400, detail="Tidak ada data produk di file")
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
            name = str(d.get("name", "")).strip()
            if pid:
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
                        await db.products.insert_one({**to_product(form, store), "product_id": pid, "rating": 0, "sold": 0, "views": 0,
                                                      "created_at": _now(), "published_at": _now()})
                    add(n, form.name, "create")
                else:
                    if commit:
                        await db.product_drafts.insert_one({"draft_id": f"dr_{uuid.uuid4().hex[:10]}", "owner": owner_key(ctx), "product_id": None,
                                                            "store_id": store["store_id"], "data": form.model_dump(), "updated_at": _now()})
                    add(n, form.name or "(tanpa nama)", "draft", "Disimpan sebagai draft: " + "; ".join(problems[:3]))

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
            for n, label in ok:
                add(n, label, "update")  # variant rows: counted as update even when equal
        if commit and (counts["update"] or counts["create"] or counts["draft"]):
            await log_activity(ctx["user"]["user_id"], "store",
                               f"Impor Excel: {counts['create']} baru, {counts['update']} diubah, {counts['draft']} draft")
        report.sort(key=lambda r: r["row"])
        return {"committed": commit, "counts": counts, "rows": report[:MAX_ROWS]}
