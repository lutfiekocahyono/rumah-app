"""Multi-branch helpers (ruparupa-style): stock at every branch, nearest branch from the buyer's area,
and moving a cart to another branch (for pickup / nearer store)."""
import math
import re
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

# Branch coordinates (approximate city centre)
BRANCH_COORDS = {"pgs-official": (-7.447, 112.718), "pgs-jombang": (-7.546, 112.233), "pgs-jember": (-8.172, 113.700)}

# East Java regencies/cities + province fallbacks (approximate centroids) — no external API needed
PLACES = {
    "SURABAYA": (-7.257, 112.752), "SIDOARJO": (-7.447, 112.718), "GRESIK": (-7.156, 112.655), "MOJOKERTO": (-7.472, 112.434),
    "JOMBANG": (-7.546, 112.233), "LAMONGAN": (-7.117, 112.417), "BOJONEGORO": (-7.150, 111.882), "TUBAN": (-6.897, 112.064),
    "PASURUAN": (-7.645, 112.907), "PROBOLINGGO": (-7.754, 113.216), "MALANG": (-7.983, 112.621), "BATU": (-7.871, 112.527),
    "KEDIRI": (-7.817, 112.012), "NGANJUK": (-7.605, 111.904), "BLITAR": (-8.095, 112.161), "TULUNGAGUNG": (-8.066, 111.902),
    "TRENGGALEK": (-8.050, 111.708), "MADIUN": (-7.630, 111.523), "MAGETAN": (-7.653, 111.328), "NGAWI": (-7.404, 111.446),
    "PONOROGO": (-7.871, 111.462), "PACITAN": (-8.205, 111.092), "LUMAJANG": (-8.134, 113.224), "JEMBER": (-8.172, 113.700),
    "BONDOWOSO": (-7.913, 113.822), "SITUBONDO": (-7.706, 114.009), "BANYUWANGI": (-8.219, 114.369), "BANGKALAN": (-7.045, 112.737),
    "SAMPANG": (-7.192, 113.239), "PAMEKASAN": (-7.157, 113.474), "SUMENEP": (-7.005, 113.859),
    # provinces
    "BALI": (-8.409, 115.189), "NUSA TENGGARA BARAT": (-8.652, 117.362), "NUSA TENGGARA TIMUR": (-8.657, 121.079),
    "JAWA TENGAH": (-7.150, 110.140), "DI YOGYAKARTA": (-7.795, 110.369), "YOGYAKARTA": (-7.795, 110.369),
    "JAWA BARAT": (-6.903, 107.619), "DKI JAKARTA": (-6.200, 106.816), "JAKARTA": (-6.200, 106.816), "BANTEN": (-6.405, 106.064),
}


def _km(a: tuple, b: tuple) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def locate(area: str) -> Optional[tuple]:
    """Find coordinates from a RajaOngkir label ('GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281') or a city name."""
    up = re.sub(r"\b(KABUPATEN|KAB\.?|KOTA)\b", "", (area or "").upper())
    parts = [p.strip() for p in up.split(",") if p.strip()]
    for p in (parts[2:3] + parts[3:4] + parts[:2]) if len(parts) >= 3 else parts:  # city first, then province
        if p in PLACES:
            return PLACES[p]
    for name, c in PLACES.items():  # free text like "Kota Malang"
        if re.search(rf"\b{name}\b", up):
            return c
    return None


class SuggestIn(BaseModel):
    area: str = Field(default="", max_length=200)
    product_ids: List[str] = Field(default=[], max_length=100)
    quantities: List[int] = Field(default=[], max_length=100)


class MoveCartIn(BaseModel):
    from_store_id: str
    to_store_id: str


