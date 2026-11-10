"""Seller Center product editor: drafts, media upload (photos + video), variants, publish with full validation.

Used by branch admins and marketplace sellers (their own store) and by the Super Admin (any active store)."""
import itertools
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

import catalog_master
import history
import product_notify
import seller
import storage
from pricing import CUSTOMER_TYPE_LABELS, CUSTOMER_TYPES, MAX_TIERS, clean_tiers
from shipping import is_cargo

log = logging.getLogger(__name__)
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
MAX_IMAGE, MAX_VIDEO = 8 * 1024 * 1024, 50 * 1024 * 1024
MAX_IMAGES, MAX_COMBOS = 12, 100
SPEC_KEYS = ("material", "color", "size", "dimensions", "weight", "origin_country", "warranty", "extra")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class VariantOption(BaseModel):
    name: str = Field(default="", max_length=20)
    values: List[str] = Field(default=[], max_length=20)


class VariantRow(BaseModel):
    variant_id: str = ""
    values: List[str] = []
    price: int = Field(default=0, ge=0)
    stock: int = Field(default=0, ge=0, le=999999)
    sku: str = Field(default="", max_length=40)
    image: str = ""
    active: bool = True


class TierRow(BaseModel):
    min_qty: int = Field(default=1, ge=1, le=99999)
    price: int = Field(default=0, ge=0)


class ProductForm(BaseModel):
    """Everything is optional for a draft; publish runs `validate()`."""
    name: str = Field(default="", max_length=150)
    category: str = ""
    subcategory: str = ""
    brand: str = Field(default="", max_length=60)
    sku: str = Field(default="", max_length=40)
    barcode: str = Field(default="", max_length=40)
    condition: str = Field(default="new", pattern="^(new|used)$")
    showcase: str = Field(default="", max_length=40)
    status: str = Field(default="active", pattern="^(active|inactive)$")
    description: str = Field(default="", max_length=10000)
    images: List[str] = Field(default=[], max_length=MAX_IMAGES)
    video: str = ""
    price: int = Field(default=0, ge=0)  # harga normal
    discount_price: int = Field(default=0, ge=0)  # harga diskon (0 = tidak ada)
    stock: int = Field(default=0, ge=0, le=999999)
    min_order: int = Field(default=1, ge=1, le=9999)
    max_order: int = Field(default=0, ge=0, le=9999)  # 0 = tanpa batas
    low_stock_alert: int = Field(default=0, ge=0, le=99999)
    variants_enabled: bool = False
    variant_options: List[VariantOption] = Field(default=[], max_length=3)
    variants: List[VariantRow] = Field(default=[], max_length=MAX_COMBOS)
    # Tahap 2: specifications + shipping
    specs: Dict[str, str] = {}
    weight_grams: int = Field(default=0, ge=0, le=500000)
    weight_estimated: bool = False  # berat hasil perkiraan otomatis, belum dicek pemilik
    dims_estimated: bool = False  # ukuran dus hasil perkiraan otomatis
    length_cm: int = Field(default=0, ge=0, le=500)
    width_cm: int = Field(default=0, ge=0, le=500)
    height_cm: int = Field(default=0, ge=0, le=500)
    couriers: List[str] = Field(default=[], max_length=20)  # empty = every courier of the store
    ship_regular: bool = True
    ship_cargo: bool = False
    preorder: bool = False
    preorder_days: int = Field(default=0, ge=0, le=90)
    processing_days: int = Field(default=1, ge=1, le=30)
    # SEO
    seo_title: str = Field(default="", max_length=70)
    meta_description: str = Field(default="", max_length=160)
    keywords: List[str] = Field(default=[], max_length=10)
    # harga grosir: rupiah per tingkat jumlah beli, per kategori pelanggan
    tier_prices: Dict[str, List[TierRow]] = {}

    @field_validator("tier_prices")
    @classmethod
    def _tiers(cls, v: Dict[str, List["TierRow"]]) -> Dict[str, List["TierRow"]]:
        return {k: rows[:MAX_TIERS] for k, rows in v.items() if k in CUSTOMER_TYPES}

    @field_validator("specs")
    @classmethod
    def _specs(cls, v: Dict[str, str]) -> Dict[str, str]:
        return {k: str(x).strip()[:300] for k, x in v.items() if k in SPEC_KEYS and str(x).strip()}


