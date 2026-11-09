"""Salin harga & stok dari PGS Sidoarjo ke cabang mitra (Jombang, Jember): harga + selisih, stok - pengurang (min 0).

Harga cabang disalin sekali (berdiri sendiri setelahnya) dan menimpa harga/stok cabang yang sudah ada. Harga grosir tiap tingkat
ikut ditambah. Pratinjau dulu, diterapkan setelah dikonfirmasi; tiap perubahan tercatat di Riwayat Harga & Stok (tanpa notifikasi pembeli)."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import UpdateOne

import history

SOURCE = "branch_copy"
history.SOURCES[SOURCE] = "Salin dari Sidoarjo"


class Rule(BaseModel):
    store_id: str
    mode: Literal["rp", "pct", "mix"] = "rp"  # mix: % below the threshold (cheap items), Rp from the threshold up
    threshold: int = Field(default=0, ge=0, le=1_000_000_000)
    price_add: int = Field(default=0, ge=-1_000_000, le=1_000_000)  # mode rp
    price_pct: float = Field(default=0, ge=-50, le=100)  # mode pct, rounded up to Rp100
    stock_sub: int = Field(default=0, ge=0, le=100_000)
    copy_price: bool = True
    copy_stock: bool = True
    overwrite_manual: bool = False  # prices changed by the branch admin (Harga Cabang) are kept unless the owner confirms


class PreviewIn(BaseModel):
    rules: List[Rule] = Field(min_length=1, max_length=5)


class ApplyIn(BaseModel):
    confirm_down: bool = False  # extra confirmation when branch prices would go DOWN


def price_fn(r: Rule, base: int = 0):
    if r.mode == "mix":
        return price_fn(r.model_copy(update={"mode": "pct" if base < r.threshold else "rp"}))
    if r.mode == "pct":
        bp = 10000 + round(r.price_pct * 100)  # integer math (basis points): 3000 +10% = 3300 exactly, no float drift
        return lambda v: max(100, -(-int(v) * bp // 1_000_000) * 100) if v else 0
    return lambda v: max(1, v + r.price_add) if v else 0


def _tiers(t: dict, f) -> dict:
    return {k: [{**x, "price": f(x["price"])} for x in rows] for k, rows in (t or {}).items()}


def register(api, db, require_admin, seller):
    async def compute(rules: List[Rule]) -> tuple[list, dict]:
        prods = await db.products.find({"store_id": seller.PGS_STORE_ID, "variants.0": {"$exists": False}, "only_branch": None},
                                       {"_id": 0, "product_id": 1, "name": 1, "price": 1, "original_price": 1, "stock": 1, "tier_prices": 1}).to_list(50000)
        ids = [p["product_id"] for p in prods]
        out, rows = [], {}
        for r in rules:
            cur = {d["product_id"]: d for d in await db.store_stock.find({"store_id": r.store_id, "product_id": {"$in": ids}}, {"_id": 0}).to_list(50000)}
            n = {"store_id": r.store_id, "total": len(prods), "price_changed": 0, "stock_changed": 0, "unchanged": 0, "zero_stock": 0,
                 "protected": 0, "protected_overwritten": 0, "big_rise": 0, "price_down": 0}
            sample, protected, down = [], [], []
            rows[r.store_id] = []
            n["by_pct"] = n["by_rp"] = 0
            for p in prods:
                f = price_fn(r, p.get("price", 0))  # mix: Sidoarjo unit price decides % or Rp for this product (tiers included)
                if r.copy_price:
                    n["by_pct" if r.mode == "pct" or (r.mode == "mix" and p.get("price", 0) < r.threshold) else "by_rp"] += 1
                c = cur.get(p["product_id"], {})
                own = bool(c.get("price"))
                old = {"price": c["price"] if own else p.get("price", 0),
                       "original_price": (c.get("original_price") if own else p.get("original_price")) or (c["price"] if own else p.get("price", 0)),
                       "tier_prices": (c.get("tier_prices") if own else p.get("tier_prices")) or {}, "stock": c.get("stock", 0)}
                new: dict = {}
                manual = bool(c.get("manual_price_at"))
                if r.copy_price and manual and not r.overwrite_manual:
                    n["protected"] += 1
                    if len(protected) < 30:
                        protected.append({"product_id": p["product_id"], "name": p["name"], "branch_price": old["price"], "would_be": f(p.get("price", 0))})
                elif r.copy_price:
                    price = f(p.get("price", 0))
                    new.update(price=price, original_price=max(price, f(p.get("original_price") or p.get("price", 0))), tier_prices=_tiers(p.get("tier_prices"), f))
                    n["protected_overwritten"] += manual
                if r.copy_stock:
                    new["stock"] = max(0, p.get("stock", 0) - r.stock_sub)
                pc = any(new.get(k) is not None and new[k] != old[k] for k in ("price", "original_price", "tier_prices"))
                sc = "stock" in new and new["stock"] != old["stock"]
                n["price_changed"] += pc
                n["stock_changed"] += sc
                n["unchanged"] += not (pc or sc)
                n["zero_stock"] += ("stock" in new and new["stock"] == 0)
                if pc and p.get("price") and new["price"] >= p["price"] * 1.5:
                    n["big_rise"] += 1
                if "price" in new and new["price"] < old["price"]:  # cheaper than the branch's current price
                    n["price_down"] += 1
                    if len(down) < 10:
                        down.append({"product_id": p["product_id"], "name": p["name"], "old_price": old["price"], "new_price": new["price"]})
                if (pc or sc) and len(sample) < 30:
                    sample.append({"product_id": p["product_id"], "name": p["name"], "sidoarjo_price": p.get("price", 0), "sidoarjo_stock": p.get("stock", 0),
                                   "old_price": old["price"], "new_price": new.get("price", old["price"]), "old_stock": old["stock"], "new_stock": new.get("stock", old["stock"])})
                if pc or sc:
                    rows[r.store_id].append({"product_id": p["product_id"], "name": p["name"], "set": new, "before": {k: old[k] for k in new}})
            n["sample"], n["protected_sample"], n["down_sample"] = sample, protected, down
            out.append(n)
        return out, rows

    async def check_rules(rules: List[Rule]) -> dict:
        names = await seller.store_names(db)
        for r in rules:
            if r.mode == "mix" and r.threshold <= 0:
                raise HTTPException(status_code=400, detail="Isi ambang harga untuk aturan campuran")
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
    async def copy_apply(preview_id: str, body: Optional[ApplyIn] = None, admin=Depends(require_admin)):
        pre = await db.branch_copy.find_one({"preview_id": preview_id}, {"_id": 0, "rules": 1})
        if pre and not (body and body.confirm_down):
            summary, _ = await compute([Rule(**r) for r in pre["rules"]])
            down = sum(s["price_down"] for s in summary)
            if down:
                raise HTTPException(status_code=409, detail=f"{down} harga cabang akan TURUN. Centang konfirmasi harga turun lalu terapkan lagi")
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
                await db.store_stock.bulk_write([UpdateOne({"store_id": sid, "product_id": x["product_id"]}, {
                    "$set": {**x["set"], **({"price_set_at": now} if "price" in x["set"] else {})},
                    **({"$unset": {"manual_price_at": ""}} if "price" in x["set"] else {}), **({} if "stock" in x["set"] else {"$setOnInsert": {"stock": 0}})},
                    upsert=True) for x in chunk], ordered=False)
                logs = []
                for x in chunk:
                    changes = history.diff(x["before"], x["set"])
                    if changes:
                        logs.append({"log_id": f"ph_{uuid.uuid4().hex[:12]}", "product_id": x["product_id"], "product_name": x["name"], "store_id": sid,
                                     "user_id": admin["user_id"], "user_name": admin.get("name") or admin.get("email", ""), "user_role": admin.get("role", ""),
                                     "source": SOURCE, "changes": changes, "kinds": sorted({c["kind"] for c in changes}), "at": now})
                if logs:  # no buyer notification: this is a one-off setup of the branch price list
                    await db.price_history.insert_many(logs)
            result.append({"store_id": sid, "store_name": names.get(sid, sid), "updated": len(items)})
        await db.branch_copy.update_one({"preview_id": preview_id}, {"$set": {"status": "applied", "result": result, "applied_at": now}})
        return {"branches": result}
