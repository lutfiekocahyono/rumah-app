"""Salin harga & stok dari PGS Sidoarjo ke cabang mitra (Jombang, Jember): harga + selisih, stok - pengurang (min 0).

Harga cabang disalin sekali (berdiri sendiri setelahnya) dan menimpa harga/stok cabang yang sudah ada. Harga grosir tiap tingkat
ikut ditambah. Pratinjau dulu, diterapkan setelah dikonfirmasi; tiap perubahan tercatat di Riwayat Harga & Stok (tanpa notifikasi pembeli)."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import UpdateOne

import history

SOURCE = "branch_copy"
history.SOURCES[SOURCE] = "Salin dari Sidoarjo"


class Rule(BaseModel):
    store_id: str
    price_add: int = Field(ge=-1_000_000, le=1_000_000)
    stock_sub: int = Field(ge=0, le=100_000)


class PreviewIn(BaseModel):
    rules: List[Rule] = Field(min_length=1, max_length=5)


def _tiers(t: dict, add: int) -> dict:
    return {k: [{**r, "price": max(1, r["price"] + add)} for r in rows] for k, rows in (t or {}).items()}


def register(api, db, require_admin, seller):
    async def compute(rules: List[Rule]) -> tuple[list, dict]:
        prods = await db.products.find({"store_id": seller.PGS_STORE_ID, "variants.0": {"$exists": False}},
                                       {"_id": 0, "product_id": 1, "name": 1, "price": 1, "original_price": 1, "stock": 1, "tier_prices": 1}).to_list(50000)
        ids = [p["product_id"] for p in prods]
        out, rows = [], {}
        for r in rules:
            cur = {d["product_id"]: d for d in await db.store_stock.find({"store_id": r.store_id, "product_id": {"$in": ids}}, {"_id": 0}).to_list(50000)}
            n = {"store_id": r.store_id, "total": len(prods), "price_changed": 0, "stock_changed": 0, "unchanged": 0, "zero_stock": 0}
            sample = []
            rows[r.store_id] = []
            for p in prods:
                price = max(1, p.get("price", 0) + r.price_add)
                orig = max(price, (p.get("original_price") or p.get("price", 0)) + r.price_add)
                stock = max(0, p.get("stock", 0) - r.stock_sub)
                c = cur.get(p["product_id"], {})
                old_price, old_stock = c.get("price") or p.get("price", 0), c.get("stock", 0)
                tiers = _tiers(p.get("tier_prices"), r.price_add)
                pc, sc = old_price != price or (c.get("tier_prices") or p.get("tier_prices") or {}) != tiers, old_stock != stock
                n["price_changed"] += pc
                n["stock_changed"] += sc
                n["unchanged"] += not (pc or sc)
                n["zero_stock"] += stock == 0
                if (pc or sc) and len(sample) < 30:
                    sample.append({"product_id": p["product_id"], "name": p["name"], "sidoarjo_price": p.get("price", 0), "sidoarjo_stock": p.get("stock", 0),
                                   "old_price": old_price, "new_price": price, "old_stock": old_stock, "new_stock": stock})
                if pc or sc:
                    rows[r.store_id].append({"product_id": p["product_id"], "name": p["name"], "price": price, "original_price": orig, "tier_prices": tiers,
                                             "stock": stock, "before": {"price": old_price, "original_price": c.get("original_price") or old_price,
                                                                        "stock": old_stock, "tier_prices": c.get("tier_prices") or p.get("tier_prices") or {}}})
            n["sample"] = sample
            out.append(n)
        return out, rows

    async def check_rules(rules: List[Rule]) -> dict:
        names = await seller.store_names(db)
        for r in rules:
            if r.store_id not in seller.OFFICIAL_IDS or r.store_id == seller.PGS_STORE_ID:
                raise HTTPException(status_code=400, detail="Cabang tujuan hanya Mitra PGS Jombang / Jember")
        if len({r.store_id for r in rules}) != len(rules):
            raise HTTPException(status_code=400, detail="Cabang tujuan dobel")
        return names

    @api.post("/admin/branch-copy/preview")
    async def copy_preview(body: PreviewIn, admin=Depends(require_admin)):
        names = await check_rules(body.rules)
        summary, _ = await compute(body.rules)
        for s in summary:
            s["store_name"] = names.get(s["store_id"], s["store_id"])
        doc = {"preview_id": f"bc_{uuid.uuid4().hex[:10]}", "rules": [r.model_dump() for r in body.rules], "by": admin["user_id"],
               "created_at": datetime.now(timezone.utc), "status": "preview"}
        await db.branch_copy.insert_one({**doc})
        return {"preview_id": doc["preview_id"], "branches": summary}

    @api.post("/admin/branch-copy/{preview_id}/apply")
    async def copy_apply(preview_id: str, admin=Depends(require_admin)):
        d = await db.branch_copy.find_one_and_update(
            {"preview_id": preview_id, "status": "preview", "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=2)}},
            {"$set": {"status": "applying"}}, projection={"_id": 0})
        if not d:
            raise HTTPException(status_code=400, detail="Pratinjau sudah dipakai atau kedaluwarsa. Buat pratinjau baru")
        rules = [Rule(**r) for r in d["rules"]]
        names = await check_rules(rules)
        _, rows = await compute(rules)  # recomputed now, so stock sold since the preview is respected
        now, result = datetime.now(timezone.utc), []
        for sid, items in rows.items():
            for i in range(0, len(items), 1000):
                chunk = items[i:i + 1000]
                await db.store_stock.bulk_write([UpdateOne({"store_id": sid, "product_id": x["product_id"]}, {"$set": {
                    "stock": x["stock"], "price": x["price"], "original_price": x["original_price"], "tier_prices": x["tier_prices"], "price_set_at": now}},
                    upsert=True) for x in chunk], ordered=False)
                logs = []
                for x in chunk:
                    changes = history.diff(x["before"], {k: x[k] for k in ("price", "original_price", "stock", "tier_prices")})
                    if changes:
                        logs.append({"log_id": f"ph_{uuid.uuid4().hex[:12]}", "product_id": x["product_id"], "product_name": x["name"], "store_id": sid,
                                     "user_id": admin["user_id"], "user_name": admin.get("name") or admin.get("email", ""), "user_role": admin.get("role", ""),
                                     "source": SOURCE, "changes": changes, "kinds": sorted({c["kind"] for c in changes}), "at": now})
                if logs:  # no buyer notification: this is a one-off setup of the branch price list
                    await db.price_history.insert_many(logs)
            result.append({"store_id": sid, "store_name": names.get(sid, sid), "updated": len(items)})
        await db.branch_copy.update_one({"preview_id": preview_id}, {"$set": {"status": "applied", "result": result, "applied_at": now}})
        return {"branches": result}
