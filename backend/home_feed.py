"""Homepage product sections (Populer / Terbaru / Rekomendasi) with per-branch rules.

Each official branch admin sets its own rules; the buyer sees the rules of the branch they picked.
Manually pinned products from all branches are merged (buyer's branch first) and shown before the automatic list."""
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

import promo
import seller
from pricing import get_pricing

SECTION_KEYS = ("popular", "newest", "recommended")
SORTS = {"best_selling", "rating", "most_viewed", "newest", "random", "personal"}
DEFAULTS = {
    "popular": {"enabled": True, "title": "Produk Populer", "limit": 10, "sort": "best_selling", "pinned": [], "categories": [], "days": 7},
    "newest": {"enabled": True, "title": "Produk Terbaru", "limit": 10, "sort": "newest", "pinned": [], "categories": [], "days": 7},
    "recommended": {"enabled": True, "title": "Rekomendasi untukmu", "limit": 20, "sort": "personal", "pinned": [], "categories": [], "days": 7},
}


class SectionIn(BaseModel):
    enabled: bool = True
    title: str = Field(min_length=1, max_length=40)
    limit: int = Field(ge=1, le=30)
    sort: Literal["best_selling", "rating", "most_viewed", "newest", "random", "personal"]
    pinned: List[str] = Field(default=[], max_length=30)
    categories: List[str] = Field(default=[], max_length=20)
    days: int = Field(default=7, ge=1, le=90)  # Produk Terbaru: uploaded or restocked within this many days


class SectionsIn(BaseModel):
    popular: SectionIn
    newest: SectionIn
    recommended: SectionIn


