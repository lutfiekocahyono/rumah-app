"""Rapikan kategori "Lainnya": usulan kategori per produk dari nama produk, pratinjau, lalu simpan setelah dikonfirmasi.

Usulan = kata kunci yang jelas (lemari, piring, rice cooker, ...) lalu "produk mirip": kata-kata nama produk dibandingkan
dengan ribuan produk yang kategorinya sudah benar (kata langka lebih berbobot), kategori terbanyak dari yang paling mirip menang."""
import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel

# (pola nama, category_id) — urutan penting
KEYWORDS = [
    (r"karpet mobil|kipas mobil|sapu mobil", "interior-mobil"),
    (r"(pampers|popok).*dewasa", "kesehatan-lainnya"),
    (r"\btas\b(?! spunbond| kurir)", "fashion-wanita"),
    (r"speaker|audio mixer|\bmic\b|microphone", "audio"),
    (r"gelas plastik|cup hokka|tas spunbond|karbon box|kemasan", "kemasan-makanan-minuman"),
    (r"kursi lipat outdoor|camping|tenda", "hiking-camping"),
    (r"kurma|kue kering|nastar|minyak goreng|coklat|bellarosa", "makanan-jadi"),
    (r"boncengan", "aksesoris-pengendara-motor"),
    (r"lemari (plastik|mini|anak|.*susun)|loker|laci|kontainer|container box|rak container", "pabrik-lemari-plastik"),
    (r"lemari besi|lemari arsip|filing cabinet", "furniture"),
    (r"\b(meja|kursi|sofa|lemari|marble swing|rak sepatu)\b", "furniture"),
    (r"showcase|freezer|kulkas|rice cooker|magic com|magic warmer|\btv\b|dispenser|setrika|blender|chopper|mixer|oven|kompor listrik|pompa galon|insect killer|timbangan", "elektronik-rumah-tangga"),
    (r"stand fan|kipas angin|air cooler", "alat-pendingin-ruangan"),
    (r"\b(lampu|bohlam|led)\b(?!.*sepeda)", "lampu"),
    (r"panci|wajan|frypan|teflon|penggorengan|stock pot|wok|kompor|regulator|pemanggang|roaster", "peralatan-masak"),
    (r"piring|mangkok|mangkuk|gelas|cangkir|mug|sendok|garpu|irus|jug|nampan|rantang|asbak", "peralatan-makan-minum"),
    (r"cetakan|loyang|pizza pan|crepes|pukis", "peralatan-baking"),
    (r"toples|fresh box|rice bucket|kotak makan|lunch box|kotak susu|botol minum", "penyimpanan-makanan"),
    (r"gilingan|parutan|pisau|serok|cobek|perajang|peras|spatula|tutup sayur|cup sealer|cup lid sealer", "peralatan-dapur"),
    (r"tissue|tisu|detergen|pembersih lantai|sapu|pel\b|kemoceng|keset", "kebersihan"),
    (r"selimut|bantal|guling|sprei|kasur", "kamar-tidur"),
    (r"timba|ember|baskom|basin|bak kuping", "kebutuhan-rumah"),
    (r"payung|jas hujan|hanger|gembok|jebakan tikus|perlengkapan jahit|sealant|lakban|flex tape|selang", "kebutuhan-rumah"),
    (r"kunci (sock|rem|\d+ in 1)|alat ukir|gas torch|waterproof", "hand-tool"),
    (r"sepeda|helm", "aksesoris-olahraga"),
    (r"sepatu roda|matras yoga|yoga", "gym-fitnes"),
    (r"crayon|magic water book|alat tulis|pensil|buku", "alat-tulis"),
    (r"tongsis|tripod|holder|kabel roll|box kabel", "elektronik-lainnya"),
    (r"pampers|popok", "perawatan-bayi"),
    (r"body cream|lotion", "perawatan-tubuh"),
    (r"sepatu|sandal|kaos|kemeja|celana|baju|jaket", "fashion-pria"),
    (r"bendera|dekorasi|hiasan", "dekorasi"),
    (r"tatakan telur|tempat telur", "peralatan-dapur"),
]
_KW = [(re.compile(p, re.I), c) for p, c in KEYWORDS]
_TOKEN = re.compile(r"[a-z]{3,}")
STOP = {"isi", "pcs", "dus", "lusin", "pack", "set", "dan", "warna", "motif", "ukuran", "size", "new", "plus", "free", "untuk", "dengan", "inch", "liter", "kunci"}


def tokens(name: str) -> set:
    return {t for t in _TOKEN.findall(name.lower()) if t not in STOP}


class Index:
    """Produk berkategori benar: kata -> kategori, untuk mencari produk mirip."""

    def __init__(self, docs: List[dict]):
        self.docs = [(tokens(d.get("name") or ""), d["category"]) for d in docs]
        df: Counter = Counter()
        self.by_token: Dict[str, List[int]] = defaultdict(list)
        for i, (toks, _) in enumerate(self.docs):
            for t in toks:
                df[t] += 1
                self.by_token[t].append(i)
        n = max(1, len(self.docs))
        self.idf = {t: math.log(n / c) for t, c in df.items()}

    def similar(self, name: str, k: int = 7) -> tuple[Optional[str], float, str]:
        toks = [t for t in tokens(name) if t in self.idf and len(self.by_token[t]) < 1500]
        score: Counter = Counter()
        for t in toks:
            for i in self.by_token[t]:
                score[i] += self.idf[t]
        if not score:
            return None, 0.0, ""
        votes: Counter = Counter()
        top = score.most_common(k)
        for i, s in top:
            votes[self.docs[i][1]] += s
        cat, v = votes.most_common(1)[0]
        return cat, v / sum(votes.values()), " ".join(sorted(toks, key=lambda t: -self.idf[t])[:3])