class DraftIn(BaseModel):
    draft_id: Optional[str] = None
    product_id: Optional[str] = None  # editing an existing product
    store_id: Optional[str] = None  # super admin: target store
    data: ProductForm


class PublishIn(DraftIn):
    pass


def plain_len(md: str) -> int:
    """Length of the description without formatting marks."""
    return len(re.sub(r"[*_#>`\-]|^\d+\.\s", "", md, flags=re.M).strip())


def combos(options: List[VariantOption]) -> List[List[str]]:
    groups = [o.values for o in options if o.values]
    return [list(c) for c in itertools.product(*groups)] if groups else []


async def canonical_brand(db, brand: str, create: bool = True) -> str:
    """Excel import: reuse the spelling of a listed brand ("advance" -> "Advance"); a new one is added to the brand list
    (only when the import is saved, not in its preview)."""
    if not create:
        hit = await catalog_master.find_brand(db, brand or "")
        return hit["name"] if hit else (brand or "").strip()
    return await catalog_master.ensure_brand(db, brand)


async def validate(db, f: ProductForm) -> dict:
    """Field -> message, same rules as the app's form."""
    e: dict = {}
    if len(f.name.strip()) < 5:
        e["name"] = "Nama produk wajib diisi (min. 5 karakter)"
    cat = await db.categories.find_one({"category_id": f.category}) if f.category else None
    if not cat:
        e["category"] = "Kategori wajib dipilih"
    elif f.subcategory and not await db.categories.find_one({"category_id": f.subcategory, "parent": f.category}):
        e["subcategory"] = "Subkategori tidak sesuai kategori"
    if not f.images:
        e["images"] = "Minimal 1 foto produk"
    n = plain_len(f.description)
    if n < 30:
        e["description"] = f"Deskripsi minimal 30 karakter (sekarang {n})"
    if f.max_order and f.max_order < f.min_order:
        e["max_order"] = "Maksimum pembelian harus ≥ minimum pembelian"
    if f.variants_enabled:
        opts = [o for o in f.variant_options if o.name.strip() or o.values]
        if not opts:
            e["variants"] = "Tambahkan minimal 1 jenis variasi beserta pilihannya"
        for i, o in enumerate(opts):
            vals = [v.strip() for v in o.values]
            if not o.name.strip():
                e[f"variant_options.{i}"] = "Nama variasi wajib diisi"
            elif not vals or any(not v for v in vals):
                e[f"variant_options.{i}"] = f"Isi pilihan untuk {o.name}"
            elif len({v.lower() for v in vals}) != len(vals):
                e[f"variant_options.{i}"] = f"Pilihan {o.name} tidak boleh sama"
        active = [r for r in f.variants if r.active]
        if not active and "variants" not in e:
            e["variants"] = "Minimal 1 variasi aktif"
        for r in f.variants:
            if r.active and r.price < 100:
                e[f"variant.{'/'.join(r.values)}.price"] = "Harga minimal Rp100"
    else:
        if f.price < 100:
            e["price"] = "Harga harus lebih dari 0 (min. Rp100)"
        if f.discount_price and f.discount_price >= f.price:
            e["discount_price"] = "Harga diskon harus lebih kecil dari harga normal"
    if f.weight_grams < 1:
        e["weight_grams"] = "Berat produk wajib diisi (gram, lebih dari 0)"
    dims = [f.length_cm, f.width_cm, f.height_cm]
    if any(dims) and not all(dims):
        e["dimensions"] = "Isi panjang, lebar, dan tinggi (atau kosongkan semuanya)"
    if not f.ship_regular and not f.ship_cargo:
        e["shipping"] = "Pilih minimal satu jenis pengiriman (reguler atau kargo)"
    if f.preorder and not 1 <= f.preorder_days <= 90:
        e["preorder_days"] = "Lama pre-order 1–90 hari"
    if not f.variants_enabled:
        base = f.discount_price or f.price
        for t, rows in f.tier_prices.items():
            qs = [r.min_qty for r in rows]
            label = CUSTOMER_TYPE_LABELS[t]
            if len(set(qs)) != len(qs):
                e[f"tiers.{t}"] = f"{label}: jumlah beli tiap tingkat tidak boleh sama"
            elif any(r.price < 100 for r in rows):
                e[f"tiers.{t}"] = f"{label}: harga tiap tingkat minimal Rp100"
            else:
                srt = sorted(rows, key=lambda r: r.min_qty)
                start = [r.price for r in srt if r.min_qty == 1] or ([base] if t == "langsung" else [])
                prices = start + [r.price for r in srt if r.min_qty > 1]
                if any(b > a for a, b in zip(prices, prices[1:])):
                    e[f"tiers.{t}"] = f"{label}: harga tingkat dengan jumlah lebih banyak tidak boleh lebih mahal"
    return e