def register(api, db, *, get_current_user, require_admin, get_optional_owner, get_optional_user,
             visible, apply_stock, product_out, all_branches: str):

    async def load_cfg(store_id: str) -> dict:
        doc = await db.home_sections.find_one({"store_id": store_id}, {"_id": 0}) or {}
        out = {k: {**DEFAULTS[k], **(doc.get(k) or {})} for k in SECTION_KEYS}
        if not doc.get("recommended"):  # older global setting (Admin > Pengaturan Beranda) stays the default
            out["recommended"]["sort"] = (await promo.get_home(db))["recommend_mode"]
            if out["recommended"]["sort"] not in SORTS:
                out["recommended"]["sort"] = "personal"
        return out

    async def merged_pins(key: str, first: str) -> List[str]:
        """Pins of the buyer's branch first, then the other branches; duplicates removed."""
        docs = {d["store_id"]: d for d in await db.home_sections.find({"store_id": {"$in": seller.OFFICIAL_IDS}}, {"_id": 0}).to_list(10)}
        out: List[str] = []
        for sid in [first] + [s for s in seller.OFFICIAL_IDS if s != first]:
            for pid in ((docs.get(sid) or {}).get(key) or {}).get("pinned", []):
                if pid not in out:
                    out.append(pid)
        return out

    async def cat_filter(cats: List[str]) -> Optional[dict]:
        if not cats:
            return None
        children = [c["category_id"] for c in await db.categories.find({"parent": {"$in": cats}}, {"category_id": 1}).to_list(500)]
        return {"$in": [*cats, *children]}

    async def section_items(key: str, cfg: dict, branch: str, owner: Optional[str], user: Optional[dict],
                            skip: int = 0, limit: Optional[int] = None) -> List:
        """Ordered list = in-stock pins, then the automatic list (in stock only); the page is sliced from that list."""
        limit = limit or cfg["limit"]
        want = skip + limit
        base = {**await visible(all_branches)}
        cf = await cat_filter(cfg["categories"])
        if cf:
            base["categories"] = cf
        pins = await merged_pins(key, branch)
        pinned_docs: list = []
        if pins:
            got = {d["product_id"]: d for d in await db.products.find({**base, "product_id": {"$in": pins}}, {"_id": 0}).to_list(len(pins))}
            pinned_docs = [got[p] for p in pins if p in got]
            await apply_stock(pinned_docs, all_branches)
            pinned_docs = [d for d in pinned_docs if d.get("stock", 0) > 0]
        need = want - len(pinned_docs)
        auto: list = []
        if need > 0:
            match = {**base, "product_id": {"$nin": pins}}
            fresh = {"$max": [{"$ifNull": ["$created_at", None]}, {"$ifNull": ["$restocked_at", None]}]}
            if key == "newest":
                since = datetime.now(timezone.utc) - timedelta(days=cfg["days"])
                match["$or"] = [{"created_at": {"$gte": since}}, {"restocked_at": {"$gte": since}}]
            fetch = need + 20  # some may be out of stock at every branch
            sort = cfg["sort"]
            if sort == "random":
                pipeline = [{"$match": match}, {"$sample": {"size": fetch}}]
            else:
                pipeline = [{"$match": match}]
                if sort == "personal":
                    act = await db.activity.find_one({"owner": owner}) if owner else None
                    cats = [c for c, _ in sorted((act or {}).get("cats", {}).items(), key=lambda kv: -kv[1])[:5]]
                    recent = (act or {}).get("recent", [])[-10:]
                    pipeline[0]["$match"]["product_id"] = {"$nin": pins + recent}
                    pipeline.append({"$addFields": {"_k": {"$cond": [{"$gt": [{"$size": {"$setIntersection": [{"$ifNull": ["$categories", []]}, cats]}}, 0]}, 1, 0]}}})
                    order = {"_k": -1, "sold": -1}
                elif sort == "newest":
                    pipeline.append({"$addFields": {"_k": fresh}})
                    order = {"_k": -1}
                elif sort == "rating":
                    order = {"rating": -1, "sold": -1}
                elif sort == "most_viewed":
                    order = {"views": -1, "sold": -1}
                else:
                    order = {"sold": -1}
                pipeline += [{"$sort": {**order, "created_at": -1, "product_id": -1}}, {"$limit": fetch}]
            pipeline.append({"$project": {"_id": 0, "_k": 0}} if sort in ("personal", "newest") else {"$project": {"_id": 0}})
            auto = await db.products.aggregate(pipeline).to_list(fetch)
            await apply_stock(auto, all_branches)
            auto = [d for d in auto if d.get("in_stock", True) and d.get("stock", 0) > 0]
        page = (pinned_docs + auto)[skip:want]
        pricing, flash = await get_pricing(db), await promo.active_flash(db)
        ctype = (user or {}).get("customer_type", "langsung")
        return [product_out(d, ctype, pricing, flash) for d in page]

    def branch_of(x_store_id: Optional[str]) -> str:
        return x_store_id if x_store_id in seller.OFFICIAL_IDS else seller.PGS_STORE_ID

    # ---------------- public ----------------
    @api.get("/home/sections")
    async def home_sections(owner: Optional[str] = Depends(get_optional_owner), user=Depends(get_optional_user),
                            x_store_id: Optional[str] = Header(default=None)):
        branch = branch_of(x_store_id)
        cfg = await load_cfg(branch)
        out = {}
        for k in SECTION_KEYS:
            c = cfg[k]
            items = await section_items(k, c, branch, owner, user) if c["enabled"] else []
            out[k] = {"enabled": c["enabled"], "title": c["title"], "limit": c["limit"], "items": items,
                      "more": k == "recommended" and c["sort"] != "random"}  # random has no stable order to page through
        return out

    @api.get("/home/sections/recommended")
    async def more_recommended(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=30),
                               owner: Optional[str] = Depends(get_optional_owner), user=Depends(get_optional_user),
                               x_store_id: Optional[str] = Header(default=None)):
        branch = branch_of(x_store_id)
        c = (await load_cfg(branch))["recommended"]
        if not c["enabled"] or c["sort"] == "random" or skip >= 300:
            return []
        return await section_items("recommended", c, branch, owner, user, skip, limit)

    # ---------------- settings (branch admin / super admin) ----------------
    async def cfg_out(store_id: str) -> dict:
        cfg = await load_cfg(store_id)
        ids = list({p for k in SECTION_KEYS for p in cfg[k]["pinned"]})
        prods = {p["product_id"]: p for p in await db.products.find(
            {"product_id": {"$in": ids}}, {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1}).to_list(len(ids) or 1)}
        for k in SECTION_KEYS:
            cfg[k]["pinned_products"] = [prods[p] for p in cfg[k]["pinned"] if p in prods]
        store = await db.stores.find_one({"store_id": store_id}, {"_id": 0, "name": 1})
        return {"store_id": store_id, "store_name": (store or {}).get("name", store_id), "sections": cfg}

    async def save(store_id: str, body: SectionsIn) -> dict:
        data = {}
        for k in SECTION_KEYS:
            s: SectionIn = getattr(body, k)
            if s.sort == "personal" and k != "recommended":
                raise HTTPException(status_code=400, detail="Urutan 'Sesuai minat pembeli' hanya untuk Rekomendasi")
            pinned = list(dict.fromkeys(s.pinned))
            found = {p["product_id"] for p in await db.products.find({"product_id": {"$in": pinned}}, {"product_id": 1}).to_list(len(pinned) or 1)}
            data[k] = {**s.model_dump(), "title": s.title.strip(), "pinned": [p for p in pinned if p in found],
                       "categories": list(dict.fromkeys(s.categories))}
        await db.home_sections.update_one({"store_id": store_id}, {"$set": {**data, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
        return await cfg_out(store_id)

    async def my_branch(user=Depends(get_current_user)) -> str:
        s = await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"store_id": 1})
        if not s or s["store_id"] not in seller.OFFICIAL_IDS:
            raise HTTPException(status_code=403, detail="Hanya admin cabang PGS yang bisa mengatur beranda")
        return s["store_id"]

    def official(store_id: str) -> str:
        if store_id not in seller.OFFICIAL_IDS:
            raise HTTPException(status_code=404, detail="Cabang tidak ditemukan")
        return store_id

    @api.get("/seller/home-sections")
    async def seller_get_sections(store_id: str = Depends(my_branch)):
        return await cfg_out(store_id)

    @api.put("/seller/home-sections")
    async def seller_set_sections(body: SectionsIn, store_id: str = Depends(my_branch)):
        return await save(store_id, body)

    @api.get("/admin/home-sections/{store_id}")
    async def admin_get_sections(store_id: str, _=Depends(require_admin)):
        return await cfg_out(official(store_id))

    @api.put("/admin/home-sections/{store_id}")
    async def admin_set_sections(store_id: str, body: SectionsIn, _=Depends(require_admin)):
        return await save(official(store_id), body)

    @api.post("/admin/home-sections/{store_id}/copy-pins")
    async def admin_copy_pins(store_id: str, _=Depends(require_admin)):
        """Copy this branch's saved manual picks (all three sections, same order) to every other PGS branch; their rules stay."""
        src = await load_cfg(official(store_id))
        targets = [s for s in seller.OFFICIAL_IDS if s != store_id]
        for sid in targets:
            await db.home_sections.update_one({"store_id": sid}, {"$set": {
                **{f"{k}.pinned": src[k]["pinned"] for k in SECTION_KEYS}, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
        return {"copied_to": targets, "counts": {k: len(src[k]["pinned"]) for k in SECTION_KEYS}}
