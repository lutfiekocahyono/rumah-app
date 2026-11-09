"""Cari dengan foto: every product photo (max 3 per product) becomes a 512-number visual fingerprint
(CLIP ViT-B/32, runs on our own server - no paid AI per search). A buyer's photo is compared with all of them."""
import asyncio
import hashlib
import io
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import numpy as np
from fastapi import Depends, File, Header, HTTPException, UploadFile
from PIL import Image
from starlette.concurrency import run_in_threadpool

import seller

log = logging.getLogger("image_search")
logging.getLogger("httpx").setLevel(logging.WARNING)  # thousands of photo downloads
MODEL = "Qdrant/clip-ViT-B-32-vision"
MAX_IMAGES = 3
RESULTS = 20
_model = None
_lock = asyncio.Lock()
_index = {"ids": [], "mat": None, "dirty": True, "built": 0.0}  # in-memory matrix of all fingerprints
status = {"running": False, "done": 0, "failed": 0, "last_run": None}


def _embedder():
    global _model
    if _model is None:
        from fastembed import ImageEmbedding
        _model = ImageEmbedding(MODEL, cache_dir="/tmp/fastembed_models")
    return _model


def _embed(images: list) -> list:
    vecs = list(_embedder().embed(images, batch_size=32))
    return [(v / (np.linalg.norm(v) or 1)).astype(np.float32) for v in vecs]


def _open(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.thumbnail((448, 448))
    return img.convert("RGB")


def _thumb(url: str) -> str:
    """WordPress keeps a 300x300 copy: much smaller to download."""
    return re.sub(r"(-scaled)?(-\d+x\d+)?(\.(jpe?g|png|webp))$", r"-300x300\3", url, flags=re.I)


def photos(p: dict) -> list:
    urls = [u for u in (p.get("images") or []) if u][:MAX_IMAGES] or ([p["image"]] if p.get("image") else [])
    return urls


def signature(p: dict) -> str:
    return hashlib.md5("|".join(photos(p)).encode()).hexdigest()


def register(api, db, *, require_admin, get_optional_user, visible, apply_stock, product_out, active_flash):
    async def fetch(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
        for u in ([_thumb(url), url] if "pusatgrosirsidoarjo.com" in url and "-300x300" not in url else [url]):
            try:
                r = await client.get(u if u.startswith("http") else f"http://localhost:8001{u}")
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                    return r.content
            except Exception:
                pass
        return None

    async def index_batch(client, prods: list):
        sem = asyncio.Semaphore(16)

        async def one(p):
            async with sem:
                return p, [b for b in await asyncio.gather(*[fetch(client, u) for u in photos(p)]) if b]
        got = await asyncio.gather(*[one(p) for p in prods])
        imgs, owners = [], []
        for p, blobs in got:
            for b in blobs:
                try:
                    imgs.append(_open(b)); owners.append(p["product_id"])
                except Exception:
                    pass
        vecs = await run_in_threadpool(_embed, imgs) if imgs else []
        by: dict = {}
        for pid, v in zip(owners, vecs):
            by.setdefault(pid, []).append(v.tolist())
        for p, _ in got:
            vs = by.get(p["product_id"], [])
            await db.image_vectors.update_one({"product_id": p["product_id"]}, {"$set": {"vectors": vs, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
            upd = {"$set": {"img_sig": signature(p), "img_tries": 0}} if vs else {"$set": {"img_sig": "failed:" + signature(p)}, "$inc": {"img_tries": 1}}
            await db.products.update_one({"product_id": p["product_id"]}, upd)
            status["done" if vs else "failed"] += 1
        _index["dirty"] = True

    async def run_index():
        """Fingerprint new / changed product photos (failed downloads are retried up to 3 runs, then again when the photos change)."""
        status["running"] = True
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "PGS-ImageIndex/1.0"}) as client:
                tried: set = set()  # a failed product is tried once per run
                while True:
                    batch = []
                    async for p in db.products.find({"status": {"$ne": "inactive"}}, {"_id": 0, "product_id": 1, "image": 1, "images": 1, "img_sig": 1, "img_tries": 1}):
                        sig = signature(p)
                        if p.get("img_sig") != sig and not (p.get("img_sig") == "failed:" + sig and p.get("img_tries", 0) >= 3) and p["product_id"] not in tried:
                            tried.add(p["product_id"])
                            batch.append(p)
                            if len(batch) >= 48:
                                break
                    if not batch:
                        break
                    await index_batch(client, batch)
            gone = set(await db.image_vectors.distinct("product_id")) - set(await db.products.distinct("product_id"))
            if gone:
                await db.image_vectors.delete_many({"product_id": {"$in": list(gone)}})
                _index["dirty"] = True
        finally:
            status["running"] = False
            status["last_run"] = datetime.now(timezone.utc)

    async def loop():
        await asyncio.sleep(20)
        while True:
            try:
                await run_index()
            except Exception:
                log.exception("image index failed")
            await asyncio.sleep(300)  # new / edited products are picked up every 5 minutes

    async def matrix():
        async with _lock:
            # while indexing, rebuild at most once a minute so searches stay fast
            if _index["dirty"] and (_index["mat"] is None or time.monotonic() - _index["built"] > 60):
                ids, rows = [], []
                async for d in db.image_vectors.find({"vectors.0": {"$exists": True}}, {"_id": 0, "product_id": 1, "vectors": 1}):
                    for v in d["vectors"]:
                        ids.append(d["product_id"]); rows.append(v)
                _index.update(ids=ids, mat=np.asarray(rows, dtype=np.float32) if rows else None, dirty=False, built=time.monotonic())
        return _index["ids"], _index["mat"]

    @api.post("/products/image-search")
    async def image_search(file: UploadFile = File(...), user=Depends(get_optional_user), x_store_id: Optional[str] = Header(default=None)):
        data = await file.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran foto maksimal 10 MB")
        try:
            img = _open(data)
        except Exception:
            raise HTTPException(status_code=400, detail="File bukan foto yang bisa dibaca. Gunakan JPG atau PNG")
        ids, mat = await matrix()
        if mat is None:
            raise HTTPException(status_code=503, detail="Pencarian foto sedang disiapkan. Coba lagi beberapa menit lagi")
        q = (await run_in_threadpool(_embed, [img]))[0]
        scores = mat @ q
        best: dict = {}
        for i in np.argsort(-scores)[:600]:  # a product counts once, with its closest photo
            pid = ids[i]
            if pid not in best:
                best[pid] = float(scores[i])
        branch = x_store_id if x_store_id in seller.OFFICIAL_IDS else seller.PGS_STORE_ID
        docs = await db.products.find({**await visible("all", branch), "product_id": {"$in": list(best)}}, {"_id": 0}).to_list(len(best))
        docs = sorted(docs, key=lambda d: -best[d["product_id"]])[:RESULTS * 2]
        await apply_stock(docs, branch, branch)  # the buyer's branch price & stock
        docs = sorted(docs[:RESULTS], key=lambda d: (0 if d.get("stock", 0) > 0 and d.get("in_stock", True) else 1, -best[d["product_id"]]))
        flash, ctype = await active_flash(db), (user or {}).get("customer_type", "langsung")
        return {"items": [{**product_out(d, ctype, flash, branch).model_dump(), "similarity": round(best[d["product_id"]] * 100)} for d in docs],
                "indexed": len(set(ids))}

    @api.get("/admin/image-index")
    async def index_status(_=Depends(require_admin)):
        return {**status, "products": await db.products.count_documents({"status": {"$ne": "inactive"}}),
                "indexed": await db.image_vectors.count_documents({"vectors.0": {"$exists": True}})}

    return loop