def register(api, db, get_owner, seller):

    async def stock_at(store_id: str, products: List[dict]) -> dict:
        shared = [p["product_id"] for p in products if p.get("store_id", seller.PGS_STORE_ID) == seller.PGS_STORE_ID]
        branch = await seller.branch_stocks(db, store_id, shared) if store_id != seller.PGS_STORE_ID else {}
        out = {}
        for p in products:
            if p.get("store_id", seller.PGS_STORE_ID) != seller.PGS_STORE_ID:  # branch-exclusive product
                out[p["product_id"]] = p.get("stock", 0) if p["store_id"] == store_id else 0
            elif store_id == seller.PGS_STORE_ID:
                out[p["product_id"]] = p.get("stock", 0) if p.get("in_stock", True) else 0
            else:
                out[p["product_id"]] = branch.get(p["product_id"], 0)
        return out

    async def suggest(area: str, product_ids: List[str], quantities: List[int]) -> dict:
        stores = await db.stores.find({"store_id": {"$in": seller.OFFICIAL_IDS}, "status": "active"},
                                      {"_id": 0, "store_id": 1, "name": 1, "city": 1, "address": 1, "pickup_hours": 1, "phone": 1}).to_list(10)
        prods = await db.products.find({"product_id": {"$in": product_ids}}, {"_id": 0, "product_id": 1, "store_id": 1, "stock": 1, "in_stock": 1}).to_list(100)
        need = {pid: (quantities[i] if i < len(quantities) else 1) for i, pid in enumerate(product_ids)}
        here = locate(area)
        rows = []
        for s in stores:
            st = await stock_at(s["store_id"], prods)
            rows.append({**s, "address": s.get("address") or "", "pickup_hours": s.get("pickup_hours") or "", "phone": s.get("phone") or "",
                         "stock": st, "available": all(st.get(pid, 0) >= q for pid, q in need.items()) if need else True,
                         "distance_km": round(_km(here, BRANCH_COORDS[s["store_id"]])) if here and s["store_id"] in BRANCH_COORDS else None})
        rows.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0))
        best = next((r["store_id"] for r in rows if r["available"]), None) if here else None
        return {"located": bool(here), "suggested": best, "stores": rows}

    @api.get("/branches/nearest")
    async def stores_nearest(lat: float, lng: float):
        """Official branches sorted by distance from the buyer's GPS position."""
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise HTTPException(status_code=400, detail="Koordinat tidak valid")
        stores = await db.stores.find({"store_id": {"$in": seller.OFFICIAL_IDS}, "status": "active"}, {"_id": 0, "store_id": 1, "name": 1}).to_list(10)
        rows = sorted(({**s, "distance_km": round(_km((lat, lng), BRANCH_COORDS[s["store_id"]]), 1)} for s in stores if s["store_id"] in BRANCH_COORDS),
                      key=lambda r: r["distance_km"])
        return {"nearest": rows[0] if rows else None, "stores": rows}

    @api.post("/stores/suggest")
    async def stores_suggest(body: SuggestIn):
        return await suggest(body.area, body.product_ids, body.quantities)

    @api.get("/products/{product_id}/availability")
    async def availability(product_id: str, area: str = ""):
        if not await db.products.find_one({"product_id": product_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        return await suggest(area, [product_id], [1])

    @api.post("/cart/move")
    async def move_cart(body: MoveCartIn, owner: str = Depends(get_owner)):
        """Move every item of one branch's cart to another branch (stock-checked, qty capped)."""
        if body.to_store_id not in seller.OFFICIAL_IDS or body.from_store_id == body.to_store_id \
                or not await db.stores.find_one({"store_id": body.to_store_id, "status": "active"}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Toko tujuan tidak valid")
        cart = await db.carts.find_one({"owner": owner}) or {"items": []}
        items = [{**i, "store_id": i.get("store_id", seller.PGS_STORE_ID)} for i in cart.get("items", [])]
        moving = [i for i in items if i.get("store_id", seller.PGS_STORE_ID) == body.from_store_id]
        if not moving:
            raise HTTPException(status_code=400, detail="Keranjang toko ini kosong")
        prods = await db.products.find({"product_id": {"$in": [i["product_id"] for i in moving]}}, {"_id": 0}).to_list(200)
        if any(p.get("store_id", seller.PGS_STORE_ID) != seller.PGS_STORE_ID for p in prods):
            raise HTTPException(status_code=400, detail="Ada produk khusus toko ini yang tidak bisa dipindah")
        st = await stock_at(body.to_store_id, prods)
        kept = [i for i in items if i.get("store_id", seller.PGS_STORE_ID) not in (body.from_store_id, body.to_store_id)]
        target = {i["product_id"]: i for i in items if i.get("store_id") == body.to_store_id}
        skipped = []
        for i in moving:
            have = st.get(i["product_id"], 0)
            if have <= 0:
                skipped.append(i["product_id"])
                kept.append(i)  # stays in the old branch's cart
                continue
            t = target.setdefault(i["product_id"], {"product_id": i["product_id"], "quantity": 0, "store_id": body.to_store_id})
            t["quantity"] = min(have, t["quantity"] + i["quantity"])
        await db.carts.update_one({"owner": owner}, {"$set": {"items": kept + list(target.values())}}, upsert=True)
        return {"moved": len(moving) - len(skipped), "skipped": skipped}
