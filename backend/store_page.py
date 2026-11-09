"""Halaman toko tiap cabang: banner, logo, info toko, produk andalan, dan produk khusus cabang.
Admin cabang mengatur tampilan tokonya sendiri; Super Admin semua cabang."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import seller
import shop_scope
import storage
import store_qr

MAX_FEATURED = 10
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class AppearanceIn(BaseModel):
    banner: str = Field(default="", max_length=500)
    logo: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=300)
    pickup_hours: str = Field(default="", max_length=80)
    featured_ids: List[str] = Field(default=[], max_length=MAX_FEATURED)


def own_query(sid: str) -> dict:
    """Products that belong to this store only (for PGS branches: produk khusus cabang, not the shared catalog)."""
    if sid == seller.PGS_STORE_ID:
        return {"only_branch": sid, "status": {"$ne": "inactive"}}
    return {"store_id": sid, "status": {"$ne": "inactive"}}


def register(api, db, *, require_admin, get_current_user, get_optional_user, visible, apply_stock, product_out, active_flash):
    async def page_store(sid: str) -> dict:
        s = await db.stores.find_one({"store_id": sid, "status": "active"}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        return s

    def ctx_of(sid: str) -> str:
        return sid if sid in seller.OFFICIAL_IDS else seller.PGS_STORE_ID

    async def outs(docs: list, sid: str, user) -> list:
        await apply_stock(docs, ctx_of(sid))
        flash, ctype = await active_flash(db), (user or {}).get("customer_type", "langsung")
        return [product_out(d, ctype, flash, ctx_of(sid)) for d in docs]

    async def featured(s: dict, user) -> list:
        sid = s["store_id"]
        ids = s.get("featured_ids") or []
        if ids:  # chosen by the branch admin, in his order
            base = await visible(ctx_of(sid)) if sid in seller.OFFICIAL_IDS else {"store_id": sid, "status": {"$ne": "inactive"}}
            docs = {d["product_id"]: d for d in await db.products.find({**base, "product_id": {"$in": ids}}, {"_id": 0}).to_list(MAX_FEATURED)}
            docs = [docs[i] for i in ids if i in docs]
            if docs:
                return await outs(docs, sid, user), True
        # empty: best sellers among the store's own products that are in stock
        docs = await db.products.find({**own_query(sid), "stock": {"$gt": 0}}, {"_id": 0}).sort([("sold", -1), ("rating", -1)]).to_list(MAX_FEATURED)
        return await outs(docs, sid, user), False

    @api.get("/stores/{store_id}/page")
    async def store_page(store_id: str, user=Depends(get_optional_user)):
        s = await page_store(store_id)
        shop_scope.ON.set(True)  # this endpoint is only used by the store page
        out = seller.store_out(s)
        if not out["official"]:
            out.pop("phone", None)  # marketplace sellers are reached via chat
        out["banner"] = s.get("banner", "")
        # official branch: the store page lists the whole catalog of that branch; other stores: their own products
        out["product_count"] = await db.products.count_documents(await visible("all", store_id) if out["official"] else own_query(store_id))
        out["featured"], out["featured_manual"] = await featured(s, user)
        return out

    @api.get("/stores/{store_id}/categories")
    async def store_categories(store_id: str):
        """Main categories that have products priced in this PGS branch (stok 0 ikut), most products first."""
        if store_id not in seller.OFFICIAL_IDS:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        shop_scope.ON.set(True)
        cats = await db.categories.find({}, {"_id": 0}).to_list(1000)
        parent = {c["category_id"]: c.get("parent") for c in cats}

        def top(cid: str) -> str:
            seen = set()
            while parent.get(cid) and cid not in seen:
                seen.add(cid)
                cid = parent[cid]
            return cid

        counts: dict = {}
        async for d in db.products.find(await visible(store_id), {"_id": 0, "categories": 1}):
            for t in {top(c) for c in (d.get("categories") or ["lainnya"])}:
                counts[t] = counts.get(t, 0) + 1
        mains = [{**c, "count": counts[c["category_id"]]} for c in cats if not c.get("parent") and counts.get(c["category_id"])]
        return sorted(mains, key=lambda c: -c["count"])

    # ---------------- appearance editor ----------------
    @api.get("/stores/{store_id}/qr")
    async def store_qr_code(store_id: str, request: Request, format: str = "png", base: str = ""):
        """Printable QR poster of the store page (public: it only points to a public page)."""
        s = await page_store(store_id)
        if format not in ("png", "pdf"):
            raise HTTPException(status_code=400, detail="Format harus png atau pdf")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        proto = request.headers.get("x-forwarded-proto", "https")
        # the app is served on the same domain as the API; a given base is only used when it is that same host
        origin = base.rstrip("/") if base and host and host in base else f"{proto}://{host}"
        url = f"{origin}/shop/{store_id}" + (f"?toko={store_id}" if store_id in seller.OFFICIAL_IDS else "")
        logo = await store_qr.fetch_logo(s.get("logo", ""))
        data = await run_in_threadpool(store_qr.render, url, s["name"], s.get("city", ""), s.get("address", ""), logo, format)
        fname = f"QR-{s['name'].replace(' ', '-')}.{format}"
        return Response(content=data, media_type="application/pdf" if format == "pdf" else "image/png",
                        headers={"Content-Disposition": f'inline; filename="{fname}"', "Cache-Control": "no-store"})

    # ---------------- appearance editor ----------------
    async def editable(user: dict) -> list:
        if user.get("role") == "admin":
            return list(seller.OFFICIAL_IDS)
        s = await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"store_id": 1})
        if not s or s["store_id"] not in seller.OFFICIAL_IDS:
            raise HTTPException(status_code=403, detail="Tampilan toko cabang hanya untuk admin cabang PGS atau Super Admin")
        return [s["store_id"]]

    async def check(user: dict, sid: str):
        if sid not in await editable(user):
            raise HTTPException(status_code=403, detail="Anda hanya bisa mengatur tampilan toko Anda sendiri")

    async def appearance_out(sid: str) -> dict:
        s = await db.stores.find_one({"store_id": sid}, {"_id": 0}) or {}
        ids = s.get("featured_ids") or []
        names = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0, "product_id": 1, "name": 1, "image": 1}).to_list(MAX_FEATURED)}
        return {"store_id": sid, "name": s.get("name", sid), "city": s.get("city", ""),
                **{k: s.get(k, "") for k in ("banner", "logo", "description", "phone", "address", "pickup_hours")},
                "featured": [names[i] for i in ids if i in names]}

    @api.get("/store-appearance")
    async def list_appearance(user=Depends(get_current_user)):
        return [await appearance_out(sid) for sid in await editable(user)]

    @api.put("/store-appearance/{store_id}")
    async def save_appearance(store_id: str, body: AppearanceIn, user=Depends(get_current_user)):
        await check(user, store_id)
        ids = list(dict.fromkeys(body.featured_ids))
        if ids:
            base = await visible(store_id)
            found = {d["product_id"] for d in await db.products.find({**base, "product_id": {"$in": ids}}, {"product_id": 1}).to_list(MAX_FEATURED)}
            missing = [i for i in ids if i not in found]
            if missing:
                raise HTTPException(status_code=400, detail="Ada produk andalan yang tidak tersedia di cabang ini")
        upd = {**body.model_dump(exclude={"featured_ids"}), "featured_ids": ids, "appearance_updated_at": datetime.now(timezone.utc)}
        upd = {k: v.strip() if isinstance(v, str) else v for k, v in upd.items()}
        await db.stores.update_one({"store_id": store_id}, {"$set": upd})
        return await appearance_out(store_id)

    @api.post("/store-appearance/{store_id}/upload")
    async def upload_appearance(store_id: str, file: UploadFile = File(...), user=Depends(get_current_user)):
        await check(user, store_id)
        ctype = (file.content_type or "").lower()
        if ctype not in IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Format gambar harus JPG, PNG, atau WEBP")
        data = await file.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran gambar maksimal 5 MB")
        path = f"{storage.APP_NAME}/stores/{store_id}/{uuid.uuid4().hex}.{IMAGE_TYPES[ctype]}"
        try:
            res = await run_in_threadpool(storage.put_object, path, data, ctype)
        except Exception:
            raise HTTPException(status_code=502, detail="Upload gagal, coba lagi")
        await db.uploads.insert_one({"storage_path": res["path"], "owner_id": user["user_id"], "content_type": ctype,
                                     "original_filename": file.filename, "size": len(data), "is_deleted": False,
                                     "created_at": datetime.now(timezone.utc)})
        return {"url": f"/api/files/{res['path']}"}
