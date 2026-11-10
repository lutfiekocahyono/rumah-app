"""Master Merek & Kategori: Super Admin membuat, mengubah, menghapus merek (dengan logo) dan kategori / sub-kategori.
Produk tidak kehilangan data: ganti nama merek ikut mengubah produknya, hapus merek -> "Tanpa merek",
hapus kategori -> produknya pindah ke "Lainnya"."""
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

OTHER = "lainnya"
LOGOS: Dict[str, str] = {}  # brand name -> logo url, for product cards / detail (refreshed on every change)


def brand_logo(name: Optional[str]) -> str:
    return LOGOS.get(name or "", "")


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    logo: str = ""


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent: Optional[str] = None
    icon: str = "pricetag-outline"
    image: str = ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "kategori"


def _ci(name: str) -> dict:
    return {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}


async def find_brand(db, name: str) -> Optional[dict]:
    """Existing brand with this name, any capitalisation."""
    return await db.brands.find_one({"name": _ci(name)}, {"_id": 0}) if name.strip() else None


async def ensure_brand(db, name: str) -> str:
    """Excel import: reuse the existing spelling, or add the new brand to the list (the product keeps its brand)."""
    name = (name or "").strip()
    if not name:
        return ""
    hit = await find_brand(db, name)
    if hit:
        return hit["name"]
    await db.brands.insert_one({"brand_id": uuid.uuid4().hex[:12], "name": name, "logo": "", "created_at": datetime.now(timezone.utc)})
    return name


async def refresh_logos(db) -> None:
    LOGOS.clear()
    LOGOS.update({b["name"]: b["logo"] async for b in db.brands.find({"logo": {"$nin": [None, ""]}}, {"_id": 0, "name": 1, "logo": 1})})


async def seed(db) -> None:
    """Every brand already on a product gets an entry (idempotent), so the 6.618 imported products keep their brand."""
    known = {b["name"].lower() for b in await db.brands.find({}, {"_id": 0, "name": 1}).to_list(100000)}
    for name in sorted(n for n in await db.products.distinct("brand") if isinstance(n, str)):
        n = (name or "").strip()
        if n and n.lower() not in known:
            known.add(n.lower())
            await db.brands.insert_one({"brand_id": uuid.uuid4().hex[:12], "name": n, "logo": "", "created_at": datetime.now(timezone.utc)})
    if not await db.categories.find_one({"category_id": OTHER}):
        await db.categories.insert_one({"category_id": OTHER, "name": "Lainnya", "icon": "ellipsis-horizontal-circle-outline", "image": "", "parent": None, "count": 0})
    await refresh_logos(db)


