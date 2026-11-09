"""Harga cabang per produk (Mitra PGS Jombang / Jember): harga satuan, harga normal, dan tingkat grosir milik cabang sendiri.

Admin cabang hanya mengubah tokonya sendiri, Super Admin semua cabang. Harga PGS Sidoarjo & cabang lain tidak tersentuh.
Setiap perubahan tercatat di Riwayat Harga & Stok (sumber "Harga Cabang")."""
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import history
from pricing import CUSTOMER_TYPES, MAX_TIERS, clean_tiers

SOURCE = "branch_price"
history.SOURCES[SOURCE] = "Harga Cabang"


class TierIn(BaseModel):
    min_qty: int = Field(ge=1, le=99999)
    price: int = Field(ge=1, le=1_000_000_000)


class BranchPriceIn(BaseModel):
    store_id: Optional[str] = None
    price: int = Field(ge=1, le=1_000_000_000)
    original_price: Optional[int] = Field(default=None, ge=0, le=1_000_000_000)
    tier_prices: Dict[str, List[TierIn]] = {}


def register(api, db, get_current_user, seller):
    branches = [s for s in seller.OFFICIAL_IDS if s != seller.PGS_STORE_ID]

    async def branch_for(user: dict, store_id: Optional[str]) -> str:
        if user.get("role") == "admin":
            sid = store_id or branches[0]
            if sid not in branches:
                raise HTTPException(status_code=400, detail="Harga cabang hanya untuk Mitra PGS Jombang / Jember")
            return sid
        s = await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"store_id": 1})
        if not s or s["store_id"] not in branches:
            raise HTTPException(status_code=403, detail="Harga cabang hanya bisa diubah admin cabang mitra atau Super Admin")
        if store_id and store_id != s["store_id"]:
            raise HTTPException(status_code=403, detail="Anda hanya bisa mengubah harga toko Anda sendiri")
        return s["store_id"]

    def view(p: dict, row: Optional[dict]) -> dict:
        own = bool(row and row.get("price"))
        b = row if own else p
        return {"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", ""),
                "sidoarjo": {"price": p.get("price", 0), "original_price": p.get("original_price") or p.get("price", 0), "tier_prices": p.get("tier_prices") or {}},
                "branch": {"price": b.get("price", 0), "original_price": b.get("original_price") or b.get("price", 0), "tier_prices": b.get("tier_prices") or {}},
                "own_price": own, "stock": (row or {}).get("stock", 0), "price_set_at": (row or {}).get("price_set_at")}

    @api.get("/branch-prices")
    async def list_branch_prices(store_id: Optional[str] = None, q: str = "", skip: int = 0, limit: int = 40, user=Depends(get_current_user)):
        sid = await branch_for(user, store_id)
        query: dict = {"store_id": seller.PGS_STORE_ID, "variants.0": {"$exists": False}}
        if q.strip():
            query["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
        docs = await db.products.find(query, {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1, "original_price": 1, "tier_prices": 1}) \
            .sort("name", 1).skip(max(0, skip)).limit(min(max(1, limit), 100)).to_list(100)
        rows = {r["product_id"]: r for r in await db.store_stock.find({"store_id": sid, "product_id": {"$in": [d["product_id"] for d in docs]}}, {"_id": 0}).to_list(100)}
        names = await seller.store_names(db)
        return {"store_id": sid, "store_name": names.get(sid, sid), "items": [view(d, rows.get(d["product_id"])) for d in docs]}

    @api.put("/branch-prices/{product_id}")
    async def set_branch_price(product_id: str, body: BranchPriceIn, user=Depends(get_current_user)):
        sid = await branch_for(user, body.store_id)
        p = await db.products.find_one({"product_id": product_id, "store_id": seller.PGS_STORE_ID}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan di katalog PGS")
        if p.get("variants"):
            raise HTTPException(status_code=400, detail="Produk bervariasi belum bisa diberi harga cabang")
        unknown = set(body.tier_prices) - set(CUSTOMER_TYPES)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Jenis pembeli tidak dikenal: {', '.join(sorted(unknown))}")
        if any(len(v) > MAX_TIERS for v in body.tier_prices.values()):
            raise HTTPException(status_code=400, detail=f"Maksimal {MAX_TIERS} tingkat grosir per jenis pembeli")
        for t, rows in body.tier_prices.items():
            qs = [r.min_qty for r in rows]
            if len(set(qs)) != len(qs):
                raise HTTPException(status_code=400, detail="Jumlah minimal grosir tidak boleh dobel")
        tiers = clean_tiers({k: [r.model_dump() for r in v] for k, v in body.tier_prices.items()})
        orig = max(body.price, body.original_price or body.price)
        row = await db.store_stock.find_one({"store_id": sid, "product_id": product_id}, {"_id": 0}) or {}
        own = bool(row.get("price"))
        before = {"price": row["price"] if own else p.get("price", 0),
                  "original_price": (row.get("original_price") if own else p.get("original_price")) or (row["price"] if own else p.get("price", 0)),
                  "tier_prices": (row.get("tier_prices") if own else p.get("tier_prices")) or {}}
        after = {"price": body.price, "original_price": orig, "tier_prices": tiers}
        await db.store_stock.update_one({"store_id": sid, "product_id": product_id},
                                        {"$set": {**after, "price_set_at": datetime.now(timezone.utc), "manual_price_at": datetime.now(timezone.utc)}, "$setOnInsert": {"stock": 0}}, upsert=True)
        await history.record(db, user, sid, p, before, after, SOURCE)
        new = await db.store_stock.find_one({"store_id": sid, "product_id": product_id}, {"_id": 0})
        return view(p, new)