def to_product(f: ProductForm, store: dict) -> dict:
    """Form -> products document fields (buyers see the active variants only)."""
    rows = []
    if f.variants_enabled:
        for r in f.variants:
            name = " / ".join(r.values)
            rows.append({"variant_id": r.variant_id or f"v_{uuid.uuid4().hex[:8]}", "values": r.values, "name": name,
                         "price": r.price, "stock": r.stock, "sku": r.sku.strip(), "image": r.image, "active": r.active})
    active = [r for r in rows if r["active"]]
    if active:
        price = min(r["price"] for r in active)
        orig, stock = price, sum(r["stock"] for r in active)
    else:
        price = f.discount_price or f.price
        orig, stock = f.price, f.stock
    return {
        "name": f.name.strip(), "description": f.description.strip(), "category": f.category,
        "categories": [c for c in (f.category, f.subcategory) if c], "subcategory": f.subcategory,
        "brand": f.brand.strip(), "sku": f.sku.strip(), "barcode": f.barcode.strip(), "condition": f.condition, "showcase": f.showcase.strip(),
        "status": f.status, "images": f.images, "image": f.images[0] if f.images else "", "video": f.video,
        "price": price, "original_price": orig, "discount": round((orig - price) * 100 / orig) if orig > price else 0,
        "stock": stock, "in_stock": stock > 0, "min_order": f.min_order, "max_order": f.max_order,
        "low_stock_alert": f.low_stock_alert,
        "variant_options": [o.model_dump() for o in f.variant_options] if rows else [], "variants": rows,
        "specs": f.specs, "weight_grams": f.weight_grams, "weight_estimated": f.weight_estimated and f.weight_grams > 0, "length_cm": f.length_cm, "width_cm": f.width_cm, "height_cm": f.height_cm,
        "dims_estimated": f.dims_estimated and f.length_cm > 0,
        "couriers": f.couriers, "ship_regular": f.ship_regular, "ship_cargo": f.ship_cargo,
        "preorder": f.preorder, "preorder_days": f.preorder_days if f.preorder else 0, "processing_days": f.processing_days,
        "seo_title": f.seo_title.strip(), "meta_description": f.meta_description.strip(),
        "keywords": list(dict.fromkeys(k.strip().lower()[:40] for k in f.keywords if k.strip())),
        "tier_prices": {} if rows else clean_tiers({t: [r.model_dump() for r in v] for t, v in f.tier_prices.items()}),
        "store_id": store["store_id"], "store_name": store["name"], "updated_at": _now(),
    }


def to_form(p: dict) -> dict:
    """products document -> form data for editing."""
    has_v = bool(p.get("variants"))
    return ProductForm(
        name=p.get("name", ""), category=p.get("category", ""), subcategory=p.get("subcategory", ""),
        brand=p.get("brand", ""), sku=p.get("sku", ""), barcode=p.get("barcode", ""), condition=p.get("condition", "new"), showcase=p.get("showcase", ""),
        status=p.get("status", "active"), description=p.get("description", "")[:10000],
        images=(p.get("images") or ([p["image"]] if p.get("image") else []))[:MAX_IMAGES], video=p.get("video", ""),
        price=p.get("original_price") or p.get("price", 0),
        discount_price=p["price"] if p.get("original_price", 0) > p.get("price", 0) else 0,
        stock=min(p.get("stock", 0), 999999), min_order=p.get("min_order", 1), max_order=p.get("max_order", 0),
        low_stock_alert=p.get("low_stock_alert", 0), variants_enabled=has_v,
        variant_options=p.get("variant_options", []) if has_v else [],
        variants=[VariantRow(**{k: v.get(k) for k in VariantRow.model_fields if k in v}) for v in p.get("variants", [])],
        specs=p.get("specs") or {}, weight_grams=min(p.get("weight_grams") or 0, 500000), weight_estimated=bool(p.get("weight_estimated")),
        length_cm=p.get("length_cm") or 0, width_cm=p.get("width_cm") or 0, height_cm=p.get("height_cm") or 0,
        dims_estimated=bool(p.get("dims_estimated")),
        couriers=p.get("couriers") or [], ship_regular=p.get("ship_regular", True), ship_cargo=p.get("ship_cargo", False),
        preorder=p.get("preorder", False), preorder_days=p.get("preorder_days") or 0, processing_days=p.get("processing_days") or 1,
        seo_title=(p.get("seo_title") or "")[:70], meta_description=(p.get("meta_description") or "")[:160], keywords=(p.get("keywords") or [])[:10],
        tier_prices=clean_tiers(p.get("tier_prices") or {}),
    ).model_dump()