def register(api, db, *, require_admin):

    async def brand_counts() -> Dict[str, int]:
        return {r["_id"]: r["n"] for r in await db.products.aggregate([
            {"$match": {"brand": {"$nin": [None, ""]}, "status": {"$ne": "inactive"}}}, {"$group": {"_id": "$brand", "n": {"$sum": 1}}}]).to_list(100000)}

    async def get_brand(brand_id: str) -> dict:
        b = await db.brands.find_one({"brand_id": brand_id}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail="Merek tidak ditemukan")
        return b

    @api.get("/brands")
    async def list_brands():
        """Daftar merek (pilihan di Tambah Produk, logo di filter merek)."""
        counts = await brand_counts()
        docs = await db.brands.find({}, {"_id": 0, "created_at": 0}).to_list(100000)
        return sorted(({**b, "count": counts.get(b["name"], 0)} for b in docs), key=lambda b: b["name"].lower())

    # ---------------- Merek Unggulan di Beranda ----------------
    async def featured_ids() -> Optional[List[str]]:
        d = await db.app_settings.find_one({"_id": "featured_brands"})
        return d["items"] if d else None

    @api.get("/brands/featured")
    async def featured_brands():
        """Deretan logo merek di Beranda: pilihan Super Admin (urut), belum diatur = 10 merek dengan produk terbanyak."""
        counts = await brand_counts()
        ids = await featured_ids()
        if ids is None:
            docs = await db.brands.find({}, {"_id": 0, "created_at": 0}).to_list(100000)
            return sorted(({**b, "count": counts.get(b["name"], 0)} for b in docs
                           if counts.get(b["name"]) and b["name"].strip().lower() not in ("no brand", "tanpa merek", "-")), key=lambda b: (-b["count"], b["name"].lower()))[:10]
        got = {b["brand_id"]: b for b in await db.brands.find({"brand_id": {"$in": ids}}, {"_id": 0, "created_at": 0}).to_list(100)}
        return [{**got[i], "count": counts.get(got[i]["name"], 0)} for i in ids if i in got]

    @api.get("/admin/featured-brands")
    async def get_featured(admin=Depends(require_admin)):
        ids = await featured_ids()
        return {"custom": ids is not None, "items": await featured_brands()}

    class FeaturedIn(BaseModel):
        items: Optional[List[str]] = Field(default=None, max_length=30)  # None = back to automatic

    @api.put("/admin/featured-brands")
    async def save_featured(body: FeaturedIn, admin=Depends(require_admin)):
        if body.items is None:
            await db.app_settings.delete_one({"_id": "featured_brands"})
        else:
            ok = {b["brand_id"] for b in await db.brands.find({"brand_id": {"$in": body.items}}, {"_id": 0, "brand_id": 1}).to_list(100)}
            items = [i for i in dict.fromkeys(body.items) if i in ok]
            await db.app_settings.update_one({"_id": "featured_brands"}, {"$set": {"items": items}}, upsert=True)
        return await get_featured(admin)

    @api.post("/admin/brands")
    async def create_brand(body: BrandIn, admin=Depends(require_admin)):
        name = body.name.strip()
        if await find_brand(db, name):
            raise HTTPException(status_code=409, detail=f"Merek “{name}” sudah ada")
        doc = {"brand_id": uuid.uuid4().hex[:12], "name": name, "logo": body.logo.strip(), "created_at": datetime.now(timezone.utc)}
        await db.brands.insert_one(dict(doc))
        await refresh_logos(db)
        return {**{k: v for k, v in doc.items() if k != "created_at"}, "count": 0}

    @api.get("/admin/brands/{brand_id}/impact")
    async def brand_impact(brand_id: str, admin=Depends(require_admin)):
        b = await get_brand(brand_id)
        return {"products": await db.products.count_documents({"brand": b["name"]})}

    @api.put("/admin/brands/{brand_id}")
    async def update_brand(brand_id: str, body: BrandIn, admin=Depends(require_admin)):
        b = await get_brand(brand_id)
        name = body.name.strip()
        dup = await find_brand(db, name)
        if dup and dup["brand_id"] != brand_id:
            raise HTTPException(status_code=409, detail=f"Merek “{name}” sudah ada")
        moved = 0
        if name != b["name"]:  # rename: the products follow, nothing is lost
            moved = (await db.products.update_many({"brand": b["name"]}, {"$set": {"brand": name}})).modified_count
        await db.brands.update_one({"brand_id": brand_id}, {"$set": {"name": name, "logo": body.logo.strip()}})
        await refresh_logos(db)
        return {"brand_id": brand_id, "name": name, "logo": body.logo.strip(), "products_updated": moved}

    @api.delete("/admin/brands/{brand_id}")
    async def delete_brand(brand_id: str, admin=Depends(require_admin)):
        b = await get_brand(brand_id)
        cleared = (await db.products.update_many({"brand": b["name"]}, {"$set": {"brand": ""}})).modified_count  # -> "Tanpa merek"
        await db.brands.delete_one({"brand_id": brand_id})
        await refresh_logos(db)
        return {"deleted": True, "products_updated": cleared}

    # ---------------- kategori ----------------
    async def get_cat(cid: str) -> dict:
        c = await db.categories.find_one({"category_id": cid}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
        return c

    async def subtree(cid: str) -> List[str]:
        ids, frontier = [cid], [cid]
        while frontier:
            frontier = [c["category_id"] for c in await db.categories.find({"parent": {"$in": frontier}}, {"_id": 0, "category_id": 1}).to_list(5000)]
            ids += frontier
        return ids

    def uses(ids: List[str]) -> dict:
        return {"$or": [{"category": {"$in": ids}}, {"subcategory": {"$in": ids}}, {"categories": {"$in": ids}}]}

    async def same_name(name: str, parent: Optional[str], skip: str = "") -> bool:
        return bool(await db.categories.find_one({"name": _ci(name), "parent": parent or None, "category_id": {"$ne": skip}}))

    @api.post("/admin/categories")
    async def create_category(body: CategoryIn, admin=Depends(require_admin)):
        name, parent = body.name.strip(), (body.parent or None)
        if parent:
            await get_cat(parent)
        if await same_name(name, parent):
            raise HTTPException(status_code=409, detail=f"Kategori “{name}” sudah ada")
        base = cid = _slug(name)
        n = 2
        while await db.categories.find_one({"category_id": cid}):
            cid, n = f"{base}-{n}", n + 1
        doc = {"category_id": cid, "name": name, "icon": body.icon or "pricetag-outline", "image": body.image.strip(), "parent": parent, "count": 0, "source": "admin"}
        await db.categories.insert_one(dict(doc))
        return doc

    @api.get("/admin/categories/{cid}/impact")
    async def category_impact(cid: str, admin=Depends(require_admin)):
        await get_cat(cid)
        ids = await subtree(cid)
        return {"products": await db.products.count_documents(uses(ids)), "subcategories": len(ids) - 1}

    @api.put("/admin/categories/{cid}")
    async def update_category(cid: str, body: CategoryIn, admin=Depends(require_admin)):
        c = await get_cat(cid)
        name = body.name.strip()
        if await same_name(name, c.get("parent"), skip=cid):
            raise HTTPException(status_code=409, detail=f"Kategori “{name}” sudah ada")
        # the id stays the same, so every product keeps its category
        upd = {"name": name, "icon": body.icon or c.get("icon") or "pricetag-outline", "image": body.image.strip()}
        await db.categories.update_one({"category_id": cid}, {"$set": upd})
        return {**c, **upd}

    @api.delete("/admin/categories/{cid}")
    async def delete_category(cid: str, admin=Depends(require_admin)):
        if cid == OTHER:
            raise HTTPException(status_code=400, detail="Kategori Lainnya tidak bisa dihapus")
        await get_cat(cid)
        ids = await subtree(cid)
        # ancestors of the deleted category don't keep the product (choice: products go to "Lainnya");
        # other, unrelated categories of a product stay
        drop, p = set(ids), (await get_cat(cid)).get("parent")
        while p and p not in drop:
            drop.add(p)
            p = (await db.categories.find_one({"category_id": p}, {"_id": 0, "parent": 1}) or {}).get("parent")
        moved = 0
        async for d in db.products.find(uses(ids), {"_id": 0, "product_id": 1, "category": 1, "subcategory": 1, "categories": 1}):
            rest = [c for c in d.get("categories") or [] if c not in drop]
            cats = rest or [OTHER]
            cat = d.get("category") if d.get("category") and d["category"] not in drop else cats[0]
            sub = d.get("subcategory") if d.get("subcategory") and d["subcategory"] not in drop and rest else ""
            await db.products.update_one({"product_id": d["product_id"]}, {"$set": {"category": cat, "subcategory": sub, "categories": cats}})
            moved += 0 if rest else 1  # only the ones that really land in "Lainnya"
        await db.categories.delete_many({"category_id": {"$in": ids}})
        if moved:
            await db.categories.update_one({"category_id": OTHER}, {"$inc": {"count": moved}})
        return {"deleted": len(ids), "products_moved": moved}
