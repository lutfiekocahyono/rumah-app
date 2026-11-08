"""Homepage marketing: banners, flash sale, vouchers, home settings and banner image uploads (public + admin)."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, File, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

import promo
import storage


logger = logging.getLogger(__name__)


class Banner(BaseModel):
    banner_id: str
    title: str
    subtitle: str = ""
    image: str
    link_type: str = "none"
    link_value: str = ""
    order: int = 0
    active: bool = True


class BannerIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    subtitle: str = Field(default="", max_length=120)
    image: str = Field(min_length=1)
    link_type: str = Field(default="none", pattern="^(none|category|product|search)$")
    link_value: str = ""
    order: int = 0
    active: bool = True


class FlashItemIn(BaseModel):
    product_id: str
    flash_price: int = Field(ge=1)


class FlashSaleIn(BaseModel):
    title: str = Field(default="Flash Sale", min_length=1, max_length=40)
    active: bool = True
    ends_at: datetime
    items: List[FlashItemIn] = []


class VoucherIn(BaseModel):
    code: str = Field(pattern="^[A-Za-z0-9]{3,20}$")
    title: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=120)
    mode: str = Field(default="percent", pattern="^(percent|rupiah)$")
    value: float = Field(gt=0)
    max_discount: int = Field(default=0, ge=0)
    min_purchase: int = Field(default=0, ge=0)
    quota: int = Field(default=0, ge=0)
    ends_at: Optional[datetime] = None
    active: bool = True
    show_on_home: bool = True


class VoucherApplyIn(BaseModel):
    code: str = Field(min_length=1)


class FreeShippingIn(BaseModel):
    enabled: bool = True
    title: str = Field(default="Gratis Ongkir", max_length=40)
    subtitle: str = Field(default="", max_length=120)
    min_purchase: int = Field(default=0, ge=0)


class HomeSettingsIn(BaseModel):
    free_shipping: FreeShippingIn
    recommend_mode: str = Field(pattern="^(personal|random)$")


def _voucher_out(v: dict, claimed: bool = False) -> dict:
    out = {k: v.get(k) for k in ("code", "title", "description", "mode", "value", "max_discount",
                                  "min_purchase", "quota", "used", "active", "show_on_home")}
    out["ends_at"] = promo.aware(v.get("ends_at"))
    out["claimed"] = claimed
    return out


def _voucher_live(v: dict) -> bool:
    ends = promo.aware(v.get("ends_at"))
    return bool(v.get("active")) and (not ends or ends > promo.now()) and (not v.get("quota") or v.get("used", 0) < v["quota"])


def _check_voucher_in(body: VoucherIn) -> dict:
    if body.mode == "percent" and body.value > 100:
        raise HTTPException(status_code=400, detail="Potongan persen maksimal 100%")
    return {**body.model_dump(), "code": body.code.upper(), "ends_at": promo.aware(body.ends_at)}


def register(api, db, *, require_admin, get_owner, get_optional_owner, get_optional_user,
             product_out, load_cart_detailed, broadcast_promo) -> None:
    # --- public ---
    @api.get("/banners", response_model=List[Banner])
    async def list_banners():
        return [Banner(**d) for d in await db.banners.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(20)]

    @api.get("/home-settings")
    async def home_settings():
        return await promo.get_home(db)

    @api.get("/flash-sale")
    async def flash_sale(user=Depends(get_optional_user)):
        flash = await promo.active_flash(db)
        if not flash:
            return {"active": False, "items": []}
        ids = list(flash["prices"].keys())
        docs = {d["product_id"]: d for d in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(100)}
        ctype = (user or {}).get("customer_type", "langsung")
        items = [product_out(docs[i], ctype, flash) for i in ids if i in docs]
        return {"active": True, "title": flash["title"], "ends_at": flash["ends_at"], "items": items}

    @api.get("/vouchers")
    async def list_vouchers(owner: Optional[str] = Depends(get_optional_owner)):
        docs = await db.vouchers.find({"active": True, "show_on_home": True}, {"_id": 0}).sort("created_at", -1).to_list(50)
        claim = await db.voucher_claims.find_one({"owner": owner}) if owner else None
        mine = set((claim or {}).get("codes", []))
        return [_voucher_out(v, v["code"] in mine) for v in docs if _voucher_live(v)]

    @api.get("/vouchers/mine")
    async def my_vouchers(owner: str = Depends(get_owner)):
        claim = await db.voucher_claims.find_one({"owner": owner}) or {}
        docs = await db.vouchers.find({"code": {"$in": claim.get("codes", [])}}, {"_id": 0}).to_list(50)
        return [_voucher_out(v, True) for v in docs if _voucher_live(v)]

    @api.post("/vouchers/{code}/claim")
    async def claim_voucher(code: str, owner: str = Depends(get_owner)):
        v = await db.vouchers.find_one({"code": code.upper()})
        if not v or not _voucher_live(v):
            raise HTTPException(status_code=404, detail="Voucher tidak tersedia")
        await db.voucher_claims.update_one({"owner": owner}, {"$addToSet": {"codes": v["code"]}}, upsert=True)
        return _voucher_out(v, True)

    @api.post("/vouchers/apply")
    async def apply_voucher(body: VoucherApplyIn, owner: str = Depends(get_owner)):
        cart = await load_cart_detailed(owner)
        code = body.code.strip().upper()
        v = await db.vouchers.find_one({"code": code})
        discount, err = promo.voucher_check(v, cart.subtotal)
        if err:
            raise HTTPException(status_code=400, detail=err)
        return {"code": code, "title": v["title"], "discount": discount}

    # --- uploaded files (banner images) ---
    @api.post("/admin/upload")
    async def admin_upload(file: UploadFile = File(...), admin=Depends(require_admin)):
        if not (file.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="File harus berupa gambar")
        data = await file.read()
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran gambar maksimal 8 MB")
        ext = (file.filename or "img.jpg").rsplit(".", 1)[-1].lower()[:5] or "jpg"
        path = f"{storage.APP_NAME}/uploads/{admin['user_id']}/{uuid.uuid4().hex}.{ext}"
        try:
            res = await run_in_threadpool(storage.put_object, path, data, file.content_type)
        except Exception as exc:
            logger.exception("upload failed")
            code = getattr(getattr(exc, "response", None), "status_code", 0)
            raise HTTPException(status_code=502, detail="Kuota penyimpanan habis" if code == 402 else "Upload gagal, coba lagi")
        await db.uploads.insert_one({"storage_path": res["path"], "owner_id": admin["user_id"], "content_type": file.content_type,
                                     "original_filename": file.filename, "size": len(data), "is_deleted": False,
                                     "created_at": datetime.now(timezone.utc)})
        return {"url": f"/api/files/{res['path']}"}

    @api.get("/files/{path:path}")
    async def get_file(path: str):
        rec = await db.uploads.find_one({"storage_path": path, "is_deleted": False})
        if not rec:  # banner images are public; only files we recorded are served
            raise HTTPException(status_code=404, detail="File tidak ditemukan")
        data, ctype = await run_in_threadpool(storage.get_object, path)
        return Response(content=data, media_type=rec.get("content_type") or ctype,
                        headers={"Cache-Control": "public, max-age=604800, immutable"})

    # --- admin: banners ---
    @api.get("/admin/banners", response_model=List[Banner])
    async def admin_banners(_=Depends(require_admin)):
        return [Banner(**d) for d in await db.banners.find({}, {"_id": 0}).sort("order", 1).to_list(50)]

    @api.post("/admin/banners", response_model=Banner)
    async def admin_create_banner(body: BannerIn, _=Depends(require_admin)):
        doc = {**body.model_dump(), "banner_id": f"bn_{uuid.uuid4().hex[:10]}"}
        await db.banners.insert_one({**doc})
        return Banner(**doc)

    @api.put("/admin/banners/{banner_id}", response_model=Banner)
    async def admin_update_banner(banner_id: str, body: BannerIn, _=Depends(require_admin)):
        d = await db.banners.find_one_and_update({"banner_id": banner_id}, {"$set": body.model_dump()},
                                                 projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not d:
            raise HTTPException(status_code=404, detail="Banner tidak ditemukan")
        return Banner(**d)

    @api.delete("/admin/banners/{banner_id}")
    async def admin_delete_banner(banner_id: str, _=Depends(require_admin)):
        await db.banners.delete_one({"banner_id": banner_id})
        return {"ok": True}

    # --- admin: flash sale ---
    async def _flash_admin_view() -> dict:
        doc = await db.settings.find_one({"key": "flash_sale"}, {"_id": 0}) or {
            "title": "Flash Sale", "active": False, "ends_at": promo.now() + timedelta(days=1), "items": []}
        ids = [i["product_id"] for i in doc.get("items", [])]
        prods = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1}).to_list(100)}
        items = [{**i, **{k: prods[i["product_id"]][k] for k in ("name", "image", "price")}} for i in doc.get("items", []) if i["product_id"] in prods]
        return {"title": doc.get("title", "Flash Sale"), "active": bool(doc.get("active")), "ends_at": promo.aware(doc.get("ends_at")), "items": items}

    @api.get("/admin/flash-sale")
    async def admin_get_flash(_=Depends(require_admin)):
        return await _flash_admin_view()

    @api.put("/admin/flash-sale")
    async def admin_set_flash(body: FlashSaleIn, _=Depends(require_admin)):
        items = list({i.product_id: i.model_dump() for i in body.items}.values())
        await db.settings.update_one({"key": "flash_sale"}, {"$set": {
            "title": body.title, "active": body.active, "ends_at": promo.aware(body.ends_at), "items": items}}, upsert=True)
        return await _flash_admin_view()

    # --- admin: vouchers ---
    @api.get("/admin/vouchers")
    async def admin_vouchers(_=Depends(require_admin)):
        return [_voucher_out(v) for v in await db.vouchers.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)]

    @api.post("/admin/vouchers")
    async def admin_create_voucher(body: VoucherIn, _=Depends(require_admin)):
        doc = _check_voucher_in(body)
        if await db.vouchers.find_one({"code": doc["code"]}):
            raise HTTPException(status_code=400, detail="Kode voucher sudah dipakai")
        await db.vouchers.insert_one({**doc, "used": 0, "created_at": datetime.now(timezone.utc)})
        if doc["active"] and doc["show_on_home"]:
            await broadcast_promo(f"Voucher baru: {doc['code']}", doc["title"], "/")
        return _voucher_out({**doc, "used": 0})

    @api.put("/admin/vouchers/{code}")
    async def admin_update_voucher(code: str, body: VoucherIn, _=Depends(require_admin)):
        doc = _check_voucher_in(body)
        if doc["code"] != code.upper():
            raise HTTPException(status_code=400, detail="Kode voucher tidak bisa diubah")
        d = await db.vouchers.find_one_and_update({"code": code.upper()}, {"$set": doc}, projection={"_id": 0},
                                                  return_document=ReturnDocument.AFTER)
        if not d:
            raise HTTPException(status_code=404, detail="Voucher tidak ditemukan")
        return _voucher_out(d)

    @api.delete("/admin/vouchers/{code}")
    async def admin_delete_voucher(code: str, _=Depends(require_admin)):
        await db.vouchers.delete_one({"code": code.upper()})
        return {"ok": True}

    # --- admin: home settings (free shipping banner + recommendation mode) ---
    @api.put("/admin/home-settings")
    async def admin_set_home(body: HomeSettingsIn, _=Depends(require_admin)):
        await db.settings.update_one({"key": "home"}, {"$set": body.model_dump()}, upsert=True)
        return await promo.get_home(db)
