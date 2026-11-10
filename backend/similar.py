"""Produk Serupa di halaman detail produk.
MANUAL: admin memilih & mengurutkan produk serupa per produk. Pilihan Super Admin (scope "all") berlaku untuk semua cabang,
admin cabang / penjual bisa menimpanya khusus tokonya (scope = store_id). Kosong -> OTOMATIS: kategori/sub-kategori,
merek, dan rentang harga yang mirip, dengan harga & stok cabang pembeli."""
import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, Field

import seller

LIMIT = 12


class SimilarIn(BaseModel):
    items: List[str] = Field(default_factory=list, max_length=30)


def register(api, db, *, get_current_user, get_optional_user, visible, apply_stock, product_out, active_flash, all_branches):

    async def manual_ids(pid: str, branch: str, owner: str) -> List[str]:
        for scope in dict.fromkeys((branch, owner, "all")):  # buyer's branch, the store selling it, Super Admin
            d = await db.similar_products.find_one({"product_id": pid, "scope": scope}, {"_id": 0, "items": 1})
            if d and d.get("items"):
                return d["items"]
        return []

    async def auto_docs(doc: dict, base: dict) -> List[dict]:
        cats = [c for c in doc.get("categories") or [] if c and c != "lainnya"]
        leaf = doc.get("subcategory") or (cats[-1] if cats else "")
        main = doc.get("category") or ""
        pool = [c for c in dict.fromkeys([leaf, *cats, main]) if c]
        if not pool:
            return []
        q = {**base, "product_id": {"$ne": doc["product_id"]}, "categories": {"$in": pool}, "status": {"$ne": "inactive"}}
        cand = await db.products.find(q, {"_id": 0}).sort("sold", -1).limit(400).to_list(400)
        price = max(doc.get("discount_price") or doc.get("price") or 1, 1)

        def score(d: dict) -> float:
            s = 3.0 if leaf and leaf in (d.get("categories") or []) else 0.0
            s += 2.0 if doc.get("brand") and d.get("brand") == doc.get("brand") else 0.0
            p = max(d.get("discount_price") or d.get("price") or 1, 1)
            s += max(0.0, 2.0 - abs(math.log(p / price)) * 2)  # same price ~ +2, 2.7x apart ~ 0
            s += 1.0 if d.get("in_stock", True) and d.get("stock", 0) > 0 else 0.0
            return s
        return sorted(cand, key=score, reverse=True)[:LIMIT]

    @api.get("/products/{product_id}/similar")
    async def similar(product_id: str, user=Depends(get_optional_user), x_store_id: Optional[str] = Header(default=None)):
        branch = x_store_id if x_store_id in seller.OFFICIAL_IDS else seller.PGS_STORE_ID
        doc = await db.products.find_one({"product_id": product_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        base = await visible(all_branches, branch)  # what this buyer's branch may see
        ids = [i for i in await manual_ids(product_id, branch, doc.get("store_id", "")) if i != product_id]
        mode = "manual"
        if ids:
            got = {d["product_id"]: d for d in await db.products.find({**base, "product_id": {"$in": ids}, "status": {"$ne": "inactive"}}, {"_id": 0}).to_list(100)}
            docs = [got[i] for i in ids if i in got][:LIMIT]
        else:
            docs = []
        if not docs:
            mode, docs = "auto", await auto_docs(doc, base)
        await apply_stock(docs, all_branches, branch)
        flash = await active_flash(db)
        return {"mode": mode, "items": [product_out(d, (user or {}).get("customer_type", "langsung"), flash, branch) for d in docs]}

    # ---------------- editor (Ubah Produk) ----------------
    async def scope_of(user: dict) -> str:
        if user.get("role") == "admin":
            return "all"
        s = await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"_id": 0, "store_id": 1})
        if not s:
            raise HTTPException(status_code=403, detail="Toko Anda belum aktif")
        return s["store_id"]

    async def brief(ids: List[str]) -> list:
        got = {d["product_id"]: d for d in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0, "product_id": 1, "name": 1, "images": 1, "price": 1, "discount_price": 1}).to_list(100)}
        return [{"product_id": i, "name": got[i]["name"], "image": (got[i].get("images") or [""])[0],
                 "price": got[i].get("discount_price") or got[i].get("price") or 0} for i in ids if i in got]

    @api.get("/product-editor/similar/{product_id}")
    async def editor_similar(product_id: str, user=Depends(get_current_user)):
        scope = await scope_of(user)
        own = await db.similar_products.find_one({"product_id": product_id, "scope": scope}, {"_id": 0})
        inherited = None
        if scope != "all" and not (own and own.get("items")):  # branch: show what Super Admin chose (used until the branch overrides it)
            g = await db.similar_products.find_one({"product_id": product_id, "scope": "all"}, {"_id": 0})
            inherited = await brief(g["items"]) if g and g.get("items") else None
        return {"scope": scope, "items": await brief((own or {}).get("items") or []), "inherited": inherited}

    @api.put("/product-editor/similar/{product_id}")
    async def save_similar(product_id: str, body: SimilarIn, user=Depends(get_current_user)):
        scope = await scope_of(user)
        if not await db.products.find_one({"product_id": product_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        items = [i for i in dict.fromkeys(body.items) if i != product_id]
        ok = {d["product_id"] for d in await db.products.find({"product_id": {"$in": items}}, {"_id": 0, "product_id": 1}).to_list(100)}
        items = [i for i in items if i in ok]
        if items:
            await db.similar_products.update_one({"product_id": product_id, "scope": scope},
                                                 {"$set": {"items": items, "updated_at": datetime.now(timezone.utc), "updated_by": user["user_id"]}}, upsert=True)
        else:  # empty = back to automatic (or to Super Admin's list for a branch)
            await db.similar_products.delete_one({"product_id": product_id, "scope": scope})
        return {"scope": scope, "items": await brief(items)}
