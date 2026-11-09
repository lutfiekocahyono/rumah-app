"""Isi merek produk impor dari atribut "Brand" (pa_brand) di pusatgrosirsidoarjo.com.

Run: python import_brands.py   (idempotent; hanya mengisi produk yang mereknya masih kosong, merek yang diubah di aplikasi tidak ditimpa)
"""
import asyncio
import html

import httpx

from import_pgs import BASE, HEADERS, db


async def get(client: httpx.AsyncClient, path: str, params: dict) -> list:
    for attempt in range(4):
        try:
            r = await client.get(f"{BASE}{path}", params=params, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            if attempt == 3:
                raise
            await asyncio.sleep(2 * (attempt + 1))
    return []


async def main():
    async with httpx.AsyncClient() as client:
        terms, page = [], 1
        while True:
            batch = await get(client, "/products/attributes/2/terms", {"per_page": 100, "page": page})
            terms += batch
            if len(batch) < 100:
                break
            page += 1
        brand_of: dict = {}
        for t in terms:
            name = html.unescape(t["name"]).strip()
            page = 1
            while True:
                items = await get(client, "/products", {"per_page": 100, "page": page, "attributes[0][attribute]": "pa_brand",
                                                         "attributes[0][term_id]": t["id"]})
                for p in items:
                    brand_of.setdefault(f"pgs-{p['id']}", name)
                if len(items) < 100:
                    break
                page += 1
            print(f"{name}: {t['count']}", flush=True)
    filled = 0
    for pid, brand in brand_of.items():
        res = await db.products.update_one({"product_id": pid, "brand": {"$in": [None, ""]}}, {"$set": {"brand": brand}})
        filled += res.modified_count
    print(f"merek: {len(terms)} | produk bermerek di website: {len(brand_of)} | diisi: {filled}")


if __name__ == "__main__":
    asyncio.run(main())
