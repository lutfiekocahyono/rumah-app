"""Multi-vendor stores: open a store (admin verifies), seller product CRUD, public store page, admin verification."""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

import history
import storage

log = logging.getLogger("seller")
PGS_STORE_ID = "pgs-official"  # PGS Sidoarjo (owns the shared 6,618-product catalog)
OFFICIAL = [
    {"store_id": PGS_STORE_ID, "name": "PGS Sidoarjo", "city": "Sidoarjo", "email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"},
    {"store_id": "pgs-jombang", "name": "Mitra PGS Jombang", "city": "Jombang", "email": "jombang@pgs.id", "password": "Jombang123!"},
    {"store_id": "pgs-jember", "name": "Mitra PGS Jember", "city": "Jember", "email": "jember@pgs.id", "password": "Jember123!"},
]
OFFICIAL_IDS = [o["store_id"] for o in OFFICIAL]
DEFAULT_COURIERS = [
    {"code": "pickup", "name": "Ambil di toko", "cost": 0, "eta": "Hari ini", "active": True},
    {"code": "jne", "name": "JNE Reguler", "cost": 25000, "eta": "2-3 hari", "active": True},
    {"code": "jnt", "name": "J&T Express", "cost": 24000, "eta": "2-3 hari", "active": True},
    {"code": "sicepat", "name": "SiCepat REG", "cost": 22000, "eta": "2-4 hari", "active": True},
]
SELLER_STATUSES = ("processing", "shipped", "completed", "cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StoreIn(BaseModel):
    name: str = Field(min_length=3, max_length=40)
    description: str = Field(default="", max_length=500)
    city: str = Field(min_length=2, max_length=60)
    phone: str = Field(default="", max_length=20)  # optional; can be filled later
    logo: str = ""
    address: str = Field(default="", max_length=300)  # pickup address shown at checkout
    pickup_hours: str = Field(default="", max_length=80)


class StoreStatusIn(BaseModel):
    status: str = Field(pattern="^(active|rejected|suspended)$")
    note: str = Field(default="", max_length=200)


class StockIn(BaseModel):
    stock: int = Field(ge=0, le=999999)


class CourierIn(BaseModel):
    code: str = Field(pattern="^[a-z0-9_]{2,20}$")
    name: str = Field(min_length=2, max_length=40)
    cost: int = Field(ge=0, le=5_000_000)
    eta: str = Field(default="", max_length=30)
    active: bool = True


class CouriersIn(BaseModel):
    couriers: List[CourierIn] = Field(min_length=1, max_length=15)


class SellerOrderStatusIn(BaseModel):
    status: str = Field(pattern="^(processing|shipped|completed|cancelled)$")
    tracking_number: str = Field(default="", max_length=40)


class SellerProductIn(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=5000)
    category: str = Field(min_length=1)
    price: int = Field(ge=100)
    original_price: int = Field(default=0, ge=0)
    stock: int = Field(ge=0, le=999999)
    images: List[str] = Field(min_length=1, max_length=8)


def store_out(s: dict) -> dict:
    out = {k: s.get(k) for k in ("store_id", "owner_id", "name", "description", "city", "phone", "logo",
                                 "status", "note", "created_at", "address", "pickup_hours")}
    out["official"] = s.get("store_id") in OFFICIAL_IDS
    out["lat"], out["lng"] = s.get("lat"), s.get("lng")
    return out


def couriers_of(store: dict) -> list:
    return store.get("couriers") or DEFAULT_COURIERS


async def store_names(db) -> dict:
    return {s["store_id"]: s["name"] for s in await db.stores.find({}, {"store_id": 1, "name": 1}).to_list(5000)}


async def branch_stocks(db, store_id: str, ids: list) -> dict:
    """Stock of shared-catalog products at a branch (Jombang/Jember). Missing = 0."""
    if not ids:
        return {}
    return {d["product_id"]: d["stock"] for d in await db.store_stock.find(
        {"store_id": store_id, "product_id": {"$in": ids}}, {"product_id": 1, "stock": 1}).to_list(len(ids))}


async def branch_prices(db, store_id: str, ids: list) -> dict:
    """Own branch price of shared-catalog products (set by 'Salin harga & stok dari Sidoarjo'). Missing = Sidoarjo price."""
    if not ids or store_id == PGS_STORE_ID:
        return {}
    return {d["product_id"]: {k: d[k] for k in ("price", "original_price", "tier_prices") if k in d} for d in await db.store_stock.find(
        {"store_id": store_id, "product_id": {"$in": ids}, "price": {"$gt": 0}}, {"_id": 0, "product_id": 1, "price": 1, "original_price": 1, "tier_prices": 1}).to_list(len(ids))}


async def adjust_stock(db, order: dict, sign: int) -> None:
    """sign=-1 reserve on checkout, +1 give back on cancel. 9999 = unlimited (website import)."""
    sid = order.get("store_id", PGS_STORE_ID)
    for i in order["items"]:
        p = await db.products.find_one({"product_id": i["product_id"]}, {"store_id": 1, "stock": 1, "variants": 1})
        if not p:
            continue
        if i.get("variant_id"):  # variant stock lives on the product; total stock follows the active variants
            await db.products.update_one({"product_id": i["product_id"]}, {"$inc": {"variants.$[v].stock": sign * i["quantity"]}},
                                         array_filters=[{"v.variant_id": i["variant_id"]}])
            p = await db.products.find_one({"product_id": i["product_id"]}, {"variants": 1})
            total = sum(v["stock"] for v in p.get("variants", []) if v.get("active", True))
            await db.products.update_one({"product_id": i["product_id"]}, {"$set": {"stock": total, "in_stock": total > 0}})
        elif sid != PGS_STORE_ID and p.get("store_id", PGS_STORE_ID) == PGS_STORE_ID:
            row = await db.store_stock.find_one({"store_id": sid, "product_id": i["product_id"]})
            if row and row["stock"] < 9999:
                await db.store_stock.update_one({"_id": row["_id"]}, {"$inc": {"stock": sign * i["quantity"]}})
        elif p.get("stock", 0) < 9999:
            res = await db.products.find_one_and_update({"product_id": i["product_id"]}, {"$inc": {"stock": sign * i["quantity"]}},
                                                        return_document=ReturnDocument.AFTER)
            await db.products.update_one({"product_id": i["product_id"]}, {"$set": {"in_stock": res["stock"] > 0}})


async def restock_once(db, order_id: str) -> None:
    o = await db.orders.find_one_and_update({"order_id": order_id, "restocked": {"$ne": True}}, {"$set": {"restocked": True}})
    if o:
        await adjust_stock(db, o, +1)


async def count_sold_once(db, order_id: str) -> None:
    """Completed order: add its quantities to each product's 'terjual' counter (once)."""
    o = await db.orders.find_one_and_update({"order_id": order_id, "status": "completed", "sold_counted": {"$ne": True}},
                                            {"$set": {"sold_counted": True}})
    for i in (o or {}).get("items", []):
        await db.products.update_one({"product_id": i["product_id"]}, {"$inc": {"sold": i["quantity"]}})


async def uncount_sold_once(db, order_id: str) -> None:
    """A counted order was cancelled/refunded afterwards: take its quantities back off (once)."""
    o = await db.orders.find_one_and_update({"order_id": order_id, "sold_counted": True}, {"$set": {"sold_counted": False}})
    for i in (o or {}).get("items", []):
        await db.products.update_one({"product_id": i["product_id"], "sold": {"$gte": i["quantity"]}}, {"$inc": {"sold": -i["quantity"]}})


async def seed_branches(db, hash_pw) -> None:
    for o in OFFICIAL:
        u = await db.users.find_one({"email": o["email"]})
        if not u:
            u = {"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": o["email"], "name": f"Admin {o['name']}",
                 "password_hash": hash_pw(o["password"]), "role": "store_admin", "customer_type": "langsung",
                 "email_verified": True, "created_at": _now()}
            await db.users.insert_one(u)
        st = await db.stores.find_one({"store_id": o["store_id"]})
        if not st:
            await db.stores.insert_one({"store_id": o["store_id"], "owner_id": u["user_id"], "name": o["name"], "name_lower": o["name"].lower(),
                                        "description": f"Toko resmi {o['name']}", "city": o["city"], "phone": "", "logo": "",
                                        "status": "active", "note": "", "couriers": DEFAULT_COURIERS, "created_at": _now()})
            if o["store_id"] != PGS_STORE_ID:  # sample: copy Sidoarjo stock so the branch is shoppable; edit in Kelola Toko > Stok
                cat = await db.products.find({"store_id": PGS_STORE_ID}, {"product_id": 1, "stock": 1}).to_list(20000)
                if cat:
                    await db.store_stock.insert_many([{"store_id": o["store_id"], "product_id": c["product_id"], "stock": c.get("stock", 0)} for c in cat])
        elif o["store_id"] == PGS_STORE_ID and st.get("name") != o["name"]:  # rename PGS Official -> PGS Sidoarjo, hand to its manager
            await db.stores.update_one({"store_id": PGS_STORE_ID}, {"$set": {"name": o["name"], "name_lower": o["name"].lower(), "owner_id": u["user_id"],
                                                                            "couriers": st.get("couriers") or DEFAULT_COURIERS}})
            await db.products.update_many({"store_id": PGS_STORE_ID}, {"$set": {"store_name": o["name"]}})


def register(api, db, get_current_user, require_admin, product_out_for_user, notify_user, log_activity,
             release_voucher, order_out):

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
        if ctx["store"]["store_id"] in OFFICIAL_IDS:  # branch admin: only this branch's buyers see it
            doc["only_branch"] = ctx["store"]["store_id"]
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
        q = {"product_id": product_id, "store_id": ctx["store"]["store_id"]}
        if q["store_id"] == PGS_STORE_ID:  # the shared master catalogue can only be removed by the Super Admin
            q["only_branch"] = PGS_STORE_ID
        res = await db.products.delete_one(q)
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        return {"ok": True}

    # ---------------- inventory (stock per store) ----------------
    @api.get("/seller/inventory")
    async def seller_inventory(q: str = "", skip: int = 0, limit: int = 40, ctx=Depends(require_seller)):
        sid = ctx["store"]["store_id"]
        ids = [sid, PGS_STORE_ID] if sid in OFFICIAL_IDS else [sid]
        query: dict = {"store_id": {"$in": ids}, "only_branch": {"$in": [None, sid]}}
        if q.strip():
            query["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
        docs = await db.products.find(query, {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1, "stock": 1, "store_id": 1}) \
            .sort([("store_id", -1 if sid != PGS_STORE_ID else 1), ("name", 1)]).skip(max(0, skip)).limit(min(limit, 100)).to_list(100)
        shared = [d["product_id"] for d in docs if d["store_id"] != sid]
        stocks = await branch_stocks(db, sid, shared)
        prices = await branch_prices(db, sid, shared)
        return [{**d, "stock": stocks.get(d["product_id"], 0) if d["store_id"] != sid else d.get("stock", 0),
                 "price": prices.get(d["product_id"], {}).get("price", d.get("price", 0)) if d["store_id"] != sid else d.get("price", 0),
                 "own": d["store_id"] == sid} for d in docs]

    @api.put("/seller/inventory/{product_id}")
    async def seller_set_stock(product_id: str, body: StockIn, ctx=Depends(require_seller)):
        sid = ctx["store"]["store_id"]
        p = await db.products.find_one({"product_id": product_id}, {"product_id": 1, "name": 1, "store_id": 1, "stock": 1, "variants": 1})
        if not p or (p["store_id"] != sid and not (sid in OFFICIAL_IDS and p["store_id"] == PGS_STORE_ID)):
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        if p.get("variants"):
            raise HTTPException(status_code=400, detail="Produk ini punya variasi. Atur stok per variasi lewat Ubah Produk")
        if p["store_id"] == sid:
            old = p.get("stock", 0)
            await db.products.update_one({"product_id": product_id}, {"$set": {"stock": body.stock, "in_stock": body.stock > 0, "updated_at": _now()}})
        else:
            row = await db.store_stock.find_one({"store_id": sid, "product_id": product_id}, {"stock": 1})
            old = (row or {}).get("stock", 0)
            await db.store_stock.update_one({"store_id": sid, "product_id": product_id}, {"$set": {"stock": body.stock}}, upsert=True)
        if body.stock > old:  # restock -> may appear in "Produk Terbaru"
            await db.products.update_one({"product_id": product_id}, {"$set": {"restocked_at": _now()}})
        await history.record(db, ctx["user"], sid, p, {"stock": old}, {"stock": body.stock}, "stock")
        return {"product_id": product_id, "stock": body.stock}

    # ---------------- couriers ----------------
    @api.get("/stores/{store_id}/couriers")
    async def store_couriers(store_id: str):
        s = await db.stores.find_one({"store_id": store_id, "status": "active"})
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        return [c for c in couriers_of(s) if c.get("active", True)]

    async def _save_couriers(store_id: str, body: CouriersIn) -> list:
        codes = [c.code for c in body.couriers]
        if len(set(codes)) != len(codes):
            raise HTTPException(status_code=400, detail="Kode kurir tidak boleh sama")
        data = [c.model_dump() for c in body.couriers]
        await db.stores.update_one({"store_id": store_id}, {"$set": {"couriers": data}})
        return data

    @api.get("/seller/couriers")
    async def seller_couriers(ctx=Depends(require_seller)):
        return couriers_of(ctx["store"])

    @api.put("/seller/couriers")
    async def seller_set_couriers(body: CouriersIn, ctx=Depends(require_seller)):
        return await _save_couriers(ctx["store"]["store_id"], body)

    @api.get("/admin/stores/{store_id}/couriers")
    async def admin_couriers(store_id: str, _=Depends(require_admin)):
        s = await db.stores.find_one({"store_id": store_id})
        if not s:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        return couriers_of(s)

    @api.put("/admin/stores/{store_id}/couriers")
    async def admin_set_couriers(store_id: str, body: CouriersIn, _=Depends(require_admin)):
        if not await db.stores.find_one({"store_id": store_id}):
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        return await _save_couriers(store_id, body)

    # ---------------- store orders ----------------
    @api.get("/seller/orders")
    async def seller_orders(status: Optional[str] = None, ctx=Depends(require_seller)):
        q: dict = {"store_id": ctx["store"]["store_id"]}
        if status == "new":
            q["status"] = {"$in": ["paid", "cod"]}
        elif status:
            q["status"] = status
        return [order_out(d) for d in await db.orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(300)]

    @api.get("/seller/orders/{order_id}")
    async def seller_order(order_id: str, ctx=Depends(require_seller)):
        d = await db.orders.find_one({"order_id": order_id, "store_id": ctx["store"]["store_id"]}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        return order_out(d)

    class ExtendIn(BaseModel):
        hours: int = Field(ge=1, le=168)

    @api.post("/seller/orders/{order_id}/extend")
    async def seller_extend_order(order_id: str, body: ExtendIn, ctx=Depends(require_seller)):
        """Give a COD pickup order more time before it auto-cancels."""
        d = await db.orders.find_one({"order_id": order_id, "store_id": ctx["store"]["store_id"]})
        if not d:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        if d["status"] != "cod" or not d.get("expires_at"):
            raise HTTPException(status_code=400, detail="Hanya pesanan COD yang belum diproses yang bisa diperpanjang")
        cur = d["expires_at"].replace(tzinfo=timezone.utc) if d["expires_at"].tzinfo is None else d["expires_at"]
        new = max(cur, _now()) + timedelta(hours=body.hours)
        res = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": {"expires_at": new, "updated_at": _now(), "expiry_reminded": False},
            "$push": {"status_history": {"status": "cod", "at": _now(), "note": f"Batas waktu diperpanjang {body.hours} jam oleh {ctx['store']['name']}"}}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        await notify_user(d.get("user_id"), "order", "Batas waktu pesanan diperpanjang",
                          f"Pesanan {order_id} diperpanjang {body.hours} jam oleh toko.", f"/order/{order_id}")
        return order_out(res)

    @api.post("/seller/orders/{order_id}/ready")
    async def seller_ready_order(order_id: str, ctx=Depends(require_seller)):
        """Pickup order is packed and waiting at the store."""
        d = await db.orders.find_one({"order_id": order_id, "store_id": ctx["store"]["store_id"]})
        if not d:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        if (d.get("courier") or {}).get("code") != "pickup" or d["status"] != "processing":
            raise HTTPException(status_code=400, detail="Tandai siap diambil setelah pesanan Ambil di toko diproses")
        if d.get("ready_at"):
            return order_out({k: v for k, v in d.items() if k != "_id"})
        s = ctx["store"]
        res = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": {"ready_at": _now(), "updated_at": _now()},
            "$push": {"status_history": {"status": "processing", "at": _now(), "note": "Siap diambil di toko"}}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        where = f" di {s.get('address')}" if s.get("address") else ""
        hours = f" Jam ambil: {s['pickup_hours']}." if s.get("pickup_hours") else ""
        code = f" Kode ambil: {d['pickup_code']} (tunjukkan ke kasir)." if d.get("pickup_code") else ""
        due = d["total"] - d.get("balance_used", 0)
        pay = f" Siapkan pembayaran tunai Rp{due:,}.".replace(",", ".") if d.get("payment_method") == "cod" and due > 0 else ""
        await notify_user(d.get("user_id"), "order", "Pesanan siap diambil",
                          f"Pesanan {order_id} sudah siap diambil di {s['name']}{where}.{code}{hours}{pay}", f"/order/{order_id}")
        return order_out(res)

    @api.put("/seller/orders/{order_id}/status")
    async def seller_order_status(order_id: str, body: SellerOrderStatusIn, ctx=Depends(require_seller)):
        sid = ctx["store"]["store_id"]
        d = await db.orders.find_one({"order_id": order_id, "store_id": sid})
        if not d:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        allowed = {"processing": ("paid", "cod"), "shipped": ("processing",), "completed": ("shipped", "processing"),
                   "cancelled": ("pending", "paid", "cod", "processing")}[body.status]
        if d["status"] not in allowed:
            raise HTTPException(status_code=400, detail="Status pesanan tidak bisa diubah ke tahap ini")
        pickup = (d.get("courier") or {}).get("code") == "pickup"
        if body.status == "shipped" and not pickup and not body.tracking_number.strip():
            raise HTTPException(status_code=400, detail="Masukkan nomor resi")
        if body.status == "completed" and d["status"] == "processing" and not pickup:
            raise HTTPException(status_code=400, detail="Kirim pesanan dulu, pembeli yang mengonfirmasi penerimaan")
        upd = {"status": body.status, "updated_at": _now()}
        if body.tracking_number.strip():
            upd["tracking_number"] = body.tracking_number.strip().upper()
        if body.status == "completed":
            upd["completed_at"] = _now()
        note = f"Resi {upd['tracking_number']}" if upd.get("tracking_number") and body.status == "shipped" else ctx["store"]["name"]
        res = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": upd, "$push": {"status_history": {
            "status": body.status, "at": _now(), "note": note}}}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if body.status == "cancelled":
            await release_voucher(order_id)
            await restock_once(db, order_id)
        if body.status == "completed":
            await count_sold_once(db, order_id)
        label = {"processing": "sedang diproses", "shipped": "sedang dikirim", "completed": "selesai", "cancelled": "dibatalkan"}[body.status]
        extra = f" No. resi: {upd['tracking_number']}" if body.status == "shipped" and upd.get("tracking_number") else ""
        await notify_user(d.get("user_id"), "order", "Status pesanan diperbarui", f"Pesanan {order_id} {label}.{extra}", f"/order/{order_id}")
        return order_out(res)

    # ---------------- Scan: kode ambil pesanan (kasir) ----------------
    class PickupCodeIn(BaseModel):
        code: str = Field(min_length=4, max_length=200)

    async def pickup_ctx(user=Depends(get_current_user)) -> dict:
        if user.get("role") == "admin":  # Super Admin may hand over orders of any branch
            return {"user": user, "store": None}
        return await require_seller(user)

    async def _pickup_order(code: str, ctx: dict) -> tuple:
        digits = re.sub(r"\D", "", code)
        q = {"pickup_code": digits, **({"store_id": ctx["store"]["store_id"]} if ctx["store"] else {})}
        # prefer an order still waiting at the counter over older/finished ones with the same code
        d = (await db.orders.find_one({**q, "status": {"$in": ["paid", "cod", "processing"]}}, {"_id": 0}, sort=[("created_at", -1)])
             or await db.orders.find_one(q, {"_id": 0}, sort=[("created_at", -1)])) if digits else None
        if not d:
            raise HTTPException(status_code=404, detail="Kode ambil tidak ditemukan di toko ini")
        store = ctx["store"] or await db.stores.find_one({"store_id": d["store_id"]}, {"_id": 0})
        return d, {"user": ctx["user"], "store": store}

    @api.post("/seller/pickup/lookup")
    async def pickup_lookup(body: PickupCodeIn, ctx=Depends(pickup_ctx)):
        """Cashier scans/types the buyer's pickup code -> the order to hand over."""
        return order_out((await _pickup_order(body.code, ctx))[0])

    @api.post("/seller/pickup/complete")
    async def pickup_complete(body: PickupCodeIn, ctx=Depends(pickup_ctx)):
        """Hand the goods over: the pickup order is completed (COD cash is collected at the counter)."""
        d, ctx = await _pickup_order(body.code, ctx)
        if d["status"] == "completed":
            raise HTTPException(status_code=400, detail="Pesanan ini sudah diambil / selesai")
        if d["status"] not in ("paid", "cod", "processing"):
            raise HTTPException(status_code=400, detail="Pesanan ini tidak bisa diserahkan (status: " + d["status"] + ")")
        if d["status"] in ("paid", "cod"):
            await seller_order_status(d["order_id"], SellerOrderStatusIn(status="processing"), ctx)
        return await seller_order_status(d["order_id"], SellerOrderStatusIn(status="completed"), ctx)

    # ---------------- revenue report (no commission) ----------------
    async def _report(store_id: Optional[str]) -> dict:
        match: dict = {"store_id": store_id} if store_id else {}
        by_status = {r["_id"]: {"orders": r["n"], "total": r["t"]} for r in await db.orders.aggregate([
            {"$match": match}, {"$group": {"_id": "$status", "n": {"$sum": 1}, "t": {"$sum": "$total"}}}]).to_list(20)}
        since = _now() - timedelta(days=30)
        daily = await db.orders.aggregate([
            {"$match": {**match, "status": "completed", "created_at": {"$gte": since}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "revenue": {"$sum": "$total"}, "orders": {"$sum": 1}}},
            {"$sort": {"_id": 1}}]).to_list(40)
        top = await db.orders.aggregate([
            {"$match": {**match, "status": {"$in": ["completed", "shipped", "processing", "paid", "cod"]}}}, {"$unwind": "$items"},
            {"$group": {"_id": "$items.product_id", "name": {"$first": "$items.name"}, "qty": {"$sum": "$items.quantity"},
                        "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}}},
            {"$sort": {"qty": -1}}, {"$limit": 5}]).to_list(5)
        done = by_status.get("completed", {"orders": 0, "total": 0})
        running = sum(v["total"] for k, v in by_status.items() if k in ("paid", "cod", "processing", "shipped"))
        return {"revenue_completed": done["total"], "orders_completed": done["orders"], "revenue_in_progress": running,
                "by_status": by_status, "daily": [{"date": d["_id"], "revenue": d["revenue"], "orders": d["orders"]} for d in daily],
                "top_products": [{"product_id": t["_id"], "name": t["name"], "qty": t["qty"], "revenue": t["revenue"]} for t in top]}

    @api.get("/seller/report")
    async def seller_report(ctx=Depends(require_seller)):
        return await _report(ctx["store"]["store_id"])

    @api.get("/admin/report")
    async def admin_report(_=Depends(require_admin)):
        stores = await db.stores.find({"status": "active"}, {"_id": 0, "store_id": 1, "name": 1}).to_list(500)
        return {"all": await _report(None), "stores": [{**s, **(await _report(s["store_id"]))} for s in stores]}

    @api.get("/official-stores")
    async def official_stores():
        docs = await db.stores.find({"store_id": {"$in": OFFICIAL_IDS}, "status": "active"}, {"_id": 0}).to_list(10)
        order = {sid: i for i, sid in enumerate(OFFICIAL_IDS)}
        return [store_out(d) for d in sorted(docs, key=lambda d: order[d["store_id"]])]

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
