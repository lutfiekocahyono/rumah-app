"""Multi-vendor stores: open a store (admin verifies), seller product CRUD, public store page, admin verification."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

import storage

log = logging.getLogger("seller")
PGS_STORE_ID = "pgs-official"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StoreIn(BaseModel):
    name: str = Field(min_length=3, max_length=40)
    description: str = Field(default="", max_length=500)
    city: str = Field(min_length=2, max_length=60)
    phone: str = Field(min_length=8, max_length=20)
    logo: str = ""


class StoreStatusIn(BaseModel):
    status: str = Field(pattern="^(active|rejected|suspended)$")
    note: str = Field(default="", max_length=200)


class SellerProductIn(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=5000)
    category: str = Field(min_length=1)
    price: int = Field(ge=100)
    original_price: int = Field(default=0, ge=0)
    stock: int = Field(ge=0, le=999999)
    images: List[str] = Field(min_length=1, max_length=8)


def store_out(s: dict) -> dict:
    return {k: s.get(k) for k in ("store_id", "owner_id", "name", "description", "city", "phone", "logo",
                                  "status", "note", "created_at")}


def register(api, db, get_current_user, require_admin, product_out_for_user, notify_user, log_activity):

    async def my_store(user: dict) -> Optional[dict]:
        return await db.stores.find_one({"owner_id": user["user_id"]}, {"_id": 0})

    async def require_seller(user=Depends(get_current_user)) -> dict:
        s = await my_store(user)
        if not s or s["status"] != "active":
            raise HTTPException(status_code=403, detail="Toko Anda belum aktif")
        return {"user": user, "store": s}

    # ---------------- store owner ----------------
    @api.get("/me/store")
    async def get_my_store(user=Depends(get_current_user)):
        s = await my_store(user)
        return store_out(s) if s else None

    @api.post("/stores")
    async def open_store(body: StoreIn, user=Depends(get_current_user)):
        if await my_store(user):
            raise HTTPException(status_code=400, detail="Anda sudah punya toko")
        if await db.stores.find_one({"name_lower": body.name.strip().lower()}):
            raise HTTPException(status_code=400, detail="Nama toko sudah dipakai")
        doc = {**body.model_dump(), "name": body.name.strip(), "name_lower": body.name.strip().lower(),
               "store_id": f"st_{uuid.uuid4().hex[:10]}", "owner_id": user["user_id"], "status": "pending", "note": "",
               "created_at": _now()}
        await db.stores.insert_one({**doc})
        await log_activity(user["user_id"], "store", f"Mengajukan toko '{doc['name']}'")
        await notify_user(user["user_id"], "security", "Pengajuan toko diterima",
                          f"Toko '{doc['name']}' sedang diverifikasi admin.", "/seller")
        return store_out(doc)

    @api.put("/me/store")
    async def edit_store(body: StoreIn, user=Depends(get_current_user)):
        s = await my_store(user)
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        name = body.name.strip()
        if await db.stores.find_one({"name_lower": name.lower(), "store_id": {"$ne": s["store_id"]}}):
            raise HTTPException(status_code=400, detail="Nama toko sudah dipakai")
        upd = {**body.model_dump(), "name": name, "name_lower": name.lower()}
        if s["status"] == "rejected":
            upd["status"] = "pending"  # re-submit after rejection
        res = await db.stores.find_one_and_update({"store_id": s["store_id"]}, {"$set": upd}, projection={"_id": 0},
                                                  return_document=ReturnDocument.AFTER)
        if name != s["name"]:
            await db.products.update_many({"store_id": s["store_id"]}, {"$set": {"store_name": name}})
        return store_out(res)

    # ---------------- seller products ----------------
    @api.post("/seller/upload")
    async def seller_upload(file: UploadFile = File(...), ctx=Depends(require_seller)):
        if not (file.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="File harus berupa gambar")
        data = await file.read()
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran gambar maksimal 8 MB")
        ext = (file.filename or "p.jpg").rsplit(".", 1)[-1].lower()[:5] or "jpg"
        path = f"{storage.APP_NAME}/products/{ctx['store']['store_id']}/{uuid.uuid4().hex}.{ext}"
        try:
            res = await run_in_threadpool(storage.put_object, path, data, file.content_type)
        except Exception:
            log.exception("seller upload failed")
            raise HTTPException(status_code=502, detail="Upload gagal, coba lagi")
        await db.uploads.insert_one({"storage_path": res["path"], "owner_id": ctx["user"]["user_id"], "content_type": file.content_type,
                                     "original_filename": file.filename, "size": len(data), "is_deleted": False, "created_at": _now()})
        return {"url": f"/api/files/{res['path']}"}

    @api.get("/seller/products")
    async def seller_products(ctx=Depends(require_seller)):
        docs = await db.products.find({"store_id": ctx["store"]["store_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
        return [await product_out_for_user(d, ctx["user"]) for d in docs]

    @api.get("/seller/stats")
    async def seller_stats(ctx=Depends(require_seller)):
        sid = ctx["store"]["store_id"]
        return {"products": await db.products.count_documents({"store_id": sid}),
                "out_of_stock": await db.products.count_documents({"store_id": sid, "stock": 0})}

    def _doc(body: SellerProductIn, store: dict) -> dict:
        orig = body.original_price if body.original_price > body.price else body.price
        return {**body.model_dump(), "original_price": orig, "discount": round((orig - body.price) * 100 / orig) if orig else 0,
                "image": body.images[0], "categories": [body.category], "in_stock": body.stock > 0,
                "store_id": store["store_id"], "store_name": store["name"], "updated_at": _now()}

    @api.post("/seller/products")
    async def seller_create(body: SellerProductIn, ctx=Depends(require_seller)):
        if not await db.categories.find_one({"category_id": body.category}):
            raise HTTPException(status_code=400, detail="Kategori tidak ditemukan")
        doc = {**_doc(body, ctx["store"]), "product_id": f"sp_{uuid.uuid4().hex[:10]}", "rating": 0, "sold": 0, "created_at": _now()}
        await db.products.insert_one({**doc})
        await log_activity(ctx["user"]["user_id"], "store", f"Menambah produk '{body.name}'")
        doc.pop("_id", None)
        return await product_out_for_user(doc, ctx["user"])

    @api.put("/seller/products/{product_id}")
    async def seller_update(product_id: str, body: SellerProductIn, ctx=Depends(require_seller)):
        d = await db.products.find_one_and_update({"product_id": product_id, "store_id": ctx["store"]["store_id"]},
                                                  {"$set": _doc(body, ctx["store"])}, projection={"_id": 0},
                                                  return_document=ReturnDocument.AFTER)
        if not d:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        return await product_out_for_user(d, ctx["user"])

    @api.delete("/seller/products/{product_id}")
    async def seller_delete(product_id: str, ctx=Depends(require_seller)):
        res = await db.products.delete_one({"product_id": product_id, "store_id": ctx["store"]["store_id"]})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        return {"ok": True}

    # ---------------- public store page ----------------
    @api.get("/stores/{store_id}")
    async def public_store(store_id: str):
        s = await db.stores.find_one({"store_id": store_id, "status": "active"}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        out = store_out(s)
        out.pop("phone", None)
        out["product_count"] = await db.products.count_documents({"store_id": store_id})
        return out

    # ---------------- admin verification ----------------
    @api.get("/admin/stores")
    async def admin_stores(status: Optional[str] = None, _=Depends(require_admin)):
        q = {"status": status} if status else {}
        docs = await db.stores.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
        owners = {u["user_id"]: u for u in await db.users.find({"user_id": {"$in": [d["owner_id"] for d in docs]}},
                                                              {"user_id": 1, "name": 1, "email": 1}).to_list(500)}
        return [{**store_out(d), "owner_name": owners.get(d["owner_id"], {}).get("name"),
                 "owner_email": owners.get(d["owner_id"], {}).get("email")} for d in docs]

    @api.put("/admin/stores/{store_id}/status")
    async def admin_store_status(store_id: str, body: StoreStatusIn, _=Depends(require_admin)):
        if store_id == PGS_STORE_ID:
            raise HTTPException(status_code=400, detail="Toko resmi PGS tidak bisa diubah")
        s = await db.stores.find_one_and_update({"store_id": store_id}, {"$set": {"status": body.status, "note": body.note}},
                                                projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        msg = {"active": ("Toko Anda disetujui", f"Selamat! Toko '{s['name']}' sudah aktif. Mulai tambah produk."),
               "rejected": ("Pengajuan toko ditolak", f"Toko '{s['name']}' ditolak. {body.note}".strip()),
               "suspended": ("Toko dinonaktifkan", f"Toko '{s['name']}' dinonaktifkan admin. {body.note}".strip())}[body.status]
        await notify_user(s["owner_id"], "security", msg[0], msg[1], "/seller")
        return store_out(s)
