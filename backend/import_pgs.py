"""Import all products, categories and store info from pusatgrosirsidoarjo.com (WooCommerce Store API).

Run: python import_pgs.py   (idempotent; upserts by product_id / category_id)
"""
import asyncio
import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

BASE = "https://pusatgrosirsidoarjo.com/wp-json/wc/store/v1"
HEADERS = {"User-Agent": "Mozilla/5.0 PGS-App-Importer"}

ICONS = {
    "dapur": "restaurant-outline", "rumah-tangga": "home-outline", "audio-elektronik": "tv-outline",
    "fashion": "shirt-outline", "kecantikan": "sparkles-outline", "kesehatan": "medkit-outline",
    "mainan-dan-hobi": "game-controller-outline", "makanan-dan-minuman": "fast-food-outline",
    "olahraga": "barbell-outline", "otomotif": "car-outline", "perlengkapan-bayi": "happy-outline",
    "perlengkapan-kantor-dan-alat-tulis": "pencil-outline", "pertukangan": "hammer-outline",
    "perawatan-tubuh": "water-outline",
}

STORE_INFO = {
    "key": "store",
    "name": "Pusat Grosir Sidoarjo",
    "tagline": "Tersedia Partai, Koli, Grosir, dan Ecer",
    "phone": "0813-3555-1252",
    "whatsapp": "6281335551252",
    "website": "https://pusatgrosirsidoarjo.com",
    "hours": [
        {"day": "Senin - Jumat", "time": "09:00 - 20:30"},
        {"day": "Sabtu", "time": "09:00 - 17:00"},
        {"day": "Minggu", "time": "Libur"},
    ],
    "branches": [
        {"name": "Head Office", "address": "Ritzgate Industrial Park Blok BF-1, Jl. Muncul, Bohar Timur, Kec. Gedangan, Kabupaten Sidoarjo, Jawa Timur 61257", "phone": "0813-3555-1252", "lat": -7.38038787726777, "lng": 112.71656590976855},
        {"name": "Mitra Jombang", "address": "Jl. Jogoloyo, Tejo Utara, Tejo, Kec. Mojoagung, Kabupaten Jombang, Jawa Timur 61482", "phone": "0857-3247-6665", "lat": -7.559756919213395, "lng": 112.31577769256194},
        {"name": "Mitra Jember", "address": "Jl. Kaca Piring No.125, Gebang Tengah, Gebang, Kec. Patrang, Kabupaten Jember, Jawa Timur 68117", "phone": "0811-3555-197", "lat": -8.165197103336697, "lng": 113.68313061109224},
    ],
}


def clean(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


async def get_json(client: httpx.AsyncClient, url: str):
    for attempt in range(4):
        try:
            r = await client.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # retry transient network errors
            print("retry", attempt, url, exc)
            await asyncio.sleep(2 + attempt * 3)
    return []


async def main():
    async with httpx.AsyncClient() as client:
        cats = await get_json(client, f"{BASE}/products/categories?per_page=100")
        id_to_slug = {c["id"]: c["slug"] for c in cats}
        for c in cats:
            img = (c.get("image") or {}).get("src") if c.get("image") else None
            await db.categories.update_one({"category_id": c["slug"]}, {"$set": {
                "category_id": c["slug"], "name": html.unescape(c["name"]),
                "parent": id_to_slug.get(c["parent"]) if c["parent"] else None,
                "count": c["count"], "icon": ICONS.get(c["slug"], "pricetag-outline"), "image": img or "",
                "source": "pgs",
            }}, upsert=True)
        # drop the old demo categories/products
        await db.categories.delete_many({"source": {"$ne": "pgs"}})
        await db.products.delete_many({"source": {"$ne": "pgs"}})
        await db.settings.update_one({"key": "store"}, {"$set": STORE_INFO}, upsert=True)
        print("categories", len(cats))

        page, total = 1, 0
        while True:
            items = await get_json(client, f"{BASE}/products?per_page=100&page={page}")
            if not items:
                break
            now = datetime.now(timezone.utc)
            for p in items:
                pr = p.get("prices") or {}
                price = int(pr.get("price") or 0)
                regular = int(pr.get("regular_price") or price)
                cat_slugs = [c["slug"] for c in p.get("categories", [])]
                images = [i["src"] for i in p.get("images", [])]
                stock = p.get("add_to_cart", {}).get("maximum") if p.get("is_in_stock") else 0
                await db.products.update_one({"product_id": f"pgs-{p['id']}"}, {
                    "$set": {
                        "product_id": f"pgs-{p['id']}",
                        "name": html.unescape(p["name"]),
                        "category": cat_slugs[0] if cat_slugs else "lainnya",
                        "categories": cat_slugs,
                        "price": price,
                        "original_price": max(regular, price),
                        "discount": round((regular - price) * 100 / regular) if regular > price else 0,
                        "rating": float(p.get("average_rating") or 0) or 4.8,
                        "sold": int(p.get("review_count") or 0),
                        "image": (p.get("images") or [{}])[0].get("thumbnail") or (images[0] if images else ""),
                        "images": images,
                        "description": clean(p.get("short_description")) or clean(p.get("description")),
                        "stock": min(9999, int(stock if stock is not None else (9999 if p.get("is_in_stock") else 0))),
                        "in_stock": bool(p.get("is_in_stock")),
                        "sku": p.get("sku") or "",
                        "permalink": p.get("permalink"),
                        "source": "pgs",
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                }, upsert=True)
            total += len(items)
            print("page", page, "total", total, flush=True)
            page += 1
    print("DONE", total)


if __name__ == "__main__":
    asyncio.run(main())