def register(api, db, *, get_current_user, log_activity, origin_label):

    async def actor(user=Depends(get_current_user)) -> dict:
        """Super admin edits any store; everyone else edits their own active store."""
        if user.get("role") == "admin":
            return {"user": user, "admin": True, "store": None}
        s = await db.stores.find_one({"owner_id": user["user_id"]}, {"_id": 0})
        if not s or s["status"] != "active":
            raise HTTPException(status_code=403, detail="Toko Anda belum aktif")
        return {"user": user, "admin": False, "store": s}

    async def target_store(ctx: dict, store_id: Optional[str]) -> dict:
        if not ctx["admin"]:
            return ctx["store"]
        s = await db.stores.find_one({"store_id": store_id or seller.PGS_STORE_ID, "status": "active"}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=400, detail="Toko tujuan tidak ditemukan")
        return s

    def owner_key(ctx: dict) -> str:
        return "admin" if ctx["admin"] else ctx["store"]["store_id"]

    @api.get("/product-editor/context")
    async def editor_context(ctx=Depends(actor)):
        if ctx["admin"]:
            stores = await db.stores.find({"status": "active"}, {"_id": 0, "store_id": 1, "name": 1}).to_list(500)
            stores.sort(key=lambda s: (s["store_id"] not in seller.OFFICIAL_IDS, s["name"]))
        else:
            stores = [{"store_id": ctx["store"]["store_id"], "name": ctx["store"]["name"]}]
        ids = [s["store_id"] for s in stores]
        showcases = sorted({s for s in await db.products.distinct("showcase", {"store_id": {"$in": ids}}) if s})
        shipping = {}  # per store: its active couriers (marked cargo/regular) + shipping origin
        for s in await db.stores.find({"store_id": {"$in": ids[:50]}}, {"_id": 0}).to_list(50):
            shipping[s["store_id"]] = {
                "origin": await origin_label(s["store_id"]) or s.get("address") or "",
                "couriers": [{"code": c["code"], "name": c["name"], "cargo": is_cargo(c)} for c in seller.couriers_of(s)
                             if c.get("active", True) and c["code"] != "pickup"],
                "pickup": any(c["code"] == "pickup" and c.get("active", True) for c in seller.couriers_of(s)),
            }
        return {"admin": ctx["admin"], "stores": stores, "showcases": showcases, "shipping": shipping, "limits": {
            "images": MAX_IMAGES, "image_mb": MAX_IMAGE // 1048576, "video_mb": MAX_VIDEO // 1048576, "combos": MAX_COMBOS}}

    @api.post("/product-editor/upload")
    async def editor_upload(file: UploadFile = File(...), ctx=Depends(actor)):
        ctype = (file.content_type or "").lower()
        if ctype not in IMAGE_TYPES | VIDEO_TYPES:
            raise HTTPException(status_code=400, detail="Format harus JPG, PNG, WEBP (foto) atau MP4, MOV (video)")
        is_video = ctype in VIDEO_TYPES
        limit = MAX_VIDEO if is_video else MAX_IMAGE
        data = await file.read(limit + 1)  # never read more than the limit allows
        if len(data) > limit:
            raise HTTPException(status_code=400, detail=f"Ukuran {'video' if is_video else 'foto'} maksimal {(MAX_VIDEO if is_video else MAX_IMAGE) // 1048576} MB")
        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "video/mp4": "mp4", "video/quicktime": "mov"}[ctype]
        path = f"{storage.APP_NAME}/products/{owner_key(ctx)}/{uuid.uuid4().hex}.{ext}"
        try:
            res = await run_in_threadpool(storage.put_object, path, data, ctype)
        except Exception:
            log.exception("product editor upload failed")
            raise HTTPException(status_code=502, detail="Upload gagal, coba lagi")
        await db.uploads.insert_one({"storage_path": res["path"], "owner_id": ctx["user"]["user_id"], "content_type": ctype,
                                     "original_filename": file.filename, "size": len(data), "is_deleted": False, "created_at": _now()})
        return {"url": f"/api/files/{res['path']}", "kind": "video" if is_video else "image"}

    # ---------------- drafts ----------------
    def draft_out(d: dict) -> dict:
        return {k: d.get(k) for k in ("draft_id", "product_id", "store_id", "data", "updated_at")}

    @api.get("/product-editor/drafts")
    async def list_drafts(ctx=Depends(actor)):
        docs = await db.product_drafts.find({"owner": owner_key(ctx)}, {"_id": 0}).sort("updated_at", -1).to_list(50)
        return [draft_out(d) for d in docs]

    @api.get("/product-editor/drafts/{draft_id}")
    async def get_draft(draft_id: str, ctx=Depends(actor)):
        d = await db.product_drafts.find_one({"draft_id": draft_id, "owner": owner_key(ctx)}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Draft tidak ditemukan")
        return draft_out(d)

    @api.post("/product-editor/drafts")
    async def save_draft(body: DraftIn, ctx=Depends(actor)):
        store = await target_store(ctx, body.store_id)
        did = body.draft_id or f"dr_{uuid.uuid4().hex[:10]}"
        doc = {"draft_id": did, "owner": owner_key(ctx), "product_id": body.product_id, "store_id": store["store_id"],
               "data": body.data.model_dump(), "updated_at": _now()}
        await db.product_drafts.update_one({"draft_id": did, "owner": owner_key(ctx)}, {"$set": doc}, upsert=True)
        return draft_out(doc)

    @api.delete("/product-editor/drafts/{draft_id}")
    async def delete_draft(draft_id: str, ctx=Depends(actor)):
        await db.product_drafts.delete_one({"draft_id": draft_id, "owner": owner_key(ctx)})
        return {"ok": True}

    # ---------------- existing product ----------------
    async def editable(product_id: str, ctx: dict) -> dict:
        q = {"product_id": product_id} if ctx["admin"] else {"product_id": product_id, "store_id": ctx["store"]["store_id"]}
        p = await db.products.find_one(q, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        return p

    parents: dict = {}

    async def load_parents() -> None:
        parents.clear()
        parents.update({c["category_id"]: c["parent"] for c in await db.categories.find({"parent": {"$nin": [None, ""]}}, {"category_id": 1, "parent": 1}).to_list(5000)})

    def form_of(p: dict) -> dict:
        """to_form + imported products store the subcategory as their category (call load_parents first)."""
        data = to_form(p)
        if parents.get(data["category"]):
            data["category"], data["subcategory"] = parents[data["category"]], data["category"]
        return data

    @api.get("/product-editor/products/{product_id}")
    async def get_for_edit(product_id: str, ctx=Depends(actor)):
        p = await editable(product_id, ctx)
        await load_parents()
        return {"product_id": product_id, "store_id": p.get("store_id"), "data": form_of(p)}

    @api.post("/product-editor/products/{product_id}/duplicate")
    async def duplicate(product_id: str, ctx=Depends(actor)):
        """Copy a product into a new draft (no SKU, new variant ids) so the seller reviews it before publishing."""
        p = await editable(product_id, ctx)
        await load_parents()
        data = form_of(p)
        data["name"] = f"{data['name']} (Salinan)"[:150]
        data["sku"], data["barcode"] = "", ""
        for v in data["variants"]:
            v["variant_id"], v["sku"] = "", ""
        doc = {"draft_id": f"dr_{uuid.uuid4().hex[:10]}", "owner": owner_key(ctx), "product_id": None,
               "store_id": p.get("store_id") or seller.PGS_STORE_ID, "data": data, "updated_at": _now()}
        await db.product_drafts.insert_one({**doc})
        await log_activity(ctx["user"]["user_id"], "store", f"Menduplikat produk '{p.get('name', '')}'")
        return draft_out(doc)

    # ---------------- publish ----------------
    @api.post("/product-editor/publish")
    async def publish(body: PublishIn, ctx=Depends(actor)):
        f = body.data
        if f.variants_enabled:  # rows must match the option combinations exactly
            want = {tuple(c) for c in combos(f.variant_options)}
            if len(want) > MAX_COMBOS:
                raise HTTPException(status_code=400, detail=f"Kombinasi variasi maksimal {MAX_COMBOS}")
            f.variants = [r for r in f.variants if tuple(r.values) in want]
        errors = await validate(db, f)
        if errors:
            raise HTTPException(status_code=422, detail={"message": "Lengkapi data produk sebelum dipublikasikan", "errors": errors})
        if body.product_id:
            old = await editable(body.product_id, ctx)
            store = await db.stores.find_one({"store_id": old["store_id"]}, {"_id": 0})
        else:
            store = await target_store(ctx, body.store_id)
        # courier choices must exist at the store; cargo only when the store has a cargo courier
        active = [c for c in seller.couriers_of(store) if c.get("active", True) and c["code"] != "pickup"]
        f.couriers = [c for c in dict.fromkeys(f.couriers) if c in {x["code"] for x in active}]
        if f.ship_cargo and not any(is_cargo(c) for c in active):
            f.ship_cargo = False
            if not f.ship_regular:
                raise HTTPException(status_code=422, detail={"message": "Toko belum punya kurir kargo", "errors": {
                    "shipping": "Toko belum punya kurir kargo. Aktifkan pengiriman reguler atau tambahkan kurir kargo di menu Pengiriman"}})
        if f.brand.strip():  # the editor picks from the brand list (Master Merek), no free text
            hit = await catalog_master.find_brand(db, f.brand)
            if not hit:
                raise HTTPException(status_code=422, detail={"message": "Merek tidak ada di daftar", "errors": {
                    "brand": "Pilih merek dari daftar. Merek baru dibuat Super Admin di menu Merek & Kategori"}})
            f.brand = hit["name"]
        if body.product_id:  # the estimate mark only survives while the value itself is unchanged (server decides, not the client)
            same_w = f.weight_grams == (old.get("weight_grams") or 0)
            same_d = [f.length_cm, f.width_cm, f.height_cm] == [old.get(k) or 0 for k in ("length_cm", "width_cm", "height_cm")]
            f.weight_estimated = same_w and f.weight_estimated and bool(old.get("weight_estimated"))
            f.dims_estimated = same_d and f.dims_estimated and bool(old.get("dims_estimated"))
        else:
            f.weight_estimated = f.dims_estimated = False
        if body.product_id:
            doc = to_product(f, store)
            await db.products.update_one({"product_id": body.product_id}, {"$set": doc})
            await history.record(db, ctx["user"], old["store_id"], old, history.snap(old), history.snap({**old, **doc}), "editor")
            await product_notify.on_info(db, old, doc)
            pid, action = body.product_id, "Mengubah"
        else:
            pid = f"sp_{uuid.uuid4().hex[:10]}"
            doc = {**to_product(f, store), "product_id": pid, "rating": 0, "sold": 0, "views": 0, "created_at": _now(), "published_at": _now()}
            if not ctx["admin"] and store["store_id"] in seller.OFFICIAL_IDS:  # branch admin: only buyers of this branch see it
                doc["only_branch"] = store["store_id"]
            await db.products.insert_one(doc)
            await product_notify.on_new(db, doc)
            action = "Menambah"
        if body.draft_id:
            await db.product_drafts.delete_one({"draft_id": body.draft_id, "owner": owner_key(ctx)})
        await log_activity(ctx["user"]["user_id"], "store", f"{action} produk '{f.name.strip()}'")
        return {"product_id": pid, "store_id": store["store_id"], "status": f.status}

    import product_bulk  # imports this module's form helpers
    product_bulk.register(api, db, actor=actor, target_store=target_store, editable=editable, owner_key=owner_key,
                          form_of=form_of, load_parents=load_parents, log_activity=log_activity)
    import category_suggest
    import weight_estimate
    category_suggest.register(api, db, actor=actor, target_store=target_store, log_activity=log_activity)  # before {kind} routes
    weight_estimate.register(api, db, actor=actor, target_store=target_store, log_activity=log_activity)