def suggest(name: str, index: Index, valid: set) -> dict:
    for rx, cat in _KW:
        m = rx.search(name)
        if m and cat in valid:
            return {"suggested": cat, "confidence": "tinggi", "reason": f"kata “{m.group(0).strip()}”"}
    cat, share, words = index.similar(name)
    if cat:
        return {"suggested": cat, "confidence": "sedang" if share >= 0.6 else "rendah", "reason": f"mirip produk lain ({words})"}
    return {"suggested": "", "confidence": "rendah", "reason": "tidak ada petunjuk, pilih manual"}


class ApplyIn(BaseModel):
    skip: List[str] = []
    overrides: Dict[str, str] = {}


def register(api, db, *, actor, target_store, log_activity):
    async def valid_ids() -> Dict[str, dict]:
        return {c["category_id"]: c for c in await db.categories.find({}, {"_id": 0, "category_id": 1, "name": 1, "parent": 1}).to_list(5000)}

    cache: dict = {}

    @api.get("/product-editor/category-suggest")
    async def category_suggest(name: str = "", ctx=Depends(actor)):
        """Usulan kategori saat menambah produk, dari nama produk (admin tetap bisa menggantinya)."""
        name = name.strip()[:150]
        if len(name) < 3:
            return {"suggested": "", "category": "", "subcategory": "", "confidence": "rendah", "reason": ""}
        now = datetime.now(timezone.utc)
        if not cache or now - cache["at"] > timedelta(minutes=10):  # the word index of ~6.000 products is rebuilt every 10 min
            cats = await valid_ids()
            docs = await db.products.find({"category": {"$in": [c for c in cats if c != "lainnya"]}}, {"_id": 0, "name": 1, "category": 1}).to_list(50000)
            cache.update(at=now, cats=cats, index=Index(docs))
        cats = cache["cats"]
        s = suggest(name, cache["index"], set(cats) - {"lainnya"})
        c = cats.get(s["suggested"]) or {}
        parent = c.get("parent")  # the editor has main category + sub-category
        return {**s, "category": parent or c.get("category_id", ""), "subcategory": c.get("category_id", "") if parent else ""}

    def uncategorized(ids) -> dict:
        return {"$or": [{"category": {"$nin": list(ids)}}, {"category": {"$exists": False}}]}

    @api.get("/product-editor/uncategorized/summary")
    async def uncat_summary(store_id: Optional[str] = None, ctx=Depends(actor)):
        store = await target_store(ctx, store_id)
        cats = await valid_ids()
        return {"store_id": store["store_id"], "count": await db.products.count_documents({"store_id": store["store_id"], **uncategorized(cats)})}

    @api.post("/product-editor/uncategorized/preview")
    async def uncat_preview(store_id: Optional[str] = None, ctx=Depends(actor)):
        store = await target_store(ctx, store_id)
        cats = await valid_ids()
        index = Index(await db.products.find({"category": {"$in": list(cats)}}, {"_id": 0, "name": 1, "category": 1}).to_list(50000))
        items = []
        async for p in db.products.find({"store_id": store["store_id"], **uncategorized(cats)}, {"_id": 0, "product_id": 1, "name": 1, "image": 1}).sort("name", 1):
            items.append({"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", ""), **suggest(p.get("name") or "", index, set(cats))})
        doc = {"preview_id": f"cp_{uuid.uuid4().hex[:10]}", "kind": "category", "store_id": store["store_id"], "items": items,
               "by": ctx["user"]["user_id"], "created_at": datetime.now(timezone.utc), "status": "preview"}
        await db.weight_previews.insert_one({**doc})
        groups = Counter(i["suggested"] or "" for i in items)
        return {"preview_id": doc["preview_id"], "total": len(items), "items": items,
                "groups": [{"category_id": k, "count": n} for k, n in groups.most_common()]}

    @api.post("/product-editor/uncategorized/{preview_id}/apply")
    async def uncat_apply(preview_id: str, body: ApplyIn, ctx=Depends(actor)):
        pre = await db.weight_previews.find_one({"preview_id": preview_id, "kind": "category"}, {"store_id": 1})
        if not pre:
            raise HTTPException(status_code=400, detail="Pratinjau tidak ditemukan. Buat pratinjau baru")
        await target_store(ctx, pre["store_id"])
        cats = await valid_ids()
        bad = [v for v in body.overrides.values() if v not in cats]
        if bad:
            raise HTTPException(status_code=400, detail=f"Kategori '{bad[0]}' tidak ditemukan")
        d = await db.weight_previews.find_one_and_update(
            {"preview_id": preview_id, "status": "preview", "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=2)}},
            {"$set": {"status": "applied"}}, projection={"_id": 0})
        if not d:
            raise HTTPException(status_code=400, detail="Pratinjau sudah dipakai atau kedaluwarsa. Buat pratinjau baru")
        skip, saved = set(body.skip), 0
        for i in d["items"]:
            cat = body.overrides.get(i["product_id"]) or i["suggested"]
            if i["product_id"] in skip or cat not in cats:
                continue
            res = await db.products.update_one({"product_id": i["product_id"], "store_id": d["store_id"], **uncategorized(cats)},
                                               {"$set": {"category": cat, "subcategory": "", "categories": [cat]}})  # no buyer notification
            saved += res.modified_count
        await log_activity(ctx["user"]["user_id"], "store", f"Merapikan kategori {saved} produk dari Lainnya")
        return {"saved": saved}
